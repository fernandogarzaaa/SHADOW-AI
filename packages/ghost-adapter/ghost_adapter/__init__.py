from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel
class GhostTaskIR(BaseModel):
    objective: str
    steps: list[dict]
    safety_profile: str = "approval_gated"
class GhostTelemetry(BaseModel):
    status: str; backend: str="mock-ghost"; started_at: str; finished_at: str; steps_executed: int; error: str|None=None
class GhostAdapter:
    def to_ir(self, plan): return GhostTaskIR(objective=plan.user_intent, steps=[{"tool":a.tool_name,"risk":str(a.risk),"description":a.description,"params":a.params} for a in plan.actions])
    def execute(self, ir: GhostTaskIR, approved: bool=False):
        start=datetime.now(timezone.utc).isoformat()
        if not approved: return {"status":"approval_required","ir":ir.model_dump(),"telemetry":GhostTelemetry(status="blocked",started_at=start,finished_at=start,steps_executed=0).model_dump()}
        blocked=[s for s in ir.steps if "blocked" in str(s.get("risk"))]
        end=datetime.now(timezone.utc).isoformat()
        if blocked: return {"status":"failed","error":"blocked action in IR","telemetry":GhostTelemetry(status="failed",started_at=start,finished_at=end,steps_executed=0,error="blocked action").model_dump()}
        return {"status":"completed","result":"Safe mock local task executed by Ghost adapter.","ir":ir.model_dump(),"telemetry":GhostTelemetry(status="completed",started_at=start,finished_at=end,steps_executed=len(ir.steps)).model_dump()}
class DesktopActionAdapter: pass
class ExecutionPolicyAdapter: pass
class SafetyProfileAdapter: pass
class TelemetryAdapter: pass
