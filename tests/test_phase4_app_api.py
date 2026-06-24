import json, time
from fastapi.testclient import TestClient
import pytest
from agent_core import AgentAction, sign_request
from shadow_node.main import app, sessions
import shadow_node.main as main

@pytest.fixture()
def client():
    main.AUTH_REQUIRED=False
    return TestClient(app)

def pair_session():
    sessions.devices.clear(); sessions.secrets.clear(); sessions.nonces.clear(); sessions.audit.clear()
    dev=sessions.register('iOS','ios-public','phase4-secret')
    return dev, 'phase4-secret'

def headers(dev, secret, method, path, body=b'', nonce='ios-nonce'):
    if isinstance(body, bytes): body_text=body.decode()
    else: body_text=body
    ts=int(time.time())
    return {'x-shadow-device-id':dev.id,'x-shadow-nonce':nonce,'x-shadow-timestamp':str(ts),'x-shadow-signature':sign_request(secret, method, path, body_text, nonce, ts)}

def test_health_reports_version(client):
    assert client.get('/health').json()['version']=='1.0.0-rc'

def test_memory_list_endpoint(client):
    client.post('/memory/ingest',json={'text':'phase four memory','source_title':'phase4'})
    assert isinstance(client.get('/memory').json(), list)

def test_create_approval_endpoint(client):
    action={'id':'act_ios','tool_name':'ghost_handoff','description':'Run safe mock','params':{},'risk':'low','requires_approval':True,'destructive':False,'data_used':[]}
    r=client.post('/approvals',json={'action':action,'reason':'iOS proposal'}).json()
    assert r['action_preview']=='Run safe mock'

def test_approve_audit_event(client):
    action={'id':'act_ios2','tool_name':'answer_question','description':'Preview','params':{},'risk':'low','requires_approval':True,'destructive':False,'data_used':[]}
    rid=client.post('/approvals',json={'action':action,'reason':'test'}).json()['id']
    client.post(f'/approvals/{rid}/approve')
    assert any(e['event_type']=='approval_approved' for e in client.get('/audit').json())

def test_emergency_pause_endpoint_blocks_execution(client):
    client.post('/emergency_pause',json={'paused':True,'reason':'test'})
    action={'id':'act_pause','tool_name':'answer_question','description':'x','params':{},'risk':'low','requires_approval':False,'destructive':False,'data_used':[]}
    res=client.post('/agent/execute',json={'action':action,'approved':True,'double_confirmed':False}).json()
    client.post('/emergency_pause',json={'paused':False,'reason':'resume'})
    assert res['ok'] is False and 'Emergency pause' in res['reason']

def test_emergency_pause_audited(client):
    client.post('/emergency_pause',json={'paused':True,'reason':'audit'}); client.post('/emergency_pause',json={'paused':False,'reason':'resume'})
    assert any(e['event_type']=='emergency_pause' for e in client.get('/audit').json())

def test_agent_ask_audited(client):
    client.post('/agent/ask',json={'prompt':'hello'})
    assert any(e['event_type']=='agent_ask' for e in client.get('/audit').json())

def test_error_envelope_for_missing_pair(client):
    r=client.post('/pair/confirm',json={'pairing_id':'missing','device_name':'ios','public_key':'pk'})
    assert r.status_code==404 and 'error' in r.json()

def test_protected_memory_requires_auth_when_enabled(client):
    main.AUTH_REQUIRED=True
    r=client.get('/memory')
    main.AUTH_REQUIRED=False
    assert r.status_code==401

def test_protected_memory_accepts_signed_get(client):
    dev, secret=pair_session(); main.AUTH_REQUIRED=True
    r=client.get('/memory',headers=headers(dev,secret,'GET','/memory',nonce='getmem'))
    main.AUTH_REQUIRED=False
    assert r.status_code==200

def test_signed_post_body_auth(client):
    dev, secret=pair_session(); main.AUTH_REQUIRED=True
    body=json.dumps({'text':'signed ios memory','source_kind':'ios','source_title':'signed'}, separators=(',',':')).encode()
    r=client.post('/memory/ingest',content=body,headers={**headers(dev,secret,'POST','/memory/ingest',body,nonce='postmem'),'content-type':'application/json'})
    main.AUTH_REQUIRED=False
    assert r.status_code==200

def test_signed_post_replay_rejected(client):
    dev, secret=pair_session(); main.AUTH_REQUIRED=True
    h=headers(dev,secret,'GET','/memory',nonce='replay4')
    assert client.get('/memory',headers=h).status_code==200
    r=client.get('/memory',headers=h)
    main.AUTH_REQUIRED=False
    assert r.status_code==401

def test_revoked_signed_request_rejected(client):
    dev, secret=pair_session(); sessions.revoke(dev.id); main.AUTH_REQUIRED=True
    r=client.get('/memory',headers=headers(dev,secret,'GET','/memory',nonce='revoked4'))
    main.AUTH_REQUIRED=False
    assert r.status_code==401

def test_ghost_mock_execute_from_ios_approval(client):
    action={'id':'act_ghost','tool_name':'ghost_handoff','description':'Safe Ghost mock','params':{},'risk':'low','requires_approval':True,'destructive':False,'data_used':[]}
    r=client.post('/agent/execute',json={'action':action,'approved':True,'double_confirmed':False}).json()
    assert r['status']=='mock_executed'

def test_destructive_requires_double_confirm_api(client):
    action={'id':'act_delete','tool_name':'delete_file','description':'delete','params':{},'risk':'high','requires_approval':True,'destructive':True,'data_used':[]}
    r=client.post('/agent/execute',json={'action':action,'approved':True,'double_confirmed':False}).json()
    assert r['ok'] is False

def test_destructive_executes_with_double_confirm_api(client):
    action={'id':'act_delete2','tool_name':'delete_file','description':'delete','params':{},'risk':'high','requires_approval':True,'destructive':True,'data_used':[]}
    r=client.post('/agent/execute',json={'action':action,'approved':True,'double_confirmed':True}).json()
    assert r['ok'] is True

def test_cloud_block_error_envelope(client):
    r=client.post('/agent/ask',json={'prompt':'hello','allow_cloud':True,'cloud_approval':False})
    assert r.status_code==403 and 'error' in r.json()

def test_search_result_contract(client):
    client.post('/memory/ingest',json={'text':'contract source memory','source_title':'contract'})
    data=client.get('/memory/search',params={'q':'contract'}).json()
    assert {'item','score','freshness','attribution','explanation'} <= set(data[0].keys())

def test_devices_contract(client):
    assert isinstance(client.get('/devices').json(), list)

def test_model_provider_contract(client):
    data=client.get('/model/providers').json(); assert {'cloud_enabled','provider','endpoint_configured','api_key_configured'} <= set(data.keys())
