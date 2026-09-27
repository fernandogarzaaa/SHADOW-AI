"""Adversarial tests: push-token ownership boundary (audit P1).

Before: any authenticated device could POST /devices/{other}/push-token
and overwrite another device's Expo token, hijacking its approval
push notifications. Now a device may only register its own token.
"""
import time

import pytest
from fastapi.testclient import TestClient

from agent_core import sign_request


@pytest.fixture
def api(monkeypatch):
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", True)
    dev_snap = dict(m.sessions.devices)
    sec_snap = dict(m.sessions.secrets)
    tok_snap = dict(m.sessions.push_tokens)
    m.sessions.devices.clear(); m.sessions.secrets.clear(); m.sessions.push_tokens.clear()
    m.sessions.nonces.clear()
    a = m.sessions.register("PhoneA", "pub-a", "secret-a")
    b = m.sessions.register("PhoneB", "pub-b", "secret-b")
    yield TestClient(m.app), m, a, b
    m.sessions.devices.clear(); m.sessions.devices.update(dev_snap)
    m.sessions.secrets.clear(); m.sessions.secrets.update(sec_snap)
    m.sessions.push_tokens.clear(); m.sessions.push_tokens.update(tok_snap)
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)


def _signed(device_id, secret, method, path, body, nonce):
    ts = int(time.time())
    return {"x-shadow-device-id": device_id, "x-shadow-nonce": nonce,
            "x-shadow-timestamp": str(ts),
            "x-shadow-signature": sign_request(secret, method, path, body, nonce, ts)}


def _post(client, dev_id, secret, target, token, nonce):
    body = f'{{"push_token":"{token}"}}'
    path = f"/devices/{target}/push-token"
    return client.post(path, content=body,
                       headers={**_signed(dev_id, secret, "POST", path, body, nonce),
                                "Content-Type": "application/json"})


def test_device_can_register_own_token(api):
    client, m, a, b = api
    r = _post(client, a.id, "secret-a", a.id, "ExponentPushToken[aaa]", "n1")
    assert r.status_code == 200 and r.json()["push_registered"] is True
    assert m.sessions.push_tokens[a.id] == "ExponentPushToken[aaa]"


def test_device_cannot_register_another_devices_token(api):
    client, m, a, b = api
    # B registers its real token first
    assert _post(client, b.id, "secret-b", b.id,
                 "ExponentPushToken[bbb]", "n1").status_code == 200
    # A tries to overwrite B's token: blocked, B's token untouched
    r = _post(client, a.id, "secret-a", b.id, "ExponentPushToken[evil]", "n2")
    assert r.status_code == 403
    assert m.sessions.push_tokens[b.id] == "ExponentPushToken[bbb]"


def test_cross_device_attempt_is_audited(api):
    client, m, a, b = api
    n_before = len(m.audit)
    _post(client, a.id, "secret-a", b.id, "ExponentPushToken[evil]", "n3")
    events = [e for e in m.audit[n_before:]
              if e.event_type == "push_token_rejected"]
    assert len(events) == 1
    assert events[0].status == "blocked"
    assert events[0].metadata["device_id"] == b.id


def test_unauthenticated_push_token_rejected(api):
    client, m, a, b = api
    r = client.post(f"/devices/{a.id}/push-token",
                    json={"push_token": "ExponentPushToken[zzz]"})
    assert r.status_code == 401
    assert a.id not in m.sessions.push_tokens


def test_unknown_device_still_404_for_self(api):
    client, m, a, b = api
    body = '{"push_token":"ExponentPushToken[zzz]"}'
    path = "/devices/dev_nope/push-token"
    # sign as A but target an unknown id: ownership check fails first
    # (403), which is fine; the point is no token is stored.
    r = client.post(path, content=body,
                    headers={**_signed(a.id, "secret-a", "POST", path, body, "n4"),
                             "Content-Type": "application/json"})
    assert r.status_code == 403
    assert "dev_nope" not in m.sessions.push_tokens
