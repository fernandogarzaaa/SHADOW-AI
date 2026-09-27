"""P0-6: /memory/ingest_file is confined to allowed roots.

Traversal, absolute paths outside the roots, symlink escapes, and oversized
files are rejected; a valid in-root file ingests normally.
"""
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from agent_core import *
from memory_engine import *
from axiom_adapter import AxiomAdapter, RedactionLayer
from ghost_adapter import GhostAdapter, GhostTaskIR
from shadow_node.main import app
import shadow_node.main as main

@pytest.fixture()
def client(tmp_path, monkeypatch):
    main.AUTH_REQUIRED=False
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR",str(tmp_path/"ws"))
    monkeypatch.setenv("SHADOW_INGEST_ROOTS","")
    return TestClient(app)

def _consent(client):
    return client.post('/consent',json={'data_source':'file','scope':'selected','purpose':'test'}).json()['id']

def _ingest(client, path, grant):
    return client.post('/memory/ingest_file',json={'path':str(path),'consent_grant_id':grant})

def test_in_root_file_ingests(client,tmp_path):
    ws=tmp_path/"ws"; ws.mkdir(); f=ws/'note.md'; f.write_text('hello workspace')
    r=_ingest(client,f,_consent(client)); assert r.status_code==200, r.text
    assert r.json()['source']['kind']=='file/md'

def test_absolute_path_outside_roots_rejected(client,tmp_path):
    outside=tmp_path/'outside.md'; outside.write_text('nope')
    r=_ingest(client,outside,_consent(client)); assert r.status_code==403
    assert 'allowed ingest roots' in r.text

def test_traversal_escape_rejected(client,tmp_path):
    ws=tmp_path/"ws"; ws.mkdir(); outside=tmp_path/'secret.md'; outside.write_text('nope')
    r=_ingest(client,ws/'..'/'secret.md',_consent(client)); assert r.status_code==403

def test_symlink_escape_rejected(client,tmp_path):
    ws=tmp_path/"ws"; ws.mkdir(); outside=tmp_path/'secret.md'; outside.write_text('nope')
    link=ws/'link.md'
    try: link.symlink_to(outside)
    except OSError: pytest.skip("symlinks unsupported on this platform")
    r=_ingest(client,link,_consent(client)); assert r.status_code==403

def test_oversize_file_rejected(client,tmp_path):
    ws=tmp_path/"ws"; ws.mkdir(); f=ws/'big.md'
    f.write_bytes(b'x'*(6*1024*1024))
    r=_ingest(client,f,_consent(client)); assert r.status_code==400
    assert 'file_too_large' in r.text

def test_missing_file_is_404(client,tmp_path):
    ws=tmp_path/"ws"; ws.mkdir()
    r=_ingest(client,ws/'ghost.md',_consent(client)); assert r.status_code==404

def test_unsupported_type_still_400(client,tmp_path):
    ws=tmp_path/"ws"; ws.mkdir(); f=ws/'a.exe'; f.write_text('x')
    r=_ingest(client,f,_consent(client)); assert r.status_code==400

def test_consent_still_required(client,tmp_path):
    ws=tmp_path/"ws"; ws.mkdir(); f=ws/'note.md'; f.write_text('hi')
    assert _ingest(client,f,'bad-grant').status_code==403

def test_extra_root_via_env(client,tmp_path,monkeypatch):
    docs=tmp_path/'docs'; docs.mkdir(); f=docs/'d.md'; f.write_text('extra root ok')
    monkeypatch.setenv("SHADOW_INGEST_ROOTS",str(docs))
    r=_ingest(client,f,_consent(client)); assert r.status_code==200, r.text
