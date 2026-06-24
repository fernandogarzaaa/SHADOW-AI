#!/usr/bin/env python3
from __future__ import annotations
import json, sys, datetime, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'apps/shadow-node'),str(ROOT/'packages/agent-core'),str(ROOT/'packages/memory-engine'),str(ROOT/'packages/axiom-adapter'),str(ROOT/'packages/ghost-adapter')]
from fastapi.testclient import TestClient
from shadow_node.main import app
from shadow_node.pairing import DemoDeviceIdentity
client=TestClient(app); DEVICE=None; DEVICE_ID=None
def headers(method,path,payload=None):
    h={'Content-Type':'application/json'}
    if DEVICE and DEVICE_ID:
        body=json.dumps(payload, separators=(',',':')).encode() if payload is not None else b''; nonce=uuid.uuid4().hex; ts=datetime.datetime.now(datetime.timezone.utc).isoformat()
        sign_path=path.split("?")[0]
        msg=b"\n".join([method.encode(),sign_path.encode(),body,nonce.encode(),ts.encode()])
        h.update({'X-Shadow-Device-Id':DEVICE_ID,'X-Shadow-Nonce':nonce,'X-Shadow-Timestamp':ts,'X-Shadow-Signature':DEVICE.sign_raw(msg)})
    return h
def call(method,path,payload=None):
    r=client.request(method,path,json=payload,headers=headers(method,path,payload)); r.raise_for_status(); return r.json()
def main():
    global DEVICE, DEVICE_ID
    print('1 health', call('GET','/health'))
    DEVICE=DemoDeviceIdentity(); start=call('POST','/pair/start',{})
    paired=call('POST','/pair/confirm',{'pairing_id':start['pairing_id'],'device_name':'Demo iOS Simulator','public_key':DEVICE.public,'signature':DEVICE.sign_confirmation(start['pairing_id'],start['challenge'],start['nonce']),'nonce':start['nonce']}); DEVICE_ID=paired['id']; print('2 paired', paired['id'])
    text=(ROOT/'examples/demo_memory.md').read_text(); print('3 ingest', len(call('POST','/memory/ingest',{'text':text,'source_title':'Project Alpha Brief'})['items']))
    ask=call('POST','/agent/ask',{'prompt':'What is the next safe Project Alpha action?','provider':'local_mock'}); print('4 answer', ask['answer'])
    action=json.loads((ROOT/'examples/demo_task.json').read_text()); approval=call('POST','/approvals?reason=Demo%20safe%20local%20action', action); print('5 approval', approval['id'])
    call('POST',f"/approvals/{approval['id']}/approve",{})
    print('6 execute', call('POST','/agent/execute',{'approval_id':approval['id'],'double_confirm':False}))
    audit=call('GET','/audit'); print('7 audit events', len(audit)); print(json.dumps(audit[-5:],indent=2))
if __name__=='__main__': main()
