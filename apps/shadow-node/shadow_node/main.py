from fastapi import FastAPI, HTTPException, WebSocket, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from agent_core import *
from memory_engine import *
from axiom_adapter import AxiomAdapter
from ghost_adapter import GhostAdapter
from .connectors import read_local_document
from .model_providers import ModelProviderConfig, LocalMockModel
import tempfile, hashlib, uuid
app=FastAPI(title="Shadow Node", version="0.3.0-beta")
profile=UserProfile(); core=AgentCore(profile); store=EncryptedMemoryStore(path=tempfile.gettempdir()+f"/shadow_memory_beta_{uuid.uuid4().hex}.db"); memory=MemoryEngine(store); axiom=AxiomAdapter(); ghost=GhostAdapter(); model_config=ModelProviderConfig(); model=LocalMockModel(); audit:list[AuditEvent]=[]; sessions=DeviceSessionStore(); pairing={}; consents:list[ConsentGrant]=[]
AUTH_REQUIRED=False
class IngestRequest(BaseModel): text:str; source_kind:str="manual"; source_title:str="Manual Import"; consent_grant_id:str|None=None; sensitive:bool|None=None; do_not_send_to_cloud:bool|None=None
class FileIngestRequest(BaseModel): path:str; consent_grant_id:str; source_title:str|None=None
class AskRequest(BaseModel): prompt:str; allow_cloud:bool=False; cloud_approval:bool=False
class PairConfirm(BaseModel): pairing_id:str; device_name:str; public_key:str
class DenyRequest(BaseModel): reason:str
class ExecuteRequest(BaseModel): action:AgentAction; approved:bool=False; double_confirmed:bool=False
class ConsentRequest(BaseModel): data_source:str; scope:str; purpose:str; retention_days:int=30; model_access_level:str="local_only"
@app.middleware("http")
async def auth_middleware(request:Request, call_next):
    exempt=request.url.path in {"/health","/pair/start","/pair/confirm"} or request.url.path.startswith("/docs") or request.url.path.startswith("/openapi")
    if AUTH_REQUIRED and not exempt:
        body=(await request.body()).decode()
        ok,reason=sessions.verify(request.headers.get("x-shadow-device-id"),request.headers.get("x-shadow-signature"),request.headers.get("x-shadow-nonce"),request.headers.get("x-shadow-timestamp"),request.method,request.url.path,body)
        if not ok: return JSONResponse(status_code=401, content={"detail":reason})
    return await call_next(request)
@app.get("/health")
def health(): return {"status":"ok","version":"0.3.0-beta","local_first":True,"emergency_paused":profile.emergency_paused,"auth_required":AUTH_REQUIRED}
@app.post("/pair/start")
def pair_start():
    pid=new_id("pair"); pairing[pid]="pending"; return {"pairing_id":pid,"code":pid[-6:].upper(),"expires_in_seconds":300}
@app.post("/pair/confirm")
def pair_confirm(req:PairConfirm):
    if req.pairing_id not in pairing: raise HTTPException(404,"pairing not found")
    secret=hashlib.sha256((req.public_key+req.pairing_id).encode()).hexdigest(); dev=sessions.register(req.device_name, req.public_key, secret); audit.append(AuditEvent(actor="pairing",event_type="device_paired",status="trusted",metadata={"device_id":dev.id,"fingerprint":dev.fingerprint})); return {"device":dev,"shared_secret":secret}
@app.post("/devices/register")
def register(d:Device): sessions.devices[d.id]=d; return d
@app.post("/devices/{device_id}/revoke")
def revoke_device(device_id:str): sessions.revoke(device_id); return {"revoked":device_id}
@app.get("/devices")
def list_devices(): return list(sessions.devices.values())
@app.post("/consent")
def grant_consent(req:ConsentRequest):
    c=ConsentGrant(**req.model_dump()); consents.append(c); return c
@app.post("/memory/ingest")
def ingest(req:IngestRequest):
    if req.consent_grant_id and not any(c.id==req.consent_grant_id and c.is_active() for c in consents): raise HTTPException(403,"active consent grant required")
    src=MemorySource(kind=req.source_kind,title=req.source_title,consent_grant_id=req.consent_grant_id); items=memory.ingest(req.text,src,sensitive=req.sensitive,do_not_send_to_cloud=req.do_not_send_to_cloud); audit.append(AuditEvent(actor="user",event_type="memory_ingest",data_used=[src.title],status="stored",metadata={"source_id":src.id,"count":len(items)})); return {"source":src,"items":items}
@app.post("/memory/ingest_file")
def ingest_file(req:FileIngestRequest):
    if not any(c.id==req.consent_grant_id and c.is_active() for c in consents): raise HTTPException(403,"active consent grant required")
    text,kind=read_local_document(req.path); src=MemorySource(kind=f"file/{kind}",title=req.source_title or req.path,uri=req.path,consent_grant_id=req.consent_grant_id); items=memory.ingest(text,src); audit.append(AuditEvent(actor="connector:file",event_type="file_ingest",data_used=[req.path],status="stored",metadata={"source_id":src.id,"count":len(items)})); return {"source":src,"items":items}
@app.get("/memory/search")
def search(q:str, limit:int=5, include_sensitive:bool=True): return memory.search(q,limit,include_sensitive)
@app.delete("/memory/source/{source_id}")
def delete_source(source_id:str): memory.delete_by_source(source_id); audit.append(AuditEvent(actor="user",event_type="memory_source_deleted",status="revoked",metadata={"source_id":source_id})); return {"deleted_source":source_id}
@app.get("/memory/export")
def export_memory(include_sensitive:bool=False): return memory.export(include_sensitive)
@app.post("/agent/ask")
def ask(req:AskRequest):
    if is_suspicious_user_request(req.prompt):
        audit.append(AuditEvent(actor="user",event_type="suspicious_request_blocked",proposed_action=req.prompt,status="blocked")); raise HTTPException(403,"request blocked by prompt-injection/data-exfiltration policy")
    results=memory.search(req.prompt,5,include_sensitive=False); context="\n".join(mark_untrusted(r.item.text) for r in results); packaged=axiom.package_context(context); plan=core.propose(req.prompt, data_used=[r.attribution for r in results], model_used="local_mock")
    if req.allow_cloud and not core.policy.cloud_allowed(consents, req.cloud_approval): audit.append(AuditEvent(actor="agent",event_type="cloud_escalation_denied",status="blocked")); raise HTTPException(403,"cloud escalation requires active grant and explicit approval")
    return {"answer":model.complete(req.prompt,packaged["context"]),"sources":[r.model_dump() for r in results],"why":[r.explanation for r in results],"context_package":packaged,"plan":plan}
@app.post("/agent/plan")
def plan(req:AskRequest): return core.propose(req.prompt)
@app.post("/agent/execute")
def execute(req:ExecuteRequest):
    if req.action.tool_name=="ghost_handoff": return ghost.execute(ghost.to_ir(AgentPlan(user_intent=req.action.description, actions=[req.action])), approved=req.approved)
    res=core.execute(req.action,req.approved,req.double_confirmed); audit.extend(core.audit); return res
@app.get("/approvals")
def approvals(): return list(core.approvals.requests.values())
@app.post("/approvals/{id}/approve")
def approve(id:str): return core.approvals.decide(id,True)
@app.post("/approvals/{id}/deny")
def deny(id:str, req:DenyRequest): return core.approvals.decide(id,False,req.reason)
@app.get("/audit")
def get_audit(): return audit + core.audit + sessions.audit
@app.get("/model/providers")
def model_providers(): return model_config.safe_summary()
@app.websocket("/ws/tasks")
async def ws_tasks(ws:WebSocket):
    await ws.accept(); await ws.send_json({"type":"hello","node":"shadow-node","version":"0.3.0-beta"})
    while True:
        data=await ws.receive_json(); await ws.send_json({"type":"ack","received":data})
