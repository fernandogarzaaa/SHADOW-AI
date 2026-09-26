from .models import *
from .policy import PolicyEngine, PolicyOutcome
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
    def __init__(self, store=None, event_sink=None, audit_chain=None):
        self.requests: dict[str, ApprovalRequest]={}
        self._store=store
        # Optional callable(event_type: str, request: ApprovalRequest) invoked on
        # create/decide/expire so the node can fan events out to live clients.
        self._event_sink=event_sink
        self._audit=audit_chain
        # Load persisted approvals on init
        if store is not None:
            for req in store.all("approvals", ApprovalRequest):
                self.requests[req.id]=req

    def _emit(self, event_type:str, req:ApprovalRequest):
        if self._event_sink is not None:
            try: self._event_sink(event_type, req)
            except Exception: pass  # events are best-effort; never break the workflow

    def _record(self, event_type:str, payload:dict):
        if self._audit is not None:
            try: self._audit.record("sentinel_approvals", event_type, payload)
            except Exception: pass  # auditing must never break approvals

    def _persist(self, req: ApprovalRequest):
        if self._store is not None:
            self._store.put("approvals", req.id, req)

    def create(self, action: AgentAction, reason: str):
        req=ApprovalRequest(action=action, reason=reason, action_preview=action.description, data_used_preview=action.data_used, model_used_preview=action.model_used, destination_preview=action.destination, risk_label=action.risk, requires_double_confirmation=action.destructive)
        self._persist(req)
        self.requests[req.id]=req
        self._emit("approval.created", req)
        self._record("approval.created", {"approval_id": req.id, "tool_name": action.tool_name, "risk": action.risk.value, "reason": reason})
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
            self._record("approval.expired", {"approval_id": approval_id})
            raise ValueError("approval is expired")
        req.status=ApprovalStatus.APPROVED if approve else ApprovalStatus.DENIED
        req.deny_reason=deny_reason
        req.decided_at=now()
        self._persist(req)
        self.requests[approval_id]=req
        self._emit("approval.updated", req)
        self._record("approval.decided", {"approval_id": approval_id, "decision": req.status.value, "deny_reason": deny_reason})
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
        self._record("approval.execution_attached", {"approval_id": approval_id, "execution_id": execution_id, "verification_status": verification_status})
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
                self._record("approval.expired", {"approval_id": rid})
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
    def __init__(self, profile:UserProfile|None=None, approval_store=None, event_sink=None, execution_store=None,
                 audit_chain=None, vault=None, policy=None, policy_file=None):
        self.profile=profile or UserProfile()
        # The single policy authority: every action decision flows through it.
        self.policy=PolicyEngine(policy=policy, policy_file=policy_file)
        self.audit_chain=audit_chain
        self.vault=vault
        self.approvals=ApprovalWorkflow(store=approval_store, event_sink=event_sink, audit_chain=audit_chain)
        self.tools=ToolRegistry()
        self.audit=[]
        self._audit_cursor=0
        # Execution records: every execute() call lands here and, when a store
        # is provided, in the encrypted runtime DB under "executions".
        self.execution_store=execution_store
        self.executions: dict[str, ExecutionRecord]={}
        if execution_store is not None:
            for rec in execution_store.all("executions", ExecutionRecord):
                self.executions[rec.id]=rec

    def _record(self, event_type:str, payload:dict):
        if self.audit_chain is not None:
            try: self.audit_chain.record("sentinel_policy", event_type, payload)
            except Exception: pass  # auditing must never break execution

    def drain_audit(self)->list:
        """Return legacy AuditEvents appended since the last drain.

        Fixes double-reporting: callers that mirror core.audit into a
        persistent list must drain instead of re-extending the whole list.
        """
        out=self.audit[self._audit_cursor:]
        self._audit_cursor=len(self.audit)
        return out

    def _scrub(self, obj):
        if self.vault is None: return obj
        try: return self.vault.scrub_obj(obj)
        except Exception: return obj

    def propose(self,prompt:str, data_used:list[str]|None=None, model_used:str|None=None):
        plan=AgentPlanner().plan(prompt)
        for a in plan.actions:
            a.data_used=data_used or []; a.model_used=model_used; a.risk=self.policy.classify_action(a); a.requires_approval=self.policy.requires_approval(a,self.profile)
            if a.requires_approval: self.approvals.create(a,"Policy requires explicit user decision before execution.")
        if any(a.risk==RiskClass.BLOCKED for a in plan.actions):
            self.audit.append(AuditEvent(actor="agent_core", event_type="suspicious_request_blocked", proposed_action=prompt, status="blocked"))
            self._record("policy.decision", {"tool_name": "leak_secret", "outcome": PolicyOutcome.DENY.value, "rule_id": "blocked_tool", "reason": "Suspicious request blocked at plan time."})
        return plan
    def _persist_execution(self, rec: ExecutionRecord):
        self.executions[rec.id]=rec
        if self.execution_store is not None:
            self.execution_store.put("executions", rec.id, rec)

    def execute(self, action:AgentAction, approved:bool=False, double_confirmed:bool=False, approval_id:str|None=None):
        rec=ExecutionRecord(intent=action.description, action=action, approval_id=approval_id,
                            approved=approved, double_confirmed=double_confirmed)
        decision=self.policy.decide(action,self.profile,approved,double_confirmed)
        ok=decision.outcome==PolicyOutcome.ALLOW
        reason=decision.reason
        rec.policy_allowed=ok; rec.policy_reason=reason
        rec.evidence.append(evidence_policy(ok, f"[{decision.rule_id}] {reason}"))
        self.audit.append(AuditEvent(actor="agent_core", event_type="execute", data_used=action.data_used, model_used=action.model_used, proposed_action=action.description, permission_checked=reason, status="allowed" if ok else "blocked"))
        self._record("policy.decision", {"action_id": action.id, "tool_name": action.tool_name, "outcome": decision.outcome.value, "rule_id": decision.rule_id, "risk": decision.risk.value, "reason": reason, "approval_id": approval_id})
        if not ok:
            rec.verification=VerificationStatus.FAILED
            rec.verification_reason=f"blocked by policy: {reason}"
            rec.finished_at=now()
            self._persist_execution(rec)
            self._record("execution.verdict", {"execution_id": rec.id, "verification": rec.verification.value, "reason": rec.verification_reason})
            return {"ok":False,"reason":reason,"verification":rec.verification.value,
                    "verification_reason":rec.verification_reason,"execution_id":rec.id}
        # Just-in-time credential injection at the execution boundary: resolve
        # surrogates into a copy of the params. The stored record keeps the
        # surrogates; only the live tool call sees real values.
        call_params=dict(action.params)
        if self.vault is not None:
            call_params,resolved=self.vault.inject(action.params)
            action_for_tool=action.model_copy(update={"params": call_params})
        else:
            action_for_tool=action
            resolved=[]
        root=workspace_root()
        before=snapshot_workspace(root)
        tool_result=None; tool_error=None
        try:
            raw=self.tools.execute(action_for_tool)
            tool_result=raw if isinstance(raw, dict) else None
            if raw is not None and not isinstance(raw, dict):
                tool_error=f"tool returned non-dict result of type {type(raw).__name__}"
        except Exception as e:
            tool_error=f"{type(e).__name__}: {e}"
        after=snapshot_workspace(root)
        diff=diff_snapshots(before, after)
        rec.tool_result=self._scrub(tool_result); rec.tool_error=tool_error
        if tool_error:
            rec.evidence.append(evidence_error(tool_error))
        if tool_result is not None:
            rec.evidence.append(evidence_tool_output(self._scrub(tool_result)))
        rec.world_state=diff
        rec.evidence.append(evidence_world_state(diff))
        status,vreason=verify_execution(action, ok, reason, tool_result, tool_error, diff, root)
        rec.verification=status; rec.verification_reason=vreason
        rec.finished_at=now()
        self._persist_execution(rec)
        self._record("execution.verdict", {"execution_id": rec.id, "tool_name": action.tool_name, "verification": status.value, "reason": vreason, "approval_id": approval_id, "credentials_resolved": resolved})
        return {"ok":True,"result":rec.tool_result,"verification":status.value,
                "verification_reason":vreason,"execution_id":rec.id}
