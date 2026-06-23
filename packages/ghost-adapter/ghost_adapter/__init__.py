from pydantic import BaseModel
class GhostTaskIR(BaseModel): objective:str; steps:list[dict]; safety_profile:str="approval_gated"
class GhostAdapter:
    def to_ir(self,plan): return GhostTaskIR(objective=plan.user_intent, steps=[{"tool":a.tool_name,"risk":a.risk,"description":a.description} for a in plan.actions])
    def execute(self,ir:GhostTaskIR,approved:bool=False):
        if not approved: return {"status":"approval_required","ir":ir.model_dump()}
        return {"status":"queued","backend":"ghost-chimera-adapter","ir":ir.model_dump()}
class DesktopActionAdapter: pass
class ExecutionPolicyAdapter: pass
class SafetyProfileAdapter: pass
class TelemetryAdapter: pass
