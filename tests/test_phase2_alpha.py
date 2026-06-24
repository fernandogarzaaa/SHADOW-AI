from datetime import datetime, timedelta, timezone
import tempfile, pytest
from fastapi.testclient import TestClient
from agent_core import *
from memory_engine import *
from axiom_adapter import AxiomAdapter, RedactionLayer
from ghost_adapter import GhostAdapter
from shadow_node.main import app
from shadow_node.stores import DeviceStore, ApprovalStore, AuditStore, ConsentStore, TaskStore
from shadow_node.pairing import PairingService, DemoDeviceIdentity
from shadow_node.connectors import ConnectorRegistry
from shadow_node.model_providers import ModelProviderRegistry, ModelRequest

def db(): return tempfile.NamedTemporaryFile(delete=True).name

def pair(svc, name="Demo"):
    ident=DemoDeviceIdentity(); start=svc.start(); sig=ident.sign_confirmation(start['pairing_id'], start['challenge'], start['nonce']); return svc.confirm(start['pairing_id'], name, ident.public, sig, start['nonce'])

def test_device_store_persists():
    path=db(); key=None; s=DeviceStore(path,key); d=s.put(Device(name='iPhone',public_key='pk')); key=s.key; assert DeviceStore(path,key).get(d.id).name=='iPhone'
def test_approval_store_persists():
    path=db(); s=ApprovalStore(path); a=s.put(ApprovalRequest(action=AgentAction(tool_name='x',description='x'),reason='r')); assert ApprovalStore(path,s.key).get(a.id).reason=='r'
def test_audit_store_persists():
    path=db(); s=AuditStore(path); e=s.put(AuditEvent(actor='t',event_type='e')); assert AuditStore(path,s.key).list()[0].event_type=='e'
def test_consent_store_persists():
    path=db(); s=ConsentStore(path); g=s.put(ConsentGrant(data_source='docs',scope='selected',purpose='qa')); assert ConsentStore(path,s.key).get(g.id).data_source=='docs'
def test_task_store_persists():
    path=db(); s=TaskStore(path); t=s.put(AgentTask(prompt='p')); assert TaskStore(path,s.key).get(t.id).prompt=='p'
def test_audit_append_only_delete_blocked():
    with pytest.raises(RuntimeError): AuditStore(db()).delete('x')
def test_pairing_success():
    assert pair(PairingService(DeviceStore(db()))).trusted is True
def test_pairing_invalid_signature():
    svc=PairingService(DeviceStore(db())); a=svc.start(); ident=DemoDeviceIdentity(); bad=DemoDeviceIdentity().sign_confirmation(a['pairing_id'],a['challenge'],a['nonce'])
    with pytest.raises(Exception): svc.confirm(a['pairing_id'],'bad',ident.public,bad,a['nonce'])
def test_pairing_replay_rejected():
    svc=PairingService(DeviceStore(db())); ident=DemoDeviceIdentity(); a=svc.start(); sig=ident.sign_confirmation(a['pairing_id'],a['challenge'],a['nonce']); svc.confirm(a['pairing_id'],'ok',ident.public,sig,a['nonce'])
    with pytest.raises(ValueError): svc.confirm(a['pairing_id'],'ok',ident.public,sig,a['nonce'])
def test_pairing_expired_rejected():
    svc=PairingService(DeviceStore(db()), ttl_seconds=-1); ident=DemoDeviceIdentity(); a=svc.start(); sig=ident.sign_confirmation(a['pairing_id'],a['challenge'],a['nonce'])
    with pytest.raises(ValueError): svc.confirm(a['pairing_id'],'old',ident.public,sig,a['nonce'])
def test_pairing_revoked_blocked():
    svc=PairingService(DeviceStore(db())); dev=pair(svc); svc.revoke(dev.id)
    with pytest.raises(PermissionError): svc.assert_trusted(dev.id)
def test_memory_search_multiple_chunks():
    e=MemoryEngine(EncryptedMemoryStore(path=db())); e.ingest('Alpha beta gamma '*100, MemorySource(kind='manual',title='doc')); assert e.search('Alpha')
def test_memory_revoke_hides_item():
    st=EncryptedMemoryStore(path=db()); e=MemoryEngine(st); item=e.ingest('secret alpha',MemorySource(kind='m',title='t'))[0]; st.revoke(item.id); assert st.get(item.id) is None
def test_policy_blocks_keylogger(): assert PolicyEngine().classify_action(AgentAction(tool_name='keylogger',description='x'))==RiskClass.BLOCKED
def test_policy_email_critical(): assert PolicyEngine().classify_action(AgentAction(tool_name='send_email',description='send'))==RiskClass.CRITICAL
def test_emergency_pause_blocks_execution():
    p=UserProfile(emergency_paused=True); ok,_=PolicyEngine().can_execute(AgentAction(tool_name='answer_question',description='safe'),p,approved=True); assert not ok
def test_cloud_blocked_without_consent():
    r=ModelProviderRegistry().complete(ModelRequest(prompt='p',context='email me@example.com',provider='openai_compatible',explicit_cloud_approval=True),[]); assert r['blocked']
def test_cloud_blocked_without_explicit_approval():
    g=ConsentGrant(data_source='docs',scope='s',purpose='p',model_access_level='cloud_redacted'); r=ModelProviderRegistry().complete(ModelRequest(prompt='p',context='c',provider='openai_compatible'),[g]); assert r['blocked']
def test_cloud_allowed_with_consent_and_approval():
    g=ConsentGrant(data_source='docs',scope='s',purpose='p',model_access_level='cloud_redacted'); r=ModelProviderRegistry().complete(ModelRequest(prompt='p',context='c',provider='openai_compatible',explicit_cloud_approval=True),[g]); assert r['cloud_used']
def test_axiom_redacts_email(): assert '[EMAIL]' in RedactionLayer().redact('a@b.com')
def test_axiom_compresses(): assert 'compressed' in AxiomAdapter().package_context('x'*3000, budget=100)['context']
def test_axiom_package_has_skeleton_tokens():
    p=AxiomAdapter().package_context('hello world'); assert 'semantic_skeleton' in p and p['tokens_estimated'] > 0
def test_ghost_requires_approval(): assert GhostAdapter().execute(GhostAdapter().to_ir(AgentPlan(user_intent='u',actions=[])),False)['status']=='approval_required'
def test_ghost_executes_approved(): assert GhostAdapter().execute(GhostAdapter().to_ir(AgentPlan(user_intent='u',actions=[])),True)['status']=='completed'
def test_connector_registry_lists_required():
    names={c['name'] for c in ConnectorRegistry().list()}; assert {'gmail','calendar','files','notes','desktop_node'} <= names
def test_api_health(): assert TestClient(app).get('/health').status_code==200
def test_api_connectors(): assert TestClient(app).get('/connectors').status_code==401
def test_api_consent_flow():
    c=TestClient(app); r=c.post('/consents',json={'data_source':'docs','scope':'selected','purpose':'qa'}); assert r.status_code==401; assert c.get('/consents').status_code==401
def test_api_memory_and_ask_flow():
    c=TestClient(app); assert c.post('/memory/ingest',json={'text':'Alpha launch prefers local mode','source_title':'alpha'}).status_code==401; r=c.post('/agent/ask',json={'prompt':'Alpha launch?'}); assert r.status_code==401
def test_api_approval_execute_safe_flow():
    c=TestClient(app); assert c.post('/approvals?reason=test',json={'tool_name':'create_local_reminder','description':'safe','params':{}}).status_code==401
def test_api_critical_requires_double_confirm():
    c=TestClient(app); assert c.post('/agent/execute',json={'approval_id':'missing'}).status_code==401
def test_api_audit_records_events():
    assert TestClient(app).get('/audit').status_code==401
def test_api_pairing_success():
    c=TestClient(app); ident=DemoDeviceIdentity(); st=c.post('/pair/start').json(); sig=ident.sign_confirmation(st['pairing_id'],st['challenge'],st['nonce']); r=c.post('/pair/confirm',json={'pairing_id':st['pairing_id'],'device_name':'pytest','public_key':ident.public,'signature':sig,'nonce':st['nonce']}); assert r.status_code==200
def test_api_device_revocation():
    assert TestClient(app).get('/devices').status_code==401
