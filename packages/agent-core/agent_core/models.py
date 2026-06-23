from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
from typing import Any
from uuid import uuid4

def now(): return datetime.now(timezone.utc)
def new_id(prefix: str): return f"{prefix}_{uuid4().hex}"

class AutonomyMode(str, Enum):
    OFF="off"; SUGGEST_ONLY="suggest_only"; DRAFT_ONLY="draft_only"; EXECUTE_WITH_APPROVAL="execute_with_approval"; TRUSTED_WORKFLOW="trusted_workflow"; FULL_AUTONOMOUS="full_autonomous_disabled"
class RiskClass(str, Enum):
    LOW="low"; MEDIUM="medium"; HIGH="high"; CRITICAL="critical"; BLOCKED="blocked"
class ApprovalStatus(str, Enum):
    PENDING="pending"; APPROVED="approved"; DENIED="denied"; EXPIRED="expired"
class UserProfile(BaseModel):
    id: str = Field(default_factory=lambda:new_id("usr")); display_name: str="Local User"; privacy_mode: str="strict_local"; autonomy_mode: AutonomyMode=AutonomyMode.SUGGEST_ONLY; emergency_paused: bool=False
class ConsentGrant(BaseModel):
    id: str = Field(default_factory=lambda:new_id("cns")); data_source: str; scope: str; purpose: str; retention_days: int=30; model_access_level: str="local_only"; approved_at: datetime=Field(default_factory=now); revoked_at: datetime|None=None; last_used_at: datetime|None=None
class AgentAction(BaseModel):
    id: str = Field(default_factory=lambda:new_id("act")); tool_name: str; description: str; params: dict[str, Any]={}; risk: RiskClass=RiskClass.LOW; requires_approval: bool=True
class AgentPlan(BaseModel):
    id: str = Field(default_factory=lambda:new_id("plan")); user_intent: str; actions: list[AgentAction]; requires_cloud: bool=False; rationale: str=""
class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda:new_id("tsk")); prompt: str; plan: AgentPlan|None=None; status: str="created"; created_at: datetime=Field(default_factory=now)
class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda:new_id("apr")); action: AgentAction; reason: str; status: ApprovalStatus=ApprovalStatus.PENDING; created_at: datetime=Field(default_factory=now); decided_at: datetime|None=None
class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda:new_id("aud")); actor: str; event_type: str; data_used: list[str]=[]; model_used: str|None=None; permission_checked: str|None=None; proposed_action: str|None=None; status: str="recorded"; result: str|None=None; timestamp: datetime=Field(default_factory=now)
class Device(BaseModel):
    id: str = Field(default_factory=lambda:new_id("dev")); name: str; public_key: str; trusted: bool=False; registered_at: datetime=Field(default_factory=now)
class CloudEscalationRequest(BaseModel):
    id: str = Field(default_factory=lambda:new_id("clr")); purpose: str; redacted_context: str; model: str; approved: bool=False
