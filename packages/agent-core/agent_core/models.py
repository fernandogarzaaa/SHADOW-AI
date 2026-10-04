from __future__ import annotations
from datetime import datetime, timezone, timedelta
from enum import Enum
from pydantic import BaseModel, Field
from typing import Any
from uuid import uuid4

def now(): return datetime.now(timezone.utc)
def new_id(prefix: str): return f"{prefix}_{uuid4().hex}"

class AutonomyMode(str, Enum):
    OFF="off"; SUGGEST_ONLY="suggest_only"; DRAFT_ONLY="draft_only"; EXECUTE_WITH_APPROVAL="execute_with_approval"; TRUSTED_WORKFLOW="trusted_workflow"; FULL_AUTONOMOUS="full_autonomous_disabled"
class RiskClass(str, Enum): LOW="low"; MEDIUM="medium"; HIGH="high"; BLOCKED="blocked"
class ApprovalStatus(str, Enum): PENDING="pending"; APPROVED="approved"; DENIED="denied"; EXPIRED="expired"; CONSUMED="consumed"
class ApprovalKind(str, Enum): ONE_TIME="one_time"; TRUSTED_WORKFLOW="trusted_workflow"
class ModelAccessLevel(str, Enum):
    """Cloud fallback policy for a consent grant.

    local_only: data from this source never goes to a cloud model.
    cloud_allowed: cloud escalation is allowed with an explicit approval
        or in trusted mode.
    ask_each_time: cloud escalation requires an explicit approval every
        time; trusted mode does not waive it.
    """
    LOCAL_ONLY="local_only"; CLOUD_ALLOWED="cloud_allowed"; ASK_EACH_TIME="ask_each_time"
class UserProfile(BaseModel):
    id: str = Field(default_factory=lambda:new_id("usr")); display_name: str="Local User"; privacy_mode: str="strict_local"; autonomy_mode: AutonomyMode=AutonomyMode.SUGGEST_ONLY; emergency_paused: bool=False
class ConsentGrant(BaseModel):
    id: str = Field(default_factory=lambda:new_id("cns")); data_source: str; scope: str; purpose: str; retention_days: int=30; model_access_level: ModelAccessLevel=ModelAccessLevel.LOCAL_ONLY; approved_at: datetime=Field(default_factory=now); revoked_at: datetime|None=None; last_used_at: datetime|None=None
    def is_active(self) -> bool: return self.revoked_at is None
class AgentAction(BaseModel):
    id: str = Field(default_factory=lambda:new_id("act")); tool_name: str; description: str; params: dict[str, Any]={}; risk: RiskClass=RiskClass.LOW; requires_approval: bool=True; destructive: bool=False; destination: str|None=None; data_used: list[str]=[]; model_used: str|None=None
class AgentPlan(BaseModel):
    id: str = Field(default_factory=lambda:new_id("plan")); user_intent: str; actions: list[AgentAction]; requires_cloud: bool=False; rationale: str=""; untrusted_context_used: bool=False
class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda:new_id("tsk")); prompt: str; plan: AgentPlan|None=None; status: str="created"; created_at: datetime=Field(default_factory=now)
class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda:new_id("apr")); action: AgentAction; reason: str; action_preview: str; data_used_preview: list[str]=[]; model_used_preview: str|None=None; destination_preview: str|None=None; risk_label: RiskClass=RiskClass.LOW; kind: ApprovalKind=ApprovalKind.ONE_TIME; requires_double_confirmation: bool=False; status: ApprovalStatus=ApprovalStatus.PENDING; deny_reason: str|None=None; created_at: datetime=Field(default_factory=now); decided_at: datetime|None=None; expires_at: datetime=Field(default_factory=lambda: now()+timedelta(minutes=15))
    # HITL run linkage (OpenDots backlog #1): the idempotency receipt key
    # (thread_id, tool_call_id). Retrying the same tool call returns the
    # existing pending approval instead of minting a duplicate.
    thread_id: str|None=None; tool_call_id: str|None=None
    # Verification linkage: once the approved action runs, the approval card
    # carries the execution id and its VERIFIED / FAILED / UNCERTAIN / CONFLICTING
    # verdict so clients can show proof, not just a claim of completion.
    execution_id: str|None=None; verification_status: str|None=None
    # One-shot semantics: a ONE_TIME approval is atomically transitioned to
    # CONSUMED when its execution is claimed, so it cannot be replayed.
    consumed_at: datetime|None=None
    # Authorization binding: sha256 over the canonical authorization envelope
    # (tool, params, destination, data/model scope, risk, destructive, policy
    # version). The presented action must reproduce this hash at claim time.
    binding_hash: str|None=None
    @property
    def card(self) -> dict:
        """Decision-card payload for approval UIs (OpenDots PageReviewCard
        analog, adapted: SHADOW adds the risk class OpenDots lacks)."""
        title = (self.action.description or self.action.tool_name).strip()
        if len(title) > 80:
            title = title[:77] + "..."
        return {
            "approval_id": self.id,
            "title": title,
            "tool_name": self.action.tool_name,
            "preview": self.action_preview,
            "risk": self.risk_label.value,
            "destination": self.destination_preview,
            "data_used": self.data_used_preview,
            "requires_double_confirmation": self.requires_double_confirmation,
            "thread_id": self.thread_id,
            "tool_call_id": self.tool_call_id,
            "status": self.status.value,
            "deny_reason": self.deny_reason,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "footnote": "Nothing runs until you approve.",
        }
class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda:new_id("aud")); actor: str; event_type: str; data_used: list[str]=[]; model_used: str|None=None; permission_checked: str|None=None; proposed_action: str|None=None; status: str="recorded"; result: str|None=None; timestamp: datetime=Field(default_factory=now); metadata: dict[str, Any]={}
class Device(BaseModel):
    id: str = Field(default_factory=lambda:new_id("dev")); name: str; public_key: str; fingerprint: str; trusted: bool=False; revoked: bool=False; session_expires_at: datetime=Field(default_factory=lambda: now()+timedelta(days=30)); registered_at: datetime=Field(default_factory=now)
    # Owner devices may manage other devices (revoke, approve pairings,
    # initiate enrollment). The first-ever (bootstrap) device becomes owner.
    is_owner: bool=False
    # How this device's request-signing secret is obtained: "stored" (a
    # random secret persisted in the encrypted runtime DB, pre-HMAC
    # devices) or "hmac-vN" (derived at verify time from the node master
    # secret via device_credentials; nothing stored per device).
    credential_scheme: str="stored"
class CloudEscalationRequest(BaseModel):
    id: str = Field(default_factory=lambda:new_id("clr")); purpose: str; redacted_context: str; model: str; approved: bool=False
