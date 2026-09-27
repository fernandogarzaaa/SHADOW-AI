"""Adversarial tests: device pairing ceremony (audit P1).

Before: POST /pair/confirm was unauthenticated and minted a device for
whoever started the pairing (the "code" was derived from the pairing_id
itself), and POST /devices/register let any authenticated device mint
another device in one call.

Now: enrollment is a ceremony. /pair/start binds the proposed identity;
/pair/approve requires a trusted, non-revoked owner device (HMAC
authenticated); /pair/confirm mints only after approval (or for the
bootstrap first device when no owner exists). /devices/register only
initiates enrollment; it never mints.
"""
import time

import pytest
from fastapi.testclient import TestClient

from agent_core import sign_request


@pytest.fixture
def api(monkeypatch):
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
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


def _signed(device_id, secret, method, path, body="", nonce="n1"):
    ts = int(time.time())
    return {"x-shadow-device-id": device_id, "x-shadow-nonce": nonce,
            "x-shadow-timestamp": str(ts),
            "x-shadow-signature": sign_request(secret, method, path, body, nonce, ts)}


def _owner(api):
    client, m = api
    return m.sessions.register("Owner", "owner-pub", "owner-secret")


def test_start_requires_proposed_identity(api):
    client, _ = api
    assert client.post("/pair/start", json={}).status_code == 422


def test_attacker_cannot_self_confirm(api):
    """The old flow: start then immediately confirm minted a device.
    Now the new device waits at 202 and nothing is minted."""
    client, m = api
    _owner(api)  # an owner exists, so no bootstrap shortcut
    pid = client.post("/pair/start",
                      json={"device_name": "Evil", "public_key": "evil-pub"}).json()["pairing_id"]
    r = client.post("/pair/confirm", json={"pairing_id": pid})
    assert r.status_code == 202 and r.json()["status"] == "pending"
    assert len(m.sessions.devices) == 1  # only the owner


def test_owner_approve_then_confirm_mints(api):
    client, m = api
    owner = _owner(api)
    m.AUTH_REQUIRED = True
    try:
        pid = client.post("/pair/start",
                          json={"device_name": "Tablet", "public_key": "tablet-pub"}).json()["pairing_id"]
        body = f'{{"pairing_id":"{pid}"}}'
        ar = client.post("/pair/approve", content=body,
                         headers={**_signed(owner.id, "owner-secret", "POST",
                                            "/pair/approve", body, nonce="a1"),
                                  "Content-Type": "application/json"})
        assert ar.status_code == 200 and ar.json()["status"] == "approved"
        # identity comes from the start proposal, not the confirm call
        cr = client.post("/pair/confirm", json={"pairing_id": pid})
        assert cr.status_code == 200
        dev = cr.json()["device"]
        assert dev["name"] == "Tablet" and dev["trusted"] is True
        assert len(cr.json()["secret"]) == 64
        # single-use: the pairing is consumed
        assert client.post("/pair/confirm", json={"pairing_id": pid}).status_code == 404
    finally:
        m.AUTH_REQUIRED = False


def test_approve_requires_owner_auth(api):
    client, m = api
    _owner(api)
    m.AUTH_REQUIRED = True
    try:
        pid = client.post("/pair/start",
                          json={"device_name": "X", "public_key": "x"}).json()["pairing_id"]
        assert client.post("/pair/approve",
                           json={"pairing_id": pid}).status_code == 401
    finally:
        m.AUTH_REQUIRED = False


def test_approve_by_revoked_device_forbidden(api):
    client, m = api
    owner = _owner(api)
    m.sessions.revoke(owner.id)
    m.AUTH_REQUIRED = True
    try:
        pid = client.post("/pair/start",
                          json={"device_name": "X", "public_key": "x"}).json()["pairing_id"]
        body = f'{{"pairing_id":"{pid}"}}'
        r = client.post("/pair/approve", content=body,
                        headers={**_signed(owner.id, "owner-secret", "POST",
                                           "/pair/approve", body, nonce="a2"),
                                 "Content-Type": "application/json"})
        assert r.status_code == 401  # middleware rejects revoked devices outright
        assert r.json()["detail"] == "revoked_device"
        # still pending afterwards
        assert client.post("/pair/confirm", json={"pairing_id": pid}).status_code == 202
    finally:
        m.AUTH_REQUIRED = False


def test_approve_unknown_pairing_404(api):
    client, m = api
    _owner(api)
    assert client.post("/pair/approve",
                       json={"pairing_id": "pair_missing"}).status_code == 404


def test_confirm_expired_pairing_410(api):
    client, m = api
    pid = client.post("/pair/start",
                      json={"device_name": "Old", "public_key": "old-pub"}).json()["pairing_id"]
    m = api[1]
    m.pairing[pid]["created_at"] -= 400
    assert client.post("/pair/confirm", json={"pairing_id": pid}).status_code == 410
    assert pid not in m.pairing


def test_bootstrap_first_device_needs_no_approver(api):
    """With zero owner devices (fresh node), the first enrollment
    self-completes so the node is not bricked."""
    client, m = api
    assert m.sessions.devices == {}
    pid = client.post("/pair/start",
                      json={"device_name": "First", "public_key": "first-pub"}).json()["pairing_id"]
    r = client.post("/pair/confirm", json={"pairing_id": pid})
    assert r.status_code == 200
    assert r.json()["device"]["name"] == "First"


def test_pairing_cap_rejects_flood(api):
    client, m = api
    _owner(api)
    pids = []
    try:
        for i in range(20):
            pids.append(client.post(
                "/pair/start",
                json={"device_name": f"d{i}", "public_key": f"pk{i}"}).json()["pairing_id"])
        assert client.post("/pair/start",
                           json={"device_name": "overflow", "public_key": "pk"}).status_code == 429
    finally:
        for pid in pids:
            api[1].pairing.pop(pid, None)


def test_approve_is_idempotent(api):
    client, m = api
    owner = _owner(api)
    m.AUTH_REQUIRED = True
    try:
        pid = client.post("/pair/start",
                          json={"device_name": "Dup", "public_key": "dup-pub"}).json()["pairing_id"]
        body = f'{{"pairing_id":"{pid}"}}'
        hdrs = {**_signed(owner.id, "owner-secret", "POST", "/pair/approve",
                          body, nonce="a3"), "Content-Type": "application/json"}
        assert client.post("/pair/approve", content=body, headers=hdrs).status_code == 200
        hdrs2 = {**_signed(owner.id, "owner-secret", "POST", "/pair/approve",
                           body, nonce="a4"), "Content-Type": "application/json"}
        r = client.post("/pair/approve", content=body, headers=hdrs2)
        assert r.status_code == 200 and r.json()["status"] == "approved"
    finally:
        m.AUTH_REQUIRED = False


def test_pairing_approval_audited(api):
    client, m = api
    owner = _owner(api)
    m.AUTH_REQUIRED = True
    try:
        n_before = len(m.audit)
        pid = client.post("/pair/start",
                          json={"device_name": "Aud", "public_key": "aud-pub"}).json()["pairing_id"]
        body = f'{{"pairing_id":"{pid}"}}'
        client.post("/pair/approve", content=body,
                    headers={**_signed(owner.id, "owner-secret", "POST",
                                       "/pair/approve", body, nonce="a5"),
                             "Content-Type": "application/json"})
        types = [e.event_type for e in m.audit[n_before:]]
        assert "pairing_started" in types and "pairing_approved" in types
        appr = [e for e in m.audit[n_before:] if e.event_type == "pairing_approved"][0]
        assert appr.metadata["approved_by"] == owner.id
    finally:
        m.AUTH_REQUIRED = False
