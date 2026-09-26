from .models import *
from .policy import PolicyEngine
from .safety import is_suspicious_user_request
from .verification import (
    EvidenceItem,
    ExecutionRecord,
    VerificationStatus,
    diff_snapshots,
    evidence_error,
    evidence_policy,
    evidence_tool_output,
    evidence_world_state,
    snapshot_workspace,
    verify_execution,
    workspace_root,
)
class ApprovalWorkflow:
    def __init__(self, store=None, event_sink=None):
        self.requests: dict[str, ApprovalRequest]={}
        self._store=store
        # Optional callable(event_type: str, request: ApprovalRequest) invoked on
        # create/decide/expire so the node can fan events out to live clients.
        self._event_sink=event_sink
        # Load persisted approvals on init
        if store is not None:
            for req in store.all("approvals", ApprovalRequest):
                self.requests[req.id]=req

    def _emit(self, event_type:str, req:ApprovalRequest):
        if self._event_sink is not None:
            try: self._event_sink(event_type, req)
            except Exception: pass  # events are best-effort; never break the workflow

    def _persist(self, req: ApprovalRequest):
        if self._store is not None:
            self._store.put("approvals", req.id, req)

    def create(self, action: AgentAction, reason: str):
        req=ApprovalRequest(action=action, reason=reason, action_preview=action.description, data_used_preview=action.data_used, model_used_preview=action.model_used, destination_preview=action.destination, risk_label=action.risk, requires_double_confirmation=action.destructive)
        self._persist(req)
        self.requests[req.id]=req
        self._emit("approval.created", req)
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
            self._emit("approval.updated", req)
            raise ValueError("approval is expired")
        req.status=ApprovalStatus.APPROVED if approve else ApprovalStatus.DENIED
        req.deny_reason=deny_reason
        req.decided_at=now()
        self._persist(req)
        self.requests[approval_id]=req
        self._emit("approval.updated", req)
        return req

    def attach_execution(self, approval_id: str, execution_id: str, verification_status: str):
        """Link a finished execution to its approval card and broadcast the verdict.

        Raises KeyError for an unknown approval id. Emits approval.updated so live
        clients (SSE) refresh the card with the verification status.
        """
        current = self.requests.get(approval_id)
        if current is None:
            raise KeyError(f"unknown approval: {approval_id}")
        req = current.model_copy(deep=True)
        req.execution_id = execution_id
        req.verification_status = verification_status
        self._persist(req)
        self.requests[approval_id] = req
        self._emit("approval.updated", req)
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
                self._emit("approval.updated", req)
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
    def __init__(self, profile:UserProfile|None=None, approval_store=None, event_sink=None, execution_store=None):
        self.profile=profile or UserProfile()
        self.policy=PolicyEngine()
        self.approvals=ApprovalWorkflow(store=approval_store, event_sink=event_sink)
        self.tools=ToolRegistry()
        self.audit=[]
        # Execution records: every execute() call lands here and, when a store
        # is provided, in the encrypted runtime DB under "executions".
        self.execution_store=execution_store
        self.executions: dict[str, ExecutionRecord]={}
        if execution_store is not None:
            for rec in execution_store.all("executions", ExecutionRecord):
                self.executions[rec.id]=rec
    def propose(self,prompt:str, data_used:list[str]|None=None, model_used:str|None=None):
        plan=AgentPlanner().plan(prompt)
        for a in plan.actions:
            a.data_used=data_used or []; a.model_used=model_used; a.risk=self.policy.classify_action(a); a.requires_approval=self.policy.requires_approval(a,self.profile)
            if a.requires_approval: self.approvals.create(a,"Policy requires explicit user decision before execution.")
        if any(a.risk==RiskClass.BLOCKED for a in plan.actions): self.audit.append(AuditEvent(actor="agent_core", event_type="suspicious_request_blocked", proposed_action=prompt, status="blocked"))
        return plan
    def _persist_execution(self, rec: ExecutionRecord):
        self.executions[rec.id]=rec
        if self.execution_store is not None:
            self.execution_store.put("executions", rec.id, rec)

    def execute(self, action:AgentAction, approved:bool=False, double_confirmed:bool=False, approval_id:str|None=None):
        rec=ExecutionRecord(intent=action.description, action=action, approval_id=approval_id,
                            approved=approved, double_confirmed=double_confirmed)
        ok,reason=self.policy.can_execute(action,self.profile,approved,double_confirmed)
        rec.policy_allowed=ok; rec.policy_reason=reason
        rec.evidence.append(evidence_policy(ok, reason))
        self.audit.append(AuditEvent(actor="agent_core", event_type="execute", data_used=action.data_used, model_used=action.model_used, proposed_action=action.description, permission_checked=reason, status="allowed" if ok else "blocked"))
        if not ok:
            rec.verification=VerificationStatus.FAILED
            rec.verification_reason=f"blocked by policy: {reason}"
            rec.finished_at=now()
            self._persist_execution(rec)
            return {"ok":False,"reason":reason,"verification":rec.verification.value,
                    "verification_reason":rec.verification_reason,"execution_id":rec.id}
        root=workspace_root()
        before=snapshot_workspace(root)
        tool_result=None; tool_error=None
        try:
            raw=self.tools.execute(action)
            tool_result=raw if isinstance(raw, dict) else None
            if raw is not None and not isinstance(raw, dict):
                tool_error=f"tool returned non-dict result of type {type(raw).__name__}"
        except Exception as e:
            tool_error=f"{type(e).__name__}: {e}"
        after=snapshot_workspace(root)
        diff=diff_snapshots(before, after)
        rec.tool_result=tool_result; rec.tool_error=tool_error
        if tool_error:
            rec.evidence.append(evidence_error(tool_error))
        if tool_result is not None:
            rec.evidence.append(evidence_tool_output(tool_result))
        rec.world_state=diff
        rec.evidence.append(evidence_world_state(diff))
        status,vreason=verify_execution(action, ok, reason, tool_result, tool_error, diff, root)
        rec.verification=status; rec.verification_reason=vreason
        rec.finished_at=now()
        self._persist_execution(rec)
        return {"ok":True,"result":tool_result,"verification":status.value,
                "verification_reason":vreason,"execution_id":rec.id}
