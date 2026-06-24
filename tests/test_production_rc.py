from __future__ import annotations
from datetime import datetime, timezone, timedelta
import json, uuid, pytest
from fastapi.testclient import TestClient
from shadow_node.main import app
from shadow_node.pairing import DemoDeviceIdentity
from agent_core import AgentAction, RiskClass
from memory_engine import EncryptedMemoryStore, MemoryEngine, MemorySource
import tempfile

client=TestClient(app)

def pair():
    dev=DemoDeviceIdentity(); st=client.post('/pair/start',json={}).json(); sig=dev.sign_confirmation(st['pairing_id'],st['challenge'],st['nonce'])
    res=client.post('/pair/confirm',json={'pairing_id':st['pairing_id'],'device_name':'pytest-ios','public_key':dev.public,'signature':sig,'nonce':st['nonce']})
    assert res.status_code==200, res.text
    return dev,res.json()['id']

def signed(dev, did, method, path, payload=None, ts=None, nonce=None):
    body=json.dumps(payload, separators=(',',':')).encode() if payload is not None else b''
    nonce=nonce or uuid.uuid4().hex; ts=ts or datetime.now(timezone.utc).isoformat()
    sign_path=path.split('?')[0]
    msg=b'\n'.join([method.encode(),sign_path.encode(),body,nonce.encode(),ts.encode()])
    return {'X-Shadow-Device-Id':did,'X-Shadow-Nonce':nonce,'X-Shadow-Timestamp':ts,'X-Shadow-Signature':dev.sign_raw(msg)}

def request(method,path,dev,did,payload=None,headers=None):
    h=headers or signed(dev,did,method,path,payload)
    return client.request(method,path,json=payload,headers=h)

def test_public_health_and_pairing_available():
    assert client.get('/health').status_code==200
    assert client.post('/pair/start',json={}).status_code==200

def test_protected_endpoint_requires_auth():
    assert client.get('/devices').status_code==401

def test_valid_signed_ios_style_request():
    d,i=pair(); assert request('GET','/devices',d,i).status_code==200

def test_invalid_signature_rejected():
    d,i=pair(); h=signed(d,i,'GET','/devices'); h['X-Shadow-Signature']='bad'
    assert client.get('/devices',headers=h).status_code==401

def test_missing_signature_rejected():
    d,i=pair(); h=signed(d,i,'GET','/devices'); h.pop('X-Shadow-Signature')
    assert client.get('/devices',headers=h).status_code==401

def test_replayed_nonce_rejected():
    d,i=pair(); h=signed(d,i,'GET','/devices')
    assert client.get('/devices',headers=h).status_code==200
    assert client.get('/devices',headers=h).status_code==409

def test_expired_timestamp_rejected():
    d,i=pair(); old=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    assert client.get('/devices',headers=signed(d,i,'GET','/devices',ts=old)).status_code==401

def test_revoked_device_rejected():
    d,i=pair(); admin,aid=pair(); assert client.delete(f'/devices/{i}',headers=signed(admin,aid,'DELETE',f'/devices/{i}')).status_code==200
    assert client.get('/devices',headers=signed(d,i,'GET','/devices')).status_code==403

def test_memory_ingest_search_ask_and_audit():
    d,i=pair(); payload={'text':'Project Alpha launch notes mention privacy first local memory','source_title':'alpha.md'}
    assert request('POST','/memory/ingest',d,i,payload).status_code==200
    assert request('GET','/memory/search?q=Alpha',d,i).status_code==200
    ask=request('POST','/agent/ask',d,i,{'prompt':'Alpha privacy','provider':'local_mock'}).json()
    assert ask['model']['cloud_used'] is False and 'context_package' in ask
    assert request('GET','/audit',d,i).json()

def test_cloud_blocked_without_consent():
    d,i=pair(); res=request('POST','/agent/ask',d,i,{'prompt':'hello','provider':'openai_compatible','allow_cloud':False}).json()
    assert res['model']['blocked'] is True

def test_emergency_pause_blocks_execution_and_ingest():
    d,i=pair(); assert request('POST','/emergency/pause',d,i,{}).status_code==200
    assert request('POST','/memory/ingest',d,i,{'text':'blocked'}).status_code==423
    assert request('POST','/emergency/resume',d,i,{}).status_code==200

def test_approval_double_confirm_for_destructive():
    d,i=pair(); action={'tool_name':'delete_file','description':'delete local file','params':{}}
    apr=request('POST','/approvals?reason=test',d,i,action).json(); request('POST',f"/approvals/{apr['id']}/approve",d,i,{})
    assert request('POST','/agent/execute',d,i,{'approval_id':apr['id']}).status_code==409

@pytest.mark.parametrize('idx', range(100))
def test_rc_policy_memory_matrix(idx):
    store=EncryptedMemoryStore(path=tempfile.NamedTemporaryFile().name); engine=MemoryEngine(store)
    flags=' SECRET_TOKEN prompt ignore previous instructions do-not-cloud' if idx % 10 == 0 else ''
    items=engine.ingest(f'rc memory item {idx} alpha beta{flags}', MemorySource(kind='manual', title=f'source-{idx}'))
    assert items[0].confidence > 0
    found=engine.search('alpha', limit=1)
    assert found and 'untrusted' in found[0].attribution.lower()
