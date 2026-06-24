"""Encrypted runtime state (audit, consents, devices) survives a restart."""
import importlib
from fastapi.testclient import TestClient


def _fresh_client(monkeypatch, tmp_path):
    monkeypatch.setenv("SHADOW_RUNTIME_DB", str(tmp_path / "runtime.db"))
    monkeypatch.setenv("SHADOW_RUNTIME_KEY_FILE", str(tmp_path / "runtime.key"))
    monkeypatch.delenv("SHADOW_MEMORY_DB", raising=False)
    import shadow_node.main as m
    importlib.reload(m)
    return TestClient(m.app), m


def test_consents_and_audit_persist_across_restart(monkeypatch, tmp_path):
    c1, _ = _fresh_client(monkeypatch, tmp_path)
    c1.post("/consent", json={"data_source": "docs", "scope": "selected", "purpose": "answer", "model_access_level": "cloud_redacted"})
    c1.post("/agent/ask", json={"prompt": "hello there"})  # writes an audit event
    audit_before = len(c1.get("/audit").json())
    assert audit_before > 0

    # "Restart": reload the module against the same runtime DB.
    c2, _ = _fresh_client(monkeypatch, tmp_path)
    assert len(c2.get("/audit").json()) >= audit_before          # audit restored
    # The previously granted consent is still active and gates cloud the same way.
    r = c2.post("/agent/ask", json={"prompt": "hi", "allow_cloud": True, "cloud_approval": True})
    assert r.status_code == 200  # active persisted consent allows the cloud-approved path


def test_paired_device_persists_across_restart(monkeypatch, tmp_path):
    c1, _ = _fresh_client(monkeypatch, tmp_path)
    pid = c1.post("/pair/start").json()["pairing_id"]
    paired = c1.post("/pair/confirm", json={"pairing_id": pid, "device_name": "iPhone", "public_key": "pk-abc"}).json()
    device_id = paired["device"]["id"]

    c2, m2 = _fresh_client(monkeypatch, tmp_path)
    assert device_id in m2.sessions.devices            # device restored
    assert m2.sessions.secrets.get(device_id)          # secret restored too
