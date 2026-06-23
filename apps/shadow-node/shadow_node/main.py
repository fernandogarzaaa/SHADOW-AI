from fastapi import FastAPI, HTTPException, WebSocket
from pydantic import BaseModel
from agent_core import *
from memory_engine import *
from axiom_adapter import AxiomAdapter
from ghost_adapter import GhostAdapter
import tempfile
app=FastAPI(title="Shadow Node", version="0.1.0")
profile=UserProfile(); core=AgentCore(profile); store=EncryptedMemoryStore(path=tempfile.gettempdir()+"/shadow_memory.db"); memory=MemoryEngine(store); axiom=AxiomAdapter(); ghost=GhostAdapter(); audit:list[AuditEvent]=[]; devices:dict[str,Device]={}; pairing={}
class IngestRequest(BaseModel): text:str; source_kind:str="manual"; source_title:str="Manual Import"
class AskRequest(BaseModel): prompt:str; allow_cloud:bool=False
class PairConfirm(BaseModel): pairing_id:str; device_name:str; public_key:str
@app.get("/health")
def health(): return {"status":"ok","local_first":True,"emergency_paused":profile.emergency_paused}
@app.post("/pair/start")
def pair_start():
    pid=new_id("pair"); pairing[pid]="pending"; return {"pairing_id":pid,"code":pid[-6:].upper(),"expires_in_seconds":300}
@app.post("/pair/confirm")
def pair_confirm(req:PairConfirm):
    if req.pairing_id not in pairing: raise HTTPException(404,"pairing not found")
    dev=Device(name=req.device_name, public_key=req.public_key, trusted=True); devices[dev.id]=dev; return dev
@app.post("/devices/register")
def register(d:Device): devices[d.id]=d; return d
@app.get("/devices")
def list_devices(): return list(devices.values())
@app.post("/memory/ingest")
def ingest(req:IngestRequest):
    src=MemorySource(kind=req.source_kind,title=req.source_title); items=memory.ingest(req.text,src); audit.append(AuditEvent(actor="user",event_type="memory_ingest",data_used=[src.title],status="stored")); return {"items":items}
@app.get("/memory/search")
def search(q:str, limit:int=5): return memory.search(q,limit)
@app.post("/agent/ask")
def ask(req:AskRequest):
    results=memory.search(req.prompt,3); context="\n".join(r.item.text for r in results); packaged=axiom.package_context(context); plan=core.propose(req.prompt); return {"answer":"Local MVP answer synthesized from approved memory.","sources":[r.attribution for r in results],"context_package":packaged,"plan":plan}
@app.post("/agent/plan")
def plan(req:AskRequest): return core.propose(req.prompt)
@app.post("/agent/execute")
def execute(action:AgentAction, approved:bool=False):
    res=core.execute(action,approved); audit.extend(core.audit); return res
@app.get("/approvals")
def approvals(): return list(core.approvals.requests.values())
@app.post("/approvals/{id}/approve")
def approve(id:str): return core.approvals.decide(id,True)
@app.post("/approvals/{id}/deny")
def deny(id:str): return core.approvals.decide(id,False)
@app.get("/audit")
def get_audit(): return audit + core.audit
@app.websocket("/ws/tasks")
async def ws_tasks(ws:WebSocket):
    await ws.accept(); await ws.send_json({"type":"hello","node":"shadow-node"})
    while True:
        data=await ws.receive_json(); await ws.send_json({"type":"ack","received":data})
