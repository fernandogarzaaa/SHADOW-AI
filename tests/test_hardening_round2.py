"""Second hardening pass: consent provenance, audit durability, streaming
body cap, rate-limit keying, secret file permissions, and the Anthropic
provider's stop_reason / retry handling."""
import os
import stat
import time
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    return TestClient(m.app), m


# --- consent comes only from a verified approval -----------------------------

def test_consent_tool_without_approval_gets_no_consent(client, monkeypatch):
    """Even when policy would let calendar.create run (autonomous mode),
    the explicit-consent flag is never manufactured: no approval, no
    consent, the executor refuses."""
    c, m = client
    seen = []
    real_run = m.action_executor.run

    def spy(tool, params, explicit_consent=False):
        seen.append(explicit_consent)
        return real_run(tool, params, explicit_consent=explicit_consent)

    monkeypatch.setattr(m.action_executor, "run", spy)
    handler = m.core.tools._tools["calendar.create"]
    out = handler({"title": "x", "start": "2026-11-01T10:00:00"})
    assert seen == [False]
    assert out["ok"] is False and out["reason"] == "explicit_consent_required"


def test_consent_is_granted_inside_approved_execute(client, monkeypatch):
    c, m = client
    seen = []
    monkeypatch.setattr(m.action_executor, "run",
                        lambda tool, params, explicit_consent=False: seen.append(explicit_consent) or {"ok": True})
    token = m._execution_consent.set(True)
    try:
        m.core.tools._tools["calendar.create"]({"title": "x"})
    finally:
        m._execution_consent.reset(token)
    assert seen == [True]


# --- audit durability ---------------------------------------------------------

def test_audit_events_survive_repeated_reads(client):
    c, m = client
    m.core.audit.append(m.AuditEvent(actor="agent_core", event_type="probe_" + uuid.uuid4().hex[:6]))
    marker = m.core.audit[-1].event_type
    first = c.get("/audit?limit=1000").json()
    second = c.get("/audit?limit=1000").json()
    assert any(e["event_type"] == marker for e in first["items"])
    assert any(e["event_type"] == marker for e in second["items"])
    assert set(first) == {"items", "count", "next_cursor"}


def test_audit_filter_and_limit(client):
    c, m = client
    c.post("/emergency_pause", json={"paused": False, "reason": "t"})
    page = c.get("/audit?event_type=emergency_pause&limit=1").json()
    assert len(page["items"]) == 1 and page["count"] >= 1
    assert page["items"][0]["event_type"] == "emergency_pause"


def test_approval_records_decider(client):
    c, m = client
    act = {"tool_name": "note.create", "description": "n", "params": {"title": "t", "body": "b"}}
    rid = c.post("/approvals", json={"action": act}).json()["id"]
    c.post(f"/approvals/{rid}/approve", headers={"x-shadow-device-id": "dev_abc"})
    ev = [e for e in c.get("/audit?event_type=approval_approved&limit=1000").json()["items"]
          if e["metadata"].get("approval_id") == rid]
    assert ev and ev[0]["metadata"]["approved_by"] == "dev_abc"


# --- streaming body cap -------------------------------------------------------

def test_chunked_body_over_limit_rejected():
    from shadow_node.request_hygiene import BodyLimitMiddleware
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def echo(request):
        return JSONResponse({"n": len(await request.body())})

    app = BodyLimitMiddleware(Starlette(routes=[Route("/", echo, methods=["POST"])]), max_bytes=10)
    tc = TestClient(app)

    def chunks():
        for _ in range(5):
            yield b"abcdef"

    r = tc.post("/", content=chunks())  # generator -> chunked, no Content-Length
    assert r.status_code == 413
    assert tc.post("/", content=b"small").json() == {"n": 5}


# --- rate-limit keying ---------------------------------------------------------

def test_rate_limit_key_ignores_unverified_header():
    from shadow_node.obs import client_key
    req = SimpleNamespace(headers={"x-shadow-device-id": "spoofed"}, state=SimpleNamespace(),
                          client=SimpleNamespace(host="10.1.2.3"))
    assert client_key(req) == "ip:10.1.2.3"
    req.state.device_id = "dev_real"
    assert client_key(req) == "dev:dev_real"


# --- secret files ---------------------------------------------------------------

def test_secret_files_created_0600(tmp_path, monkeypatch):
    from shadow_node.crypto_config import load_fernet_key, write_secret_file
    monkeypatch.delenv("X_KEY", raising=False)
    old = os.umask(0o022)
    try:
        load_fernet_key("X_KEY", "X_KEY_FILE", str(tmp_path / "k" / "x.key"))
        write_secret_file(tmp_path / "s.bin", b"secret")
    finally:
        os.umask(old)
    for p in (tmp_path / "k" / "x.key", tmp_path / "s.bin"):
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".*.tmp"))


def test_key_dir_follows_shadow_data_dir(monkeypatch, tmp_path):
    from shadow_node.crypto_config import key_path
    monkeypatch.setenv("SHADOW_DATA_DIR", str(tmp_path))
    assert key_path("master.key") == str(tmp_path / "keys" / "master.key")


# --- Anthropic provider ------------------------------------------------------------

def _resp(status, json_body=None, headers=None):
    return httpx.Response(status, json=json_body or {}, headers=headers or {},
                          request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


def _provider(monkeypatch, responses, **kw):
    from shadow_node import model_providers as mp
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"headers": headers, "json": json})
        return responses.pop(0)

    monkeypatch.setattr(mp.httpx, "post", fake_post)
    monkeypatch.setattr(mp.time, "sleep", lambda s: None)
    monkeypatch.setattr(mp, "get_system_prompt", lambda: "sys")
    return mp.AnthropicProvider("sk-test", "", **kw), calls, mp


def test_anthropic_defaults_and_fallback_opt_in(monkeypatch):
    p, calls, mp = _provider(monkeypatch, [_resp(200, {"stop_reason": "end_turn",
                                                       "content": [{"type": "text", "text": "hi"}]})])
    assert p.complete("q") == "hi"
    body = calls[0]["json"]
    assert body["model"] == mp.DEFAULT_ANTHROPIC_MODEL == "claude-opus-5-5"
    assert body["max_tokens"] >= 4096
    assert body["fallbacks"] == "default"
    assert calls[0]["headers"]["anthropic-beta"] == mp.AnthropicProvider.FALLBACK_BETA
    assert "temperature" not in body


def test_anthropic_custom_endpoint_omits_beta(monkeypatch):
    p, calls, _ = _provider(monkeypatch, [_resp(200, {"stop_reason": "end_turn",
                                                      "content": [{"type": "text", "text": "ok"}]})],
                            endpoint="https://gateway.internal/v1/messages")
    p.complete("q")
    assert "fallbacks" not in calls[0]["json"]
    assert "anthropic-beta" not in calls[0]["headers"]


def test_anthropic_retries_429_and_529(monkeypatch):
    ok = _resp(200, {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]})
    p, calls, _ = _provider(monkeypatch, [_resp(429, headers={"retry-after": "1"}), _resp(529), ok])
    assert p.complete("q") == "done"
    assert len(calls) == 3


def test_anthropic_refusal_raises(monkeypatch):
    p, _, mp = _provider(monkeypatch, [_resp(200, {"stop_reason": "refusal", "content": [],
                                                   "stop_details": {"category": "cyber"}})])
    with pytest.raises(mp.ModelResponseError, match="cyber"):
        p.complete("q")


def test_anthropic_max_tokens_is_marked(monkeypatch):
    p, _, _ = _provider(monkeypatch, [_resp(200, {"stop_reason": "max_tokens",
                                                  "content": [{"type": "text", "text": "partial"}]})])
    assert p.complete("q").endswith("[response truncated: max_tokens reached]")


def test_anthropic_http_error_raises(monkeypatch):
    p, _, mp = _provider(monkeypatch, [_resp(400, {"error": {"message": "bad model"}})])
    with pytest.raises(mp.ModelResponseError, match="bad model"):
        p.complete("q")


def test_cloud_failure_is_reported_not_disguised(monkeypatch):
    """A failing cloud call must not come back as the mock's canned answer."""
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    monkeypatch.setattr(m.core.policy, "cloud_allowed", lambda *a, **k: True)
    monkeypatch.setattr(m.credentials, "resolve", lambda provider: {"api_key": "sk"})

    class Boom:
        name = "anthropic"

        def complete(self, prompt, context=""):
            raise RuntimeError("upstream exploded")

    monkeypatch.setattr(m, "build_frontier", lambda *a, **k: Boom())
    r = TestClient(m.app).post("/agent/ask", json={"prompt": "summarize everything",
                                                  "allow_cloud": True, "cloud_approval": True})
    body = r.json()
    assert r.status_code == 200 and body["degraded"] is True
    assert body["error"] == "cloud_model_error"
    assert "Local mock answer" not in body["answer"]
    assert "upstream exploded" in body["answer"]
