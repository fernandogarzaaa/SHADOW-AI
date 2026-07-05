from .models import *
from .policy import PolicyEngine
from .safety import is_suspicious_user_request
class ApprovalWorkflow:
    def __init__(self, store=None):
        self.requests: dict[str, ApprovalRequest]={}
        self._store=store
        # Load persisted approvals on init
        if store is not None:
            for req in store.all("approvals", ApprovalRequest):
                self.requests[req.id]=req

    def _persist(self, req: ApprovalRequest):
        if self._store is not None:
            self._store.put("approvals", req.id, req)

    def create(self, action: AgentAction, reason: str):
        req=ApprovalRequest(action=action, reason=reason, action_preview=action.description, data_used_preview=action.data_used, model_used_preview=action.model_used, destination_preview=action.destination, risk_label=action.risk, requires_double_confirmation=action.destructive)
        self._persist(req)
        self.requests[req.id]=req
        return req

    def decide(self, approval_id:str, approve:bool, deny_reason:str|None=None):
        current=self.requests[approval_id]
        if current.status != ApprovalStatus.PENDING:
            raise ValueError(f"approval is already {current.status}")
        req=current.model_copy(deep=True)
        if now() > current.expires_at:
            req.status=ApprovalStatus.EXPIRED
            req.decided_at=now()
            self._persist(req)
            self.requests[approval_id]=req
            raise ValueError("approval is expired")
        req.status=ApprovalStatus.APPROVED if approve else ApprovalStatus.DENIED
        req.deny_reason=deny_reason
        req.decided_at=now()
        self._persist(req)
        self.requests[approval_id]=req
        return req

    def sweep_expired(self)->list[str]:
        """Expire and persist decisions older than 15 minutes. Returns expired IDs."""
        expired=[]
        for rid, current in list(self.requests.items()):
            if current.status==ApprovalStatus.PENDING and now() > current.expires_at:
                req=current.model_copy(deep=True)
                req.status=ApprovalStatus.EXPIRED
                req.decided_at=now()
                self._persist(req)
                self.requests[rid]=req
                expired.append(rid)
        return expired
class ToolRegistry:
    def __init__(self): self._tools={}
    def register(self,name,handler): self._tools[name]=handler
    def names(self): return sorted(self._tools)
    def execute(self, action:AgentAction):
        if action.tool_name not in self._tools: return {"status":"mock_executed","message":"Safe local mock executor", "action":action.model_dump()}
        return self._tools[action.tool_name](action.params)
class AgentPlanner:
    def plan(self, prompt:str)->AgentPlan:
        lowered=prompt.lower(); tool="answer_question"; desc=f"Answer user request: {prompt}"; destructive=False; dest=None
        if is_suspicious_user_request(prompt): tool="leak_secret"; desc="Suspicious request attempts to bypass policy or reveal secrets"
        elif any(w in lowered for w in ["send","email","message"]): tool="send_email"; desc="Draft outbound communication; sending requires approval"; dest="external_recipient"
        elif any(w in lowered for w in ["delete","remove","destroy"]): tool="delete_file"; desc="Potential destructive local action"; destructive=True
        return AgentPlan(user_intent=prompt, actions=[AgentAction(tool_name=tool, description=desc, destructive=destructive, destination=dest)], rationale="Deterministic beta planner with policy gate.")
class AgentCore:
    def __init__(self, profile:UserProfile|None=None, approval_store=None):
        self.profile=profile or UserProfile()
        self.policy=PolicyEngine()
        self.approvals=ApprovalWorkflow(store=approval_store)
        self.tools=ToolRegistry()
        self.audit=[]
    def propose(self,prompt:str, data_used:list[str]|None=None, model_used:str|None=None):
        plan=AgentPlanner().plan(prompt)
        for a in plan.actions:
            a.data_used=data_used or []; a.model_used=model_used; a.risk=self.policy.classify_action(a); a.requires_approval=self.policy.requires_approval(a,self.profile)
            if a.requires_approval: self.approvals.create(a,"Policy requires explicit user decision before execution.")
        if any(a.risk==RiskClass.BLOCKED for a in plan.actions): self.audit.append(AuditEvent(actor="agent_core", event_type="suspicious_request_blocked", proposed_action=prompt, status="blocked"))
        return plan
    def execute(self, action:AgentAction, approved:bool=False, double_confirmed:bool=False):
        ok,reason=self.policy.can_execute(action,self.profile,approved,double_confirmed)
        self.audit.append(AuditEvent(actor="agent_core", event_type="execute", data_used=action.data_used, model_used=action.model_used, proposed_action=action.description, permission_checked=reason, status="allowed" if ok else "blocked"))
        if not ok: return {"ok":False,"reason":reason}
        return {"ok":True,"result":self.tools.execute(action)}
