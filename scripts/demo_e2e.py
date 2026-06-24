#!/usr/bin/env python3
from __future__ import annotations
import json, sys, urllib.request, urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'apps/shadow-node'),str(ROOT/'packages/agent-core'),str(ROOT/'packages/memory-engine'),str(ROOT/'packages/axiom-adapter'),str(ROOT/'packages/ghost-adapter')]
from shadow_node.pairing import DemoDeviceIdentity
BASE='http://127.0.0.1:8787'
def call(method,path,payload=None):
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(BASE+path,data=data,method=method,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=5) as r: return json.loads(r.read().decode())
def main():
    print('1 health', call('GET','/health'))
    dev=DemoDeviceIdentity(); start=call('POST','/pair/start',{})
    sig=dev.sign_confirmation(start['pairing_id'],start['challenge'],start['nonce'])
    paired=call('POST','/pair/confirm',{'pairing_id':start['pairing_id'],'device_name':'Demo iOS Simulator','public_key':dev.public,'signature':sig,'nonce':start['nonce']}); print('2 paired', paired['id'])
    text=(ROOT/'examples/demo_memory.md').read_text(); print('3 ingest', len(call('POST','/memory/ingest',{'text':text,'source_title':'Project Alpha Brief'})['items']))
    ask=call('POST','/agent/ask',{'prompt':'What is the next safe Project Alpha action?','provider':'local_mock'}); print('4 answer', ask['answer'])
    action=json.loads((ROOT/'examples/demo_task.json').read_text()); approval=call('POST','/approvals?reason=Demo%20safe%20local%20action', action); print('5 approval', approval['id'])
    call('POST',f"/approvals/{approval['id']}/approve",{})
    result=call('POST','/agent/execute',{'approval_id':approval['id'],'double_confirm':False}); print('6 execute', result)
    audit=call('GET','/audit'); print('7 audit events', len(audit)); print(json.dumps(audit[-5:],indent=2))
if __name__=='__main__': main()
