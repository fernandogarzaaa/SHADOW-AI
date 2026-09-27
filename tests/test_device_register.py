"""Regression tests for /devices/register hardening (audit P0-7).

The endpoint must never write a client-supplied device record: the
server mints the id, fingerprint, trust state, session window, and
HMAC secret. A registered device must be able to authenticate
immediately (previously no secret was set, so verify() raised
KeyError -> HTTP 500).
"""
import time

import pytest
from fastapi.testclient import TestClient

from agent_core import sign_request


@pytest.fixture
def api(monkeypatch):
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    return TestClient(m.app), m


def _signed(device_id, secret, method, path, body="", nonce="regtest"):
    ts = int(time.time())
    return {"x-shadow-device-id": device_id, "x-shadow-nonce": nonce,
            "x-shadow-timestamp": str(ts),
            "x-shadow-signature": sign_request(secret, method, path, body, nonce, ts)}


def test_register_mints_server_side_fields(api):
    client, m = api
    # Old-style hostile payload: chosen id, untrusted, revoked, long session.
    payload = {"name": "Evil", "public_key": "evil-pub",
               "id": "dev_chosen", "trusted": False, "revoked": True,
               "session_expires_at": "2099-01-01T00:00:00+00:00"}
    r = client.post("/devices/register", json=payload).json()
    dev = r["device"]
    assert dev["id"] != "dev_chosen" and dev["id"].startswith("dev_")
    assert dev["name"] == "Evil"
    assert dev["trusted"] is True
    assert dev["revoked"] is False
    assert dev["session_expires_at"] < "2099-01-01T00:00:00+00:00"
    assert len(r["secret"]) == 64
    # The stored record is the server-minted one, not the client payload.
    stored = m.sessions.devices[dev["id"]]
    assert stored.trusted is True and stored.revoked is False


def test_registered_device_can_authenticate(api):
    client, m = api
    r = client.post("/devices/register",
                    json={"name": "Phone", "public_key": "phone-pub"}).json()
    dev_id, secret = r["device"]["id"], r["secret"]
    m.AUTH_REQUIRED = True
    try:
        res = client.get("/devices", headers=_signed(dev_id, secret, "GET", "/devices"))
        assert res.status_code == 200
    finally:
        m.AUTH_REQUIRED = False


def test_register_cannot_overwrite_existing_device(api):
    client, m = api
    first = client.post("/devices/register",
                        json={"name": "One", "public_key": "pub-one"}).json()["device"]
    snapshot = m.sessions.devices[first["id"]].model_dump()
    second = client.post("/devices/register",
                         json={"name": "Two", "public_key": "pub-one"}).json()["device"]
    assert second["id"] != first["id"]
    assert m.sessions.devices[first["id"]].model_dump() == snapshot


def test_register_emits_audit_event(api):
    client, m = api
    n_before = len(m.audit)
    r = client.post("/devices/register",
                    json={"name": "Audited", "public_key": "pub-audit"}).json()
    events = [e for e in m.audit[n_before:] if e.event_type == "device_registered"]
    assert len(events) == 1
    assert events[0].metadata["device_id"] == r["device"]["id"]
