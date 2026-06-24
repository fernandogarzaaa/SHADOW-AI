from fastapi import FastAPI, HTTPException, WebSocket, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent_core import *
from memory_engine import *
from axiom_adapter import AxiomAdapter
from ghost_adapter import GhostAdapter, LocalActionExecutor
from .connectors import read_local_document
from .model_providers import ModelProviderConfig, LocalMockModel
from .crypto_config import load_fernet_key
from .providers import build_frontier, CATALOG
from .hybrid import HybridRouter
from . import provider_auth
import tempfile, hashlib, uuid, os, time
APP_VERSION="1.0.0-rc"
app=FastAPI(title="Shadow Node", version=APP_VERSION)
# CORS: localhost by default; add deployed PWA/app origins via SHADOW_CORS_ORIGINS
# (comma-separated). Use "*" only for fully trusted/private deployments.
_DEFAULT_CORS=["http://localhost","http://127.0.0.1","http://localhost:8787","http://127.0.0.1:8787","http://localhost:8081","http://localhost:19006"]
_EXTRA_CORS=[o.strip() for o in os.getenv("SHADOW_CORS_ORIGINS","").split(",") if o.strip()]
CORS_ORIGINS=_EXTRA_CORS if "*" in _EXTRA_CORS else (_DEFAULT_CORS+_EXTRA_CORS)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
def _build_memory_store():
    # Persistent, stable-key store when SHADOW_MEMORY_DB is set (production);
    # ephemeral temp store otherwise (tests/dev) so runs stay isolated.
    db=os.getenv("SHADOW_MEMORY_DB")
    if db:
        key=load_fernet_key("SHADOW_MEMORY_KEY","SHADOW_MEMORY_KEY_FILE","data/keys/memory.key")
        os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
        return EncryptedMemoryStore(path=db, key=key)
    return EncryptedMemoryStore(path=tempfile.gettempdir()+f"/shadow_memory_beta_{uuid.uuid4().hex}.db")
profile=UserProfile(); core=AgentCore(profile); store=_build_memory_store(); memory=MemoryEngine(store); axiom=AxiomAdapter(); ghost=GhostAdapter(); model_config=ModelProviderConfig(); model=LocalMockModel(); pairing={}
# Persistent encrypted runtime state when SHADOW_RUNTIME_DB is set; in-memory otherwise.
_runtime_db=os.getenv("SHADOW_RUNTIME_DB")
if _runtime_db:
    from .runtime_store import build_runtime
    _runtime_store, audit, consents, sessions = build_runtime(_runtime_db)
else:
    audit:list[AuditEvent]=[]; sessions=DeviceSessionStore(); consents:list[ConsentGrant]=[]
# Register real, sandboxed action handlers so approved /agent/execute calls run for real.
action_executor=LocalActionExecutor()
for _tool in action_executor.names(): core.tools.register(_tool, (lambda t: (lambda params: action_executor.run(t, params)))(_tool))
# Hybrid local+frontier router and provider credential store.
hybrid=HybridRouter(model, axiom)
credentials=provider_auth.CredentialStore()
AUTH_REQUIRED=os.getenv("SHADOW_AUTH_REQUIRED", "false").lower()=="true"
GROUNDING_VERIFY=os.getenv("SHADOW_GROUNDING_VERIFY", "true").lower()=="true"
RATE_LIMIT_RPM=int(os.getenv("SHADOW_RATE_LIMIT_RPM", "0"))  # 0 disables
from .obs import RateLimiter, configure_logging, client_key
log=configure_logging()
rate_limiter=RateLimiter(RATE_LIMIT_RPM) if RATE_LIMIT_RPM>0 else None
class IngestRequest(BaseModel): text:str; source_kind:str="manual"; source_title:str="Manual Import"; consent_grant_id:str|None=None; sensitive:bool|None=None; do_not_send_to_cloud:bool|None=None
class FileIngestRequest(BaseModel): path:str; consent_grant_id:str; source_title:str|None=None
class AskRequest(BaseModel): prompt:str; allow_cloud:bool=False; cloud_approval:bool=False
class PairConfirm(BaseModel): pairing_id:str; device_name:str; public_key:str
class DenyRequest(BaseModel): reason:str
class ExecuteRequest(BaseModel): action:AgentAction; approved:bool=False; double_confirmed:bool=False
class ApprovalCreateRequest(BaseModel): action:AgentAction; reason:str="User requested approval"
class EmergencyPauseRequest(BaseModel): paused:bool; reason:str|None=None
class ConsentRequest(BaseModel): data_source:str; scope:str; purpose:str; retention_days:int=30; model_access_level:str="local_only"
class ProviderConnectRequest(BaseModel): api_key:str
class OAuthExchangeRequest(BaseModel): code:str; code_verifier:str; redirect_uri:str
@app.exception_handler(HTTPException)
async def http_exception_handler(request:Request, exc:HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error":{"code":str(exc.detail),"message":str(exc.detail),"path":request.url.path}})
@app.middleware("http")
async def observability_middleware(request:Request, call_next):
    start=time.perf_counter()
    if rate_limiter is not None and request.url.path not in {"/health","/ready"}:
        if not rate_limiter.allow(client_key(request)):
            log.warning("rate_limited", extra={"path":request.url.path,"client":client_key(request),"status":429})
            return JSONResponse(status_code=429, content={"error":{"code":"rate_limited","message":"too many requests"}})
    response=await call_next(request)
    log.info("request", extra={"method":request.method,"path":request.url.path,"status":response.status_code,"ms":round((time.perf_counter()-start)*1000,1),"client":client_key(request)})
    return response
@app.middleware("http")
async def auth_middleware(request:Request, call_next):
    exempt=request.url.path in {"/","/health","/ready","/pair/start","/pair/confirm"} or request.url.path.startswith("/docs") or request.url.path.startswith("/openapi")
    if AUTH_REQUIRED and not exempt:
        body=(await request.body()).decode()
        ok,reason=sessions.verify(request.headers.get("x-shadow-device-id"),request.headers.get("x-shadow-signature"),request.headers.get("x-shadow-nonce"),request.headers.get("x-shadow-timestamp"),request.method,request.url.path,body)
        if not ok: return JSONResponse(status_code=401, content={"detail":reason})
    return await call_next(request)
WEB_INDEX=os.path.join(os.path.dirname(__file__),"web","index.html")
@app.get("/", include_in_schema=False)
def dashboard(): return FileResponse(WEB_INDEX)
@app.get("/health")
def health(): return {"status":"ok","version":APP_VERSION,"local_first":True,"emergency_paused":profile.emergency_paused,"auth_required":AUTH_REQUIRED}
@app.get("/ready")
def ready():
    # Readiness probe: the node can serve memory + routing.
    try:
        memory.search("ready", 1); ok=True
    except Exception:
        ok=False
    status="ready" if ok else "degraded"
    return JSONResponse(status_code=200 if ok else 503, content={"status":status,"version":APP_VERSION,"auth_required":AUTH_REQUIRED,"rate_limit_rpm":RATE_LIMIT_RPM,"grounding_verify":GROUNDING_VERIFY,"providers_ready":model_config.cloud_model_ready()})
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
@app.get("/memory")
def list_memory(include_sensitive:bool=False): return memory.export(include_sensitive)
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
    results=memory.search(req.prompt,5,include_sensitive=False); raw_context="\n".join(mark_untrusted(r.item.text) for r in results); plan=core.propose(req.prompt, data_used=[r.attribution for r in results], model_used="local_mock")
    if req.allow_cloud and not core.policy.cloud_allowed(consents, req.cloud_approval): audit.append(AuditEvent(actor="agent",event_type="cloud_escalation_denied",status="blocked")); raise HTTPException(403,"cloud escalation requires active grant and explicit approval")
    # Hybrid routing: build a frontier provider only when cloud is approved AND a credential resolves; else fully local.
    frontier=None
    if req.allow_cloud:
        cred=credentials.resolve(model_config.provider)
        if cred is not None:
            cred={**cred,"endpoint":model_config.endpoint}
            frontier=build_frontier(model_config.provider, cred, model_config.model_name)
    try:
        out=hybrid.run(req.prompt, raw_context, frontier=frontier, verify=GROUNDING_VERIFY)
    except Exception as e:
        audit.append(AuditEvent(actor="agent",event_type="cloud_model_error",model_used=model_config.provider,status="fallback_local",result=str(e)[:200]))
        out=hybrid.run(req.prompt, raw_context, frontier=None)
    cloud_used=out["route"]=="frontier"
    audit.append(AuditEvent(actor="agent",event_type="agent_ask",data_used=[r.attribution for r in results],model_used=out["provider"],status="answered",metadata={"route":out["route"],"tokens_saved":out["savings"]["tokens_saved_estimate"],"grounding":out["grounding"]}))
    return {"answer":out["answer"],"sources":[r.model_dump() for r in results],"why":[r.explanation for r in results],"model_used":out["provider"],"cloud_allowed":cloud_used,"untrusted_context":True,"context_package":out["context_package"],"plan":plan,"route":out["route"],"routing_reason":out["reason"],"grounding":out["grounding"],"regrounded":out["regrounded"],"savings":out["savings"]}
@app.post("/agent/plan")
def plan(req:AskRequest): return core.propose(req.prompt)
@app.post("/agent/execute")
def execute(req:ExecuteRequest):
    if req.action.tool_name=="ghost_handoff": return ghost.execute(ghost.to_ir(AgentPlan(user_intent=req.action.description, actions=[req.action])), approved=req.approved)
    res=core.execute(req.action,req.approved,req.double_confirmed); audit.extend(core.audit); return res
@app.post("/approvals")
def create_approval(req:ApprovalCreateRequest):
    approval=core.approvals.create(req.action, req.reason); audit.append(AuditEvent(actor="user", event_type="approval_created", proposed_action=req.action.description, status="pending", metadata={"approval_id":approval.id})); return approval
@app.get("/approvals")
def approvals(): return list(core.approvals.requests.values())
@app.post("/approvals/{id}/approve")
def approve(id:str):
    req=core.approvals.decide(id,True); audit.append(AuditEvent(actor="user", event_type="approval_approved", proposed_action=req.action.description, status="approved", metadata={"approval_id":id})); return req
@app.post("/approvals/{id}/deny")
def deny(id:str, req:DenyRequest):
    out=core.approvals.decide(id,False,req.reason); audit.append(AuditEvent(actor="user", event_type="approval_denied", proposed_action=out.action.description, status="denied", result=req.reason, metadata={"approval_id":id})); return out
@app.get("/emergency_pause")
def get_emergency_pause(): return {"paused":profile.emergency_paused}
@app.post("/emergency_pause")
def set_emergency_pause(req:EmergencyPauseRequest):
    profile.emergency_paused=req.paused; audit.append(AuditEvent(actor="user", event_type="emergency_pause", status="paused" if req.paused else "resumed", result=req.reason)); return {"paused":profile.emergency_paused}
@app.get("/audit")
def get_audit(): return audit + core.audit + sessions.audit
@app.get("/model/providers")
def model_providers(): return model_config.safe_summary()
@app.get("/providers")
def providers_status(): return {"active_provider":model_config.provider,"providers":credentials.status()}
@app.post("/providers/{name}/connect")
def provider_connect(name:str, req:ProviderConnectRequest):
    if name not in CATALOG: raise HTTPException(404,"unknown provider")
    if not req.api_key: raise HTTPException(400,"api_key required")
    credentials.set(name,{"type":"api_key","api_key":req.api_key,"source":"stored"}); audit.append(AuditEvent(actor="user",event_type="provider_connected",data_used=[name],status="connected")); return {"connected":True,"provider":name}
@app.delete("/providers/{name}")
def provider_disconnect(name:str):
    credentials.delete(name); audit.append(AuditEvent(actor="user",event_type="provider_disconnected",data_used=[name],status="disconnected")); return {"connected":False,"provider":name}
@app.get("/providers/{name}/oauth/start")
def provider_oauth_start(name:str, redirect_uri:str):
    try: return provider_auth.start_oauth(name, redirect_uri)
    except ValueError as e: raise HTTPException(400,str(e))
@app.post("/providers/{name}/oauth/exchange")
def provider_oauth_exchange(name:str, req:OAuthExchangeRequest):
    try: cred=provider_auth.exchange_code(name, req.code, req.code_verifier, req.redirect_uri)
    except ValueError as e: raise HTTPException(400,str(e))
    except Exception as e: raise HTTPException(502,f"token exchange failed: {e}")
    credentials.set(name,cred); audit.append(AuditEvent(actor="user",event_type="provider_oauth_connected",data_used=[name],status="connected")); return {"connected":True,"provider":name,"type":"oauth"}
@app.get("/tools")
def tools(): return {"tools":action_executor.names(),"ghost_mode":ghost.mode,"workspace":os.getenv("SHADOW_WORKSPACE_DIR","data/workspace")}
@app.websocket("/ws/tasks")
async def ws_tasks(ws:WebSocket):
    await ws.accept(); await ws.send_json({"type":"hello","node":"shadow-node","version":APP_VERSION})
    while True:
        data=await ws.receive_json(); await ws.send_json({"type":"ack","received":data})
