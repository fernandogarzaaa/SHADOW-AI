"""Subscription providers: ChatGPT plan (Sign in with ChatGPT) and the
experimental Claude Code delegate. No network: OpenAI is faked, ID tokens
are signed with a throwaway RSA key, and `claude` is a stub script."""
import base64
import hashlib
import json
import os
import stat
import sys
import time
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from shadow_node import chatgpt_plan as cp
from shadow_node.provider_auth import CredentialStore

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_id_token(claims: dict, kid="k1", key=KEY) -> str:
    header = b64u(json.dumps({"alg": "RS256", "kid": kid}).encode())
    payload = b64u(json.dumps(claims).encode())
    sig = key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{b64u(sig)}"


def jwk(key=KEY, kid="k1"):
    n = key.public_key().public_numbers()
    return {"kty": "RSA", "kid": kid, "n": b64u(n.n.to_bytes((n.n.bit_length() + 7) // 8, "big")),
            "e": b64u(n.e.to_bytes(3, "big"))}


class Resp:
    def __init__(self, status=200, body=None, lines=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self._lines = lines or []

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_lines(self):
        yield from self._lines

    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpenAI:
    """Just enough of auth.openai.com + api.openai.com."""

    def __init__(self):
        self.posts = []
        self.token_responses = []
        self.stream_lines = []
        self.stream_status = 200
        self.models = {"models": [{"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "visibility": "list"},
                                  {"slug": "hidden", "display_name": "x", "visibility": "hide"}]}

    def get(self, url, headers=None, timeout=None):
        if url == cp.DISCOVERY_URL:
            return Resp(body={"issuer": cp.ISSUER, "jwks_uri": "https://auth.openai.com/jwks",
                              "revocation_endpoint": "https://auth.openai.com/revoke"})
        if url.endswith("/jwks"):
            return Resp(body={"keys": [jwk()]})
        if url.endswith("/models"):
            return Resp(body=self.models)
        raise AssertionError(url)

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, dict(data or {})))
        if url.endswith("/revoke"):
            return Resp(200)
        return self.token_responses.pop(0)

    def stream(self, method, url, json=None, headers=None, timeout=None):
        self.last_request = {"url": url, "json": json, "headers": headers}
        return Resp(self.stream_status, body={"error": {"code": "subscription_sharing_usage_limit_exceeded"}},
                    lines=self.stream_lines)


def sse(*events):
    out = []
    for e in events:
        out += [f"data: {json.dumps(e)}", ""]
    return out


@pytest.fixture(autouse=True)
def _fresh_jwks():
    cp._jwks_cache.update(at=0.0, keys={}, discovery=None)


@pytest.fixture
def auth(tmp_path):
    from cryptography.fernet import Fernet
    store = CredentialStore(path=str(tmp_path / "p.enc"), key=Fernet.generate_key())
    fake = FakeOpenAI()
    return cp.ChatGPTPlanAuth(store, http_client=fake), fake


def _sign_in(auth_fake, plan=True, aud=None, nonce=None, kid="k1", key=KEY):
    a, fake = auth_fake
    start = a.start(8787, "dev_1")
    q = parse_qs(urlparse(start["authorization_url"]).query)
    claims = {"iss": cp.ISSUER, "aud": aud or "client_abc", "exp": time.time() + 600,
              "nonce": nonce or q["nonce"][0], "sub": "user-1", "email": "me@example.com"}
    scope = cp.SCOPES if plan else "openid profile email offline_access"
    fake.token_responses.append(Resp(body={"access_token": "at-1", "refresh_token": "rt-1",
                                           "id_token": make_id_token(claims, kid=kid, key=key),
                                           "expires_in": 3600, "scope": scope, "token_type": "Bearer"}))
    return a.complete(q["state"][0], "code-1", "client_abc", scope), q


# --- sign-in ------------------------------------------------------------------------------

def test_authorization_url_follows_siwc(auth):
    a, _ = auth
    start = a.start(8787, None)
    url = urlparse(start["authorization_url"])
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == cp.AUTHORIZE_URL
    assert q["client_id"] == "dynamic_agent_client" and q["agent_name_hint"] == "Shadow"
    assert q["redirect_uri"] == "http://127.0.0.1:8787/auth/callback"  # never localhost
    assert q["scope"] == cp.SCOPES and q["resource"] == "https://api.openai.com/v1"
    assert q["code_challenge_method"] == "S256" and q["response_type"] == "code"
    assert q["ext_agent_host_id"].startswith("urn:uuid:")
    assert a.host_id() == q["ext_agent_host_id"]  # stable per node
    verifier = a._txns[q["state"]]["verifier"]
    assert q["code_challenge"] == b64u(hashlib.sha256(verifier.encode()).digest())


def test_sign_in_verifies_and_stores(auth):
    info, _ = _sign_in(auth)
    a, fake = auth
    assert info == {"email": "me@example.com", "plan_usage": True, "return_to": "http://127.0.0.1:8787"}
    rec = a.credentials.get(cp.PROVIDER)
    assert rec["client_id"] == "client_abc" and rec["access_token"] == "at-1" and rec["plan_usage"]
    url, data = fake.posts[0]
    assert url == cp.TOKEN_URL and data["grant_type"] == "authorization_code"
    assert data["client_id"] == "client_abc" and data["resource"] == cp.RESOURCE and "code_verifier" in data


def test_state_is_single_use(auth):
    _, q = _sign_in(auth)
    a, _ = auth
    with pytest.raises(cp.ChatGPTPlanError, match="expired or was already used"):
        a.complete(q["state"][0], "code-1", "client_abc", cp.SCOPES)


@pytest.mark.parametrize("kwargs,match", [
    ({"aud": "someone-else"}, "different app"),
    ({"nonce": "wrong"}, "nonce"),
    ({"key": rsa.generate_private_key(public_exponent=65537, key_size=2048)}, "bad signature"),
    ({"kid": "unknown"}, "unknown signing key"),
])
def test_id_token_checks(auth, kwargs, match):
    with pytest.raises(cp.ChatGPTPlanError, match=match):
        _sign_in(auth, **kwargs)
    assert auth[0].credentials.get(cp.PROVIDER) is None  # nothing activated


def test_plan_usage_not_granted_is_explicit(auth):
    info, _ = _sign_in(auth, plan=False)
    assert info["plan_usage"] is False
    with pytest.raises(cp.ChatGPTPlanError) as e:
        auth[0].access_token()
    assert e.value.code == "plan_usage_not_granted"


def test_reauthorization_reuses_registration(auth):
    _sign_in(auth)
    q = parse_qs(urlparse(auth[0].start(8787, None)["authorization_url"]).query)
    assert q["client_id"] == ["client_abc"] and "agent_name_hint" not in q
    assert q["login_hint"] == ["me@example.com"] and "id_token_hint" in q


# --- tokens ---------------------------------------------------------------------------------

def test_refresh_rotates_tokens(auth):
    _sign_in(auth)
    a, fake = auth
    rec = a.credentials.get(cp.PROVIDER)
    rec["expires_at"] = time.time() + 30  # inside the refresh margin
    a.credentials.set(cp.PROVIDER, rec)
    fake.token_responses.append(Resp(body={"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600}))
    assert a.access_token() == "at-2"
    url, data = fake.posts[-1]
    assert data == {"grant_type": "refresh_token", "client_id": "client_abc", "refresh_token": "rt-1",
                    "resource": cp.RESOURCE}
    assert a.credentials.get(cp.PROVIDER)["refresh_token"] == "rt-2"


def test_failed_refresh_requires_reauth(auth):
    _sign_in(auth)
    a, fake = auth
    rec = a.credentials.get(cp.PROVIDER)
    rec["expires_at"] = 0
    a.credentials.set(cp.PROVIDER, rec)
    fake.token_responses.append(Resp(400, {"error": "invalid_grant"}))
    with pytest.raises(cp.ChatGPTPlanError) as e:
        a.access_token()
    assert e.value.code == "reauth_required"


def test_sign_out_revokes_and_keeps_registration(auth):
    _sign_in(auth)
    a, fake = auth
    assert a.sign_out() == {"revoked": True}
    url, data = fake.posts[-1]
    assert url.endswith("/revoke") and data["token"] == "rt-1" and data["token_type_hint"] == "refresh_token"
    rec = a.credentials.get(cp.PROVIDER)
    assert rec["client_id"] == "client_abc" and "access_token" not in rec and "refresh_token" not in rec


def test_models_filtered_to_listed(auth):
    _sign_in(auth)
    assert auth[0].models() == [{"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol"}]


# --- inference ----------------------------------------------------------------------------

def test_responses_stream_and_body_shape(auth):
    _sign_in(auth)
    a, fake = auth
    fake.stream_lines = sse({"type": "response.output_text.delta", "delta": "Hel"},
                            {"type": "response.output_text.delta", "delta": "lo"},
                            {"type": "response.completed"})
    out = cp.ChatGPTPlanProvider(a, "gpt-6.1-sol", http_client=fake).complete("hi", "ctx")
    assert out == "Hello"
    body = fake.last_request["json"]
    assert body["store"] is False and body["stream"] is True and body["model"] == "gpt-6.1-sol"
    assert "instructions" in body and all(i["role"] != "system" for i in body["input"])
    for unsupported in ("temperature", "top_p", "max_output_tokens", "previous_response_id", "metadata"):
        assert unsupported not in body
    assert fake.last_request["headers"]["Authorization"] == "Bearer at-1"


def test_usage_limit_mid_stream_is_reported(auth):
    _sign_in(auth)
    a, fake = auth
    fake.stream_lines = sse({"type": "response.output_text.delta", "delta": "par"},
                            {"type": "response.failed",
                             "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}}})
    with pytest.raises(cp.ChatGPTPlanError) as e:
        cp.ChatGPTPlanProvider(a, "m", http_client=fake).complete("hi")
    assert e.value.code == "subscription_sharing_usage_limit_exceeded"
    assert "usage limit" in str(e.value)


def test_http_429_plan_limit(auth):
    _sign_in(auth)
    a, fake = auth
    fake.stream_status = 429
    with pytest.raises(cp.ChatGPTPlanError) as e:
        cp.ChatGPTPlanProvider(a, "m", http_client=fake).complete("hi")
    assert e.value.code == "subscription_sharing_usage_limit_exceeded"


def test_stream_without_completed_is_a_failure(auth):
    _sign_in(auth)
    a, fake = auth
    fake.stream_lines = sse({"type": "response.output_text.delta", "delta": "partial"})
    with pytest.raises(cp.ChatGPTPlanError) as e:
        cp.ChatGPTPlanProvider(a, "m", http_client=fake).complete("hi")
    assert e.value.code == "interrupted"


# --- node API -----------------------------------------------------------------------------

@pytest.fixture
def node(monkeypatch, tmp_path):
    import shadow_node.main as m
    from cryptography.fernet import Fernet
    store = CredentialStore(path=str(tmp_path / "node.enc"), key=Fernet.generate_key())
    fake = FakeOpenAI()
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    monkeypatch.setattr(m, "credentials", store)
    monkeypatch.setattr(m, "chatgpt_auth", cp.ChatGPTPlanAuth(store, http_client=fake))
    return TestClient(m.app), m, fake


def test_status_lists_subscriptions_with_disclosures(node):
    c, m, _ = node
    subs = c.get("/providers").json()["subscriptions"]
    assert subs["chatgpt_plan"]["connected"] is False
    assert subs["chatgpt_plan"]["manage_usage_url"] == "https://chatgpt.com/settings/usage"
    assert "never sees or stores your Claude login" in subs["claude_code"]["disclosure"]
    assert "prohibit" in subs["gemini"]["note"]


def test_signin_route_uses_loopback(node):
    c, m, _ = node
    r = c.post("/providers/chatgpt_plan/signin", json={"port": 8787}).json()
    assert r["redirect_uri"] == "http://127.0.0.1:8787/auth/callback"
    assert r["authorization_url"].startswith(cp.AUTHORIZE_URL)


def test_callback_rejects_unknown_state(node, monkeypatch):
    c, m, _ = node
    monkeypatch.setattr(m, "AUTH_REQUIRED", True)  # the callback is public by design
    r = c.get("/auth/callback?state=nope&code=x")
    assert r.status_code == 200 and "Not connected" in r.text and "expired" in r.text
    assert "script-src 'self'" in r.headers["content-security-policy"]


def test_callback_completes_sign_in(node):
    c, m, fake = node
    start = m.chatgpt_auth.start(8787, None)
    q = parse_qs(urlparse(start["authorization_url"]).query)
    claims = {"iss": cp.ISSUER, "aud": "client_abc", "exp": time.time() + 600, "nonce": q["nonce"][0],
              "sub": "u", "email": "me@example.com"}
    fake.token_responses.append(Resp(body={"access_token": "at", "refresh_token": "rt",
                                           "id_token": make_id_token(claims), "expires_in": 3600,
                                           "scope": cp.SCOPES}))
    r = c.get(f"/auth/callback?state={q['state'][0]}&code=c&client_id=client_abc&scope={cp.SCOPES}")
    assert "using your ChatGPT plan" in r.text and "Connected" in r.text
    assert c.get("/providers").json()["subscriptions"]["chatgpt_plan"]["connected"] is True


def test_activate_requires_connected_provider(node):
    c, m, _ = node
    assert c.post("/providers/active", json={"provider": "chatgpt_plan"}).status_code == 409
    assert c.post("/providers/active", json={"provider": "local_mock"}).json()["active_provider"] == "local_mock"


def test_plan_failure_never_falls_back_to_api_key(node, monkeypatch):
    """With ChatGPT plan active and an OpenAI API key also configured, a plan
    limit error must surface (with Manage usage), not silently bill the key."""
    c, m, fake = node
    m.credentials.set("openai", {"type": "api_key", "api_key": "sk-test", "source": "stored"})
    m.credentials.set(cp.PROVIDER, {"type": "chatgpt_plan", "access_token": "at", "refresh_token": "rt",
                                     "client_id": "client_abc", "expires_at": time.time() + 3600,
                                     "plan_usage": True, "model": "gpt-6.1-sol"})
    m.credentials.set("_active", {"provider": "chatgpt_plan"})
    monkeypatch.setattr(m.core.policy, "cloud_allowed", lambda *a, **k: True)
    calls = []
    monkeypatch.setattr(m, "build_frontier", lambda *a, **k: calls.append(a) or None)
    fake.stream_status = 429
    monkeypatch.setattr(cp.httpx, "stream", fake.stream)
    r = c.post("/agent/ask", json={"prompt": "summarize my plans", "allow_cloud": True, "cloud_approval": True}).json()
    assert r["degraded"] is True and r["error"] == "subscription_sharing_usage_limit_exceeded"
    assert r["manage_usage_url"] == "https://chatgpt.com/settings/usage"
    assert "usage limit" in r["answer"]
    assert calls == []  # the API-key provider was never built


def test_chatgpt_answer_reports_billing(node, monkeypatch):
    c, m, fake = node
    m.credentials.set(cp.PROVIDER, {"type": "chatgpt_plan", "access_token": "at", "refresh_token": "rt",
                                     "client_id": "client_abc", "expires_at": time.time() + 3600,
                                     "plan_usage": True, "model": "gpt-6.1-sol"})
    m.credentials.set("_active", {"provider": "chatgpt_plan"})
    monkeypatch.setattr(m.core.policy, "cloud_allowed", lambda *a, **k: True)
    fake.stream_lines = sse({"type": "response.output_text.delta", "delta": "From your plan."},
                            {"type": "response.completed"})
    monkeypatch.setattr(cp.httpx, "stream", fake.stream)
    r = c.post("/agent/ask", json={"prompt": "hello there", "allow_cloud": True, "cloud_approval": True}).json()
    assert r["answer"] == "From your plan." and r["billing"] == "chatgpt_plan"


def test_disconnect_route_revokes_chatgpt(node):
    c, m, fake = node
    _sign_in((m.chatgpt_auth, fake))
    r = c.delete("/providers/chatgpt_plan").json()
    assert r["remote_revocation_confirmed"] is True
    assert any(u.endswith("/revoke") for u, _ in fake.posts)


# --- Claude Code delegate -------------------------------------------------------------------

@pytest.fixture
def stub_claude(tmp_path, monkeypatch):
    """A fake `claude` that records its argv, cwd and env, then answers."""
    log = tmp_path / "calls.jsonl"
    script = tmp_path / "claude"
    script.write_text(f"""#!{sys.executable}
import json, os, sys
if "--version" in sys.argv:
    print("2.1.400 (Claude Code)"); sys.exit(0)
with open({str(log)!r}, "a") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(),
                         "env_keys": sorted(k for k in os.environ if k.startswith(("ANTHROPIC", "CLAUDE_CODE")))}}) + "\\n")
mode = os.environ.get("STUB_MODE", "ok")
if mode == "login":
    print(json.dumps({{"is_error": True, "result": "Invalid API key · Please run /login"}})); sys.exit(1)
print(json.dumps({{"type": "result", "is_error": False, "result": "Answer from your Claude Code."}}))
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("SHADOW_CLAUDE_BIN", str(script))
    monkeypatch.setenv("SHADOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "should-not-leak")
    monkeypatch.delenv("SHADOW_DISABLE_CLAUDE_CODE", raising=False)
    return log


def test_claude_code_runs_isolated(stub_claude, tmp_path):
    from shadow_node import claude_code
    out = claude_code.ClaudeCodeProvider(system_prompt="be brief").complete("what's up?", "ctx")
    assert out == "Answer from your Claude Code."
    call = json.loads(stub_claude.read_text().splitlines()[-1])
    assert call["env_keys"] == []  # API key / OAuth token stripped from the child
    assert call["cwd"].endswith("claude-code-sandbox")
    assert "-p" in call["argv"] and "--output-format" in call["argv"]
    assert "--mcp-config" not in call["argv"]
    disallowed = call["argv"][call["argv"].index("--disallowedTools") + 1]
    for tool in ("Bash", "Edit", "Write", "WebFetch"):
        assert tool in disallowed


def test_claude_code_not_signed_in(stub_claude, monkeypatch):
    from shadow_node import claude_code
    monkeypatch.setenv("STUB_MODE", "login")
    with pytest.raises(claude_code.ClaudeCodeError) as e:
        claude_code.ClaudeCodeProvider().complete("hi")
    assert e.value.code == "not_signed_in"


def test_claude_code_enable_requires_ack_and_respects_kill_switch(node, stub_claude, monkeypatch):
    c, m, _ = node
    assert c.post("/providers/claude_code/enable", json={}).status_code == 400
    r = c.post("/providers/claude_code/enable", json={"acknowledge": True}).json()
    assert r["enabled"] is True and r["version"] == "2.1.400"
    assert c.post("/providers/active", json={"provider": "claude_code"}).status_code == 200
    monkeypatch.setenv("SHADOW_DISABLE_CLAUDE_CODE", "true")
    assert c.get("/providers").json()["subscriptions"]["claude_code"]["enabled"] is False
    assert m._build_active_frontier("claude_code") is None  # kill switch wins
    assert c.post("/providers/claude_code/enable", json={"acknowledge": True}).status_code == 403
    monkeypatch.delenv("SHADOW_DISABLE_CLAUDE_CODE")
    c.delete("/providers/claude_code")
    assert c.get("/providers").json()["active_provider"] != "claude_code"


@pytest.mark.parametrize("origin,expected", [
    ("http://localhost:8787", "http://localhost:8787"),
    ("http://127.0.0.1:8787", "http://127.0.0.1:8787"),
    ("https://evil.example", "http://127.0.0.1:8787"),
    ("http://localhost:8787/phish", "http://127.0.0.1:8787"),
    (None, "http://127.0.0.1:8787"),
])
def test_return_to_only_loopback(origin, expected):
    assert cp._safe_return_to(origin, 8787) == expected
