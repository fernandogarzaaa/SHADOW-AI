import os, time
from pydantic import BaseModel
class GhostTaskIR(BaseModel): objective:str; steps:list[dict]; safety_profile:str="approval_gated"; sandbox:str="local_user_boundary"; timeout_seconds:int=30
class GhostAdapter:
    def __init__(self, mode:str|None=None): self.mode=mode or os.getenv("GHOST_RUNTIME_MODE","mock")
    def to_ir(self,plan): return GhostTaskIR(objective=plan.user_intent, steps=[{"tool":a.tool_name,"risk":a.risk,"description":a.description} for a in plan.actions])
    def execute(self,ir:GhostTaskIR,approved:bool=False):
        if not approved: return {"status":"approval_required","ir":ir.model_dump(),"mode":self.mode}
        start=time.time()
        if self.mode=="mock": return {"status":"mock_executed","backend":"safe-local-mock","duration_ms":int((time.time()-start)*1000),"telemetry":{"steps":len(ir.steps)},"ir":ir.model_dump()}
        return {"status":"queued","backend":"ghost-local-adapter","duration_ms":int((time.time()-start)*1000),"telemetry":{"steps":len(ir.steps)},"ir":ir.model_dump()}
class DesktopActionAdapter: pass
class ExecutionPolicyAdapter: pass
class SafetyProfileAdapter: pass
class TelemetryAdapter: pass
