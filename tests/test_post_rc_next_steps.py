from __future__ import annotations
from datetime import datetime, timezone
import json, uuid
from pathlib import Path
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from shadow_node.main import app
from shadow_node.pairing import DemoDeviceIdentity
from shadow_node.auth import SignedRequestVerifier
from shadow_node.stores import DeviceStore, AuditStore, SQLiteRuntimeStore
from memory_engine import EncryptedMemoryStore, MemoryEngine, MemorySource

client=TestClient(app)

def pair():
    dev=DemoDeviceIdentity(); st=client.post('/pair/start',json={}).json(); sig=dev.sign_confirmation(st['pairing_id'],st['challenge'],st['nonce'])
    res=client.post('/pair/confirm',json={'pairing_id':st['pairing_id'],'device_name':'post-rc','public_key':dev.public,'signature':sig,'nonce':st['nonce']})
    assert res.status_code==200
    return dev,res.json()['id']

def signed(dev, did, method, path, payload=None, nonce=None):
    body=json.dumps(payload, separators=(',',':')).encode() if payload is not None else b''
    nonce=nonce or uuid.uuid4().hex; ts=datetime.now(timezone.utc).isoformat(); sign_path=path.split('?')[0]
    msg=b'\n'.join([method.encode(),sign_path.encode(),body,nonce.encode(),ts.encode()])
    return {'X-Shadow-Device-Id':did,'X-Shadow-Nonce':nonce,'X-Shadow-Timestamp':ts,'X-Shadow-Signature':dev.sign_raw(msg)}

def test_runtime_key_file_persists_store_data(tmp_path, monkeypatch):
    key_file=tmp_path/'runtime.key'; monkeypatch.setenv('SHADOW_RUNTIME_KEY_FILE', str(key_file))
    db=tmp_path/'runtime.db'
    from agent_core import Device
    first=DeviceStore(str(db)); saved=first.put(Device(name='persisted', public_key='pub', trusted=True))
    second=DeviceStore(str(db)); assert second.get(saved.id).name == 'persisted'
    assert key_file.exists()

def test_memory_key_file_persists_memory_data(tmp_path, monkeypatch):
    key_file=tmp_path/'memory.key'; monkeypatch.setenv('SHADOW_MEMORY_KEY_FILE', str(key_file))
    db=tmp_path/'memory.db'
    first=MemoryEngine(EncryptedMemoryStore(path=str(db)))
    item=first.ingest('persistent private local memory', MemorySource(kind='manual', title='persist'))[0]
    second=EncryptedMemoryStore(path=str(db))
    assert second.get(item.id).text == 'persistent private local memory'
    assert key_file.exists()

def test_nonce_replay_persists_in_runtime_database(tmp_path):
    db=str(tmp_path/'runtime.db')
    devices=DeviceStore(db); audit=AuditStore(db)
    dev,did=pair(); device=client.get('/devices',headers=signed(dev,did,'GET','/devices')).json()[0]
    # Trust the paired public key inside an isolated store used by two verifier instances.
    from agent_core import Device
    devices.put(Device(id=device['id'], name=device['name'], public_key=device['public_key'], trusted=True))
    verifier_one=SignedRequestVerifier(devices, audit, nonce_db_path=db)
    verifier_two=SignedRequestVerifier(devices, audit, nonce_db_path=db)
    now=datetime.now(timezone.utc)
    assert verifier_one.nonces.check(device['id'], 'same-nonce', now, 300) is True
    assert verifier_two.nonces.check(device['id'], 'same-nonce', now, 300) is False
