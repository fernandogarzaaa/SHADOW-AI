"""Regression tests for WebSocket handshake authentication (audit P0-1).

The HTTP auth middleware does not run for websocket routes, so
/ws/tasks verifies the HMAC handshake itself and closes with 4401
before accept when the signature is missing or invalid.
"""
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_core import sign_request


@pytest.fixture
def api(monkeypatch):
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", True)
    return TestClient(m.app), m


def _headers(m, nonce="wstest", secret=None, device_id=None):
    if device_id is None:
        dev = m.sessions.register("ws-test", "ws-pubkey-" + nonce)
        device_id, secret = dev.id, m.sessions.secrets[dev.id]
    ts = int(time.time())
    return {"x-shadow-device-id": device_id, "x-shadow-nonce": nonce,
            "x-shadow-timestamp": str(ts),
            "x-shadow-signature": sign_request(secret, "GET", "/ws/tasks", "", nonce, ts)}


def test_ws_rejects_missing_credentials(api):
    client, m = api
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/tasks"):
            pass
    assert exc.value.code == 4401


def test_ws_rejects_bad_signature(api):
    client, m = api
    h = _headers(m, nonce="wsbad")
    h["x-shadow-signature"] = "bad"
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/tasks", headers=h):
            pass
    assert exc.value.code == 4401


def test_ws_rejects_replayed_nonce(api):
    client, m = api
    dev = m.sessions.register("ws-replay", "ws-pubkey-replay")
    secret = m.sessions.secrets[dev.id]
    h = _headers(m, nonce="wsreplay", secret=secret, device_id=dev.id)
    with client.websocket_connect("/ws/tasks", headers=h) as ws:
        assert ws.receive_json()["type"] == "hello"
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/tasks", headers=h):
            pass
    assert exc.value.code == 4401


def test_ws_accepts_signed_handshake_and_echoes(api):
    client, m = api
    with client.websocket_connect("/ws/tasks", headers=_headers(m, nonce="wsok")) as ws:
        assert ws.receive_json()["type"] == "hello"
        ws.send_json({"ping": 1})
        ack = ws.receive_json()
        assert ack["type"] == "ack" and ack["received"] == {"ping": 1}


def test_ws_open_when_auth_disabled(monkeypatch):
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    with TestClient(m.app).websocket_connect("/ws/tasks") as ws:
        assert ws.receive_json()["type"] == "hello"
