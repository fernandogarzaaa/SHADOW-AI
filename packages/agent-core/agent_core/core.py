from .models import *
from .policy import PolicyEngine
class ApprovalWorkflow:
    def __init__(self): self.requests: dict[str, ApprovalRequest]={}
    def create(self, action: AgentAction, reason: str):
        req=ApprovalRequest(action=action, reason=reason); self.requests[req.id]=req; return req
    def decide(self, approval_id:str, approve:bool):
        req=self.requests[approval_id]; req.status=ApprovalStatus.APPROVED if approve else ApprovalStatus.DENIED; req.decided_at=now(); return req
class ToolRegistry:
    def __init__(self): self._tools={}
    def register(self,name,handler): self._tools[name]=handler
    def names(self): return sorted(self._tools)
    def execute(self, action:AgentAction):
        if action.tool_name not in self._tools: return {"status":"stubbed","message":"Tool interface registered later","action":action.model_dump()}
        return self._tools[action.tool_name](action.params)
class AgentPlanner:
    def plan(self, prompt:str)->AgentPlan:
        lowered=prompt.lower(); tool="answer_question"; desc=f"Answer user request: {prompt}"
        if any(w in lowered for w in ["send","email","message"]): tool="send_email"; desc="Draft/send communication only after explicit approval"
        elif any(w in lowered for w in ["delete","remove"]): tool="delete_file"; desc="Potential destructive local action"
        return AgentPlan(user_intent=prompt, actions=[AgentAction(tool_name=tool, description=desc)], rationale="MVP deterministic planner with policy gate.")
class AgentCore:
    def __init__(self, profile:UserProfile|None=None): self.profile=profile or UserProfile(); self.policy=PolicyEngine(); self.approvals=ApprovalWorkflow(); self.tools=ToolRegistry(); self.audit=[]
    def propose(self,prompt:str):
        plan=AgentPlanner().plan(prompt)
        for a in plan.actions:
            a.risk=self.policy.classify_action(a); a.requires_approval=self.policy.requires_approval(a,self.profile)
        return plan
    def execute(self, action:AgentAction, approved:bool=False):
        ok,reason=self.policy.can_execute(action,self.profile,approved)
        self.audit.append(AuditEvent(actor="agent_core", event_type="execute", proposed_action=action.description, permission_checked=reason, status="allowed" if ok else "blocked"))
        if not ok: return {"ok":False,"reason":reason}
        return {"ok":True,"result":self.tools.execute(action)}
