"""Contract-first list endpoints + device revoke authorization.

Regression coverage for re-audit items 4, 5, 6, 9:

- GET /approvals and GET /devices return the uniform page envelope
  {"items", "count", "next_cursor"}, never a bare array (the Expo client
  declared object types while the server returned arrays).
- GET /approvals honors ?status= filtering.
- POST /devices/{id}/revoke: a device may revoke itself; revoking another
  device requires owner authority. Unknown device ids 404.
"""

import time

from fastapi.testclient import TestClient

import shadow_node.main as main
from shadow_node.main import app, sessions
from agent_core import sign_request


def _client():
    main.AUTH_REQUIRED = False
    return TestClient(app)


def _signed(device_id, secret, method, path, nonce):
    ts = int(time.time())
    return {
        "x-shadow-device-id": device_id,
        "x-shadow-nonce": nonce,
        "x-shadow-timestamp": str(ts),
        "x-shadow-signature": sign_request(secret, method, path, "", nonce, ts),
    }


def test_approvals_page_envelope():
    client = _client()
    data = client.get("/approvals").json()
    assert set(data.keys()) == {"items", "count", "next_cursor"}
    assert data["count"] == len(data["items"])
    assert data["next_cursor"] is None


def test_approvals_status_filter():
    client = _client()
    action = {"tool_name": "note.create", "description": "filter me",
              "params": {}, "risk": "low", "requires_approval": True,
              "destructive": False, "data_used": []}
    rid = client.post("/approvals", json={"action": action, "reason": "t"}).json()["id"]
    pending = client.get("/approvals", params={"status": "pending"}).json()
    assert any(a["id"] == rid for a in pending["items"])
    client.post(f"/approvals/{rid}/approve")
    pending = client.get("/approvals", params={"status": "pending"}).json()
    assert not any(a["id"] == rid for a in pending["items"])
    approved = client.get("/approvals", params={"status": "approved"}).json()
    assert any(a["id"] == rid for a in approved["items"])


def test_devices_page_envelope():
    client = _client()
    data = client.get("/devices").json()
    assert set(data.keys()) == {"items", "count", "next_cursor"}
    assert data["count"] == len(data["items"])


def _two_devices():
    sessions.devices.clear(); sessions.secrets.clear(); sessions.nonces.clear()
    a = sessions.register("PhoneA", "pubA", "secA")
    b = sessions.register("PhoneB", "pubB", "secB")
    a.is_owner = True  # PhoneA is the owner; PhoneB is a plain trusted device
    return a, b


def test_self_revoke_allowed():
    _two_devices()
    main.AUTH_REQUIRED = True
    client = TestClient(app)
    a = list(sessions.devices.values())[0]
    r = client.post(f"/devices/{a.id}/revoke",
                    headers=_signed(a.id, "secA", "POST", f"/devices/{a.id}/revoke", "n-self"))
    main.AUTH_REQUIRED = False
    assert r.status_code == 200, r.text
    assert r.json() == {"revoked": a.id}
    assert sessions.devices[a.id].revoked is True


def test_revoke_other_device_requires_owner():
    a, b = _two_devices()
    main.AUTH_REQUIRED = True
    client = TestClient(app)
    # PhoneB is trusted but not the owner: revoking PhoneA must fail.
    r = client.post(f"/devices/{a.id}/revoke",
                    headers=_signed(b.id, "secB", "POST", f"/devices/{a.id}/revoke", "n-other"))
    assert r.status_code == 403, r.text
    assert sessions.devices[a.id].revoked is False
    # The owner can revoke another device.
    r = client.post(f"/devices/{b.id}/revoke",
                    headers=_signed(a.id, "secA", "POST", f"/devices/{b.id}/revoke", "n-owner"))
    main.AUTH_REQUIRED = False
    assert r.status_code == 200, r.text
    assert sessions.devices[b.id].revoked is True


def test_revoke_unknown_device_404s():
    main.AUTH_REQUIRED = False
    client = TestClient(app)
    r = client.post("/devices/dev_nope/revoke")
    assert r.status_code == 404
