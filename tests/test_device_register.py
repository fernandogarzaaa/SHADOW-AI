"""Regression tests for /devices/register enrollment ceremony (audit P1).

An authenticated device must not mint another device in a single call.
POST /devices/register now only *initiates* enrollment: the caller's HMAC
authentication is the owner approval, the server returns a pairing_id/code,
and the new device collects its credentials via POST /pair/confirm.
"""
import time

import pytest
from fastapi.testclient import TestClient

from agent_core import sign_request


@pytest.fixture
def api(monkeypatch):
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    # snapshot + isolate global device/pairing state
    dev_snap = dict(m.sessions.devices)
    sec_snap = dict(m.sessions.secrets)
    pair_snap = dict(m.pairing)
    m.sessions.devices.clear()
    m.sessions.secrets.clear()
    m.pairing.clear()
    yield TestClient(m.app), m
    m.sessions.devices.clear(); m.sessions.devices.update(dev_snap)
    m.sessions.secrets.clear(); m.sessions.secrets.update(sec_snap)
    m.pairing.clear(); m.pairing.update(pair_snap)


def _signed(device_id, secret, method, path, body="", nonce="regtest"):
    ts = int(time.time())
    return {"x-shadow-device-id": device_id, "x-shadow-nonce": nonce,
            "x-shadow-timestamp": str(ts),
            "x-shadow-signature": sign_request(secret, method, path, body, nonce, ts)}


def test_register_returns_pairing_not_device(api):
    client, m = api
    r = client.post("/devices/register",
                    json={"name": "Tablet", "public_key": "tablet-pub"}).json()
    assert "pairing_id" in r and "code" in r and "expires_in_seconds" in r
    assert "device" not in r and "secret" not in r
    # no device was minted
    assert len(m.sessions.devices) == 0
    assert m.pairing[r["pairing_id"]]["status"] == "approved"


def test_register_then_confirm_mints_device(api):
    client, m = api
    pid = client.post("/devices/register",
                      json={"name": "Tablet", "public_key": "tablet-pub"}).json()["pairing_id"]
    r = client.post("/pair/confirm", json={"pairing_id": pid}).json()
    dev = r["device"]
    assert dev["id"].startswith("dev_") and dev["name"] == "Tablet"
    assert dev["trusted"] is True and dev["revoked"] is False
    assert len(r["secret"]) == 64
    # the minted record is the server's, and the pairing is consumed
    assert m.sessions.devices[dev["id"]].name == "Tablet"
    assert pid not in m.pairing


def test_register_ignores_client_minted_fields(api):
    client, m = api
    payload = {"name": "Evil", "public_key": "evil-pub",
               "id": "dev_chosen", "trusted": False, "revoked": True,
               "session_expires_at": "2099-01-01T00:00:00+00:00"}
    pid = client.post("/devices/register", json=payload).json()["pairing_id"]
    # the pending pairing carries only the proposed identity
    entry = m.pairing[pid]
    assert "trusted" not in entry and "revoked" not in entry
    dev = client.post("/pair/confirm", json={"pairing_id": pid}).json()["device"]
    assert dev["id"] != "dev_chosen" and dev["trusted"] is True and dev["revoked"] is False
    assert dev["session_expires_at"] < "2099-01-01T00:00:00+00:00"


def test_register_requires_auth_when_enabled(api):
    client, m = api
    m.AUTH_REQUIRED = True
    try:
        r = client.post("/devices/register",
                        json={"name": "X", "public_key": "x"})
        assert r.status_code == 401
    finally:
        m.AUTH_REQUIRED = False


def test_register_approved_by_owner_device(api):
    client, m = api
    owner = m.sessions.register("OwnerPhone", "owner-pub", "owner-secret")
    m.AUTH_REQUIRED = True
    try:
        body = '{"name":"Watch","public_key":"watch-pub"}'
        r = client.post("/devices/register", content=body,
                        headers={**_signed(owner.id, "owner-secret", "POST",
                                           "/devices/register", body, nonce="n1"),
                                 "Content-Type": "application/json"})
        assert r.status_code == 200
        pid = r.json()["pairing_id"]
        assert m.pairing[pid]["approved_by"] == owner.id
    finally:
        m.AUTH_REQUIRED = False


def test_register_emits_audit_event(api):
    client, m = api
    n_before = len(m.audit)
    client.post("/devices/register",
                json={"name": "Audited", "public_key": "pub-audit"})
    events = [e for e in m.audit[n_before:]
              if e.event_type == "device_enrollment_initiated"]
    assert len(events) == 1
    assert events[0].metadata["approved_by"] == "devmode-owner"
