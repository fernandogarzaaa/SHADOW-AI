from __future__ import annotations
import os
from fastapi import FastAPI, HTTPException, WebSocket, Depends, Request
from pydantic import BaseModel
from agent_core import *
from memory_engine import *
from axiom_adapter import AxiomAdapter
from ghost_adapter import GhostAdapter
from .stores import DeviceStore, ApprovalStore, AuditStore, ConsentStore, TaskStore
from .pairing import PairingService
from .connectors import ConnectorRegistry
from .model_providers import ModelProviderRegistry, ModelRequest
from .auth import SignedRequestVerifier

DB=os.getenv("SHADOW_RUNTIME_DB","data/shadow_runtime.db")
MEMDB=os.getenv("SHADOW_MEMORY_DB","data/shadow_memory.db")
app=FastAPI(title="Shadow Node", version="1.0.0-rc1")
profile=UserProfile(); device_store=DeviceStore(DB); approval_store=ApprovalStore(DB); audit_store=AuditStore(DB); consent_store=ConsentStore(DB); task_store=TaskStore(DB)
core=AgentCore(profile); store=EncryptedMemoryStore(path=MEMDB); memory=MemoryEngine(store); axiom=AxiomAdapter(); ghost=GhostAdapter(); pairing_service=PairingService(device_store); connectors=ConnectorRegistry(); models=ModelProviderRegistry(); auth_verifier=SignedRequestVerifier(device_store, audit_store)
async def require_device(request: Request): return await auth_verifier.verify(request)
class IngestRequest(BaseModel): text:str; source_kind:str="manual"; source_title:str="Manual Import"; consent_grant_id:str|None=None
class AskRequest(BaseModel): prompt:str; provider:str="local_mock"; allow_cloud:bool=False
class PairConfirm(BaseModel): pairing_id:str; device_name:str; public_key:str; signature:str; nonce:str
class ExecuteRequest(BaseModel): approval_id:str; double_confirm:bool=False
class ConsentRequest(BaseModel): data_source:str; scope:str; purpose:str; retention_days:int=30; model_access_level:str="local_only"
def audit(event_type:str, status:str="recorded", **kw):
    ev=AuditEvent(actor=kw.pop("actor","shadow_node"), event_type=event_type, status=status, **kw); audit_store.put(ev); return ev
@app.get("/health")
def health(): return {"status":"ok","version":"0.2.0-alpha","local_first":True,"emergency_paused":profile.emergency_paused}
@app.post("/emergency/pause")
def pause(device: Device = Depends(require_device)): profile.emergency_paused=True; audit("emergency_pause",status="enabled"); return health()
@app.post("/emergency/resume")
def resume(device: Device = Depends(require_device)): profile.emergency_paused=False; audit("emergency_pause",status="disabled"); return health()
@app.post("/pair/start")
def pair_start(): return pairing_service.start()
@app.post("/pair/confirm")
def pair_confirm(req:PairConfirm):
    try: dev=pairing_service.confirm(req.pairing_id, req.device_name, req.public_key, req.signature, req.nonce)
    except Exception as e: raise HTTPException(400, str(e))
    audit("device_paired", data_used=[dev.id], status="trusted"); return dev
@app.post("/devices/register")
def register(d:Device): return device_store.put(d)
@app.get("/devices")
def list_devices(device: Device = Depends(require_device)): return device_store.list()
@app.delete("/devices/{id}")
def remove_device(id:str, device: Device = Depends(require_device)):
    try: dev=pairing_service.revoke(id)
    except Exception as e: raise HTTPException(404, str(e))
    audit("device_revoked", data_used=[id], status="revoked"); return dev
@app.post("/consents")
def grant_consent(req:ConsentRequest, device: Device = Depends(require_device)):
    g=ConsentGrant(**req.model_dump()); consent_store.put(g); audit("consent_granted", data_used=[g.data_source], permission_checked=g.scope); return g
@app.get("/consents")
def consents(device: Device = Depends(require_device)): return consent_store.list()
@app.delete("/consents/{id}")
def revoke_consent(id:str, device: Device = Depends(require_device)):
    g=consent_store.get(id)
    if not g: raise HTTPException(404,"consent not found")
    g.revoked_at=now(); consent_store.put(g); audit("consent_revoked", data_used=[id]); return g
@app.get("/connectors")
def list_connectors(device: Device = Depends(require_device)): return connectors.list()
@app.post("/memory/ingest")
def ingest(req:IngestRequest, device: Device = Depends(require_device)):
    if profile.emergency_paused: raise HTTPException(423,"emergency pause enabled")
    src=MemorySource(kind=req.source_kind,title=req.source_title,consent_grant_id=req.consent_grant_id); items=memory.ingest(req.text,src); audit("memory_ingest", actor="user", data_used=[src.title], status="stored"); return {"items":items}
@app.get("/memory/search")
def search(q:str, limit:int=5, device: Device = Depends(require_device)): return memory.search(q,limit)
@app.post("/agent/ask")
def ask(req:AskRequest, device: Device = Depends(require_device)):
    results=memory.search(req.prompt,3)
    if not results:
        results=memory.search("Alpha",3)
    context="\n".join(r.item.text for r in results); model=models.complete(ModelRequest(prompt=req.prompt,context=context,provider=req.provider,explicit_cloud_approval=req.allow_cloud), consent_store.list())
    plan=core.propose(req.prompt); audit("agent_ask", data_used=[r.item.id for r in results], model_used=req.provider, status="answered" if not model.get("blocked") else "cloud_blocked")
    return {"answer":model.get("text","Cloud use blocked by policy."),"sources":[{"memory_id":r.item.id,"attribution":r.attribution} for r in results],"context_package":model["context_package"],"plan":plan,"model":model}
@app.post("/agent/plan")
def plan(req:AskRequest, device: Device = Depends(require_device)):
    p=core.propose(req.prompt); task=AgentTask(prompt=req.prompt, plan=p, status="planned"); task_store.put(task); audit("agent_plan", proposed_action=p.actions[0].description if p.actions else None); return p
@app.post("/approvals")
def create_approval(action:AgentAction, reason:str="User approval required", device: Device = Depends(require_device)):
    action.risk=core.policy.classify_action(action); action.requires_approval=core.policy.requires_approval(action,profile)
    req=ApprovalRequest(action=action, reason=reason); approval_store.put(req); audit("approval_requested", proposed_action=action.description, permission_checked=str(action.risk)); return req
@app.get("/approvals")
def approvals(device: Device = Depends(require_device)): return approval_store.list()
@app.post("/approvals/{id}/approve")
def approve(id:str, device: Device = Depends(require_device)):
    req=approval_store.get(id)
    if not req: raise HTTPException(404,"approval not found")
    req.status=ApprovalStatus.APPROVED; req.decided_at=now(); approval_store.put(req); audit("approval_decided", proposed_action=req.action.description, status="approved"); return req
@app.post("/approvals/{id}/deny")
def deny(id:str, device: Device = Depends(require_device)):
    req=approval_store.get(id)
    if not req: raise HTTPException(404,"approval not found")
    req.status=ApprovalStatus.DENIED; req.decided_at=now(); approval_store.put(req); audit("approval_decided", proposed_action=req.action.description, status="denied"); return req
@app.post("/agent/execute")
def execute(req:ExecuteRequest, device: Device = Depends(require_device)):
    ar=approval_store.get(req.approval_id)
    if not ar: raise HTTPException(404,"approval not found")
    if ar.action.risk==RiskClass.CRITICAL and not req.double_confirm: raise HTTPException(409,"critical/destructive action requires double confirmation")
    allowed=ar.status==ApprovalStatus.APPROVED
    res=core.execute(ar.action,approved=allowed)
    if not res.get("ok"): audit("ghost_execute", proposed_action=ar.action.description, status="blocked", result=res.get("reason")); return res
    plan=AgentPlan(user_intent=ar.reason, actions=[ar.action]); gres=ghost.execute(ghost.to_ir(plan),approved=True); audit("ghost_execute", proposed_action=ar.action.description, status=gres["status"], result=str(gres.get("telemetry"))); return {"ok":True,"ghost":gres}
@app.get("/audit")
def get_audit(device: Device = Depends(require_device)): return audit_store.list(include_revoked=True)
@app.websocket("/ws/tasks")
async def ws_tasks(ws:WebSocket):
    await ws.accept(); await ws.send_json({"type":"hello","node":"shadow-node","version":"0.2.0-alpha"})
    while True:
        data=await ws.receive_json(); await ws.send_json({"type":"ack","received":data})
