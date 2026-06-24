"""Hybrid local+frontier routing, token savings, providers, and credentials."""
import importlib
import pytest
from fastapi.testclient import TestClient

from shadow_node.hybrid import HybridRouter, ComplexityRouter
from shadow_node.model_providers import LocalMockModel
from shadow_node.providers import build_frontier, CATALOG, OpenAIProvider, GeminiProvider
from shadow_node import provider_auth


class FakeFrontier:
    name = "fake_frontier"
    cloud = True
    def __init__(self): self.seen_context = None
    def complete(self, prompt, context=""):
        self.seen_context = context
        return f"FRONTIER:{prompt}"


def test_router_keeps_simple_queries_local():
    r = ComplexityRouter()
    d = r.decide("what time is it?", context_tokens=10, frontier_available=True)
    assert d.route == "local"


def test_router_sends_hard_queries_to_frontier():
    r = ComplexityRouter()
    d = r.decide("analyze and compare the strategy trade-offs across these documents", 800, frontier_available=True)
    assert d.route == "frontier"


def test_router_stays_local_when_no_frontier():
    r = ComplexityRouter()
    assert r.decide("design a full architecture and explain why", 900, frontier_available=False).route == "local"


def test_hybrid_local_shortcircuit_saves_all_context_tokens():
    h = HybridRouter(LocalMockModel())
    out = h.run("hi?", "some retrieved memory context here", frontier=None)
    assert out["route"] == "local"
    assert out["provider"] == "local_mock"
    assert out["savings"]["frontier_tokens_sent"] == 0
    assert out["savings"]["tokens_saved_estimate"] == out["savings"]["raw_context_tokens"]


def test_hybrid_frontier_receives_compressed_context_and_reports_savings():
    big_context = ("Project Aurora detail. " * 400)  # large raw context
    fake = FakeFrontier()
    h = HybridRouter(LocalMockModel())
    out = h.run("analyze and summarize the strategy across Aurora", big_context, frontier=fake)
    assert out["route"] == "frontier" and out["provider"] == "fake_frontier"
    # The frontier saw compressed context, not the full raw text.
    assert len(fake.seen_context) < len(big_context)
    s = out["savings"]
    assert s["compressed_context_tokens"] <= s["raw_context_tokens"]
    assert s["tokens_saved_estimate"] >= 0 and s["saved_pct"] >= 0


def test_build_frontier_requires_credential():
    assert build_frontier("openai", None) is None
    assert build_frontier("openai", {}) is None
    p = build_frontier("openai", {"api_key": "sk-x"})
    assert isinstance(p, OpenAIProvider)
    g = build_frontier("gemini", {"oauth_token": "ya29.x"})
    assert isinstance(g, GeminiProvider) and g.oauth_token == "ya29.x"


def test_credential_store_resolves_env_and_stored(monkeypatch, tmp_path):
    monkeypatch.setenv("SHADOW_PROVIDERS_FILE", str(tmp_path / "p.enc"))
    monkeypatch.setenv("SHADOW_PROVIDERS_KEY_FILE", str(tmp_path / "p.key"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cs = provider_auth.CredentialStore()
    assert cs.resolve("anthropic") is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert cs.resolve("anthropic")["source"] == "env"
    cs.set("anthropic", {"type": "api_key", "api_key": "sk-stored", "source": "stored"})
    assert cs.resolve("anthropic")["api_key"] == "sk-stored"  # stored wins
    statuses = {s["provider"]: s for s in cs.status()}
    assert statuses["anthropic"]["connected"] and statuses["anthropic"]["subscription_oauth"] is False


def test_oauth_start_requires_client_id_and_only_supported_providers(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    with pytest.raises(ValueError):
        provider_auth.start_oauth("gemini", "http://127.0.0.1:8787/cb")   # no client id
    with pytest.raises(ValueError):
        provider_auth.start_oauth("anthropic", "http://127.0.0.1:8787/cb")  # unsupported
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    res = provider_auth.start_oauth("gemini", "http://127.0.0.1:8787/cb")
    assert res["authorization_url"].startswith("https://accounts.google.com/")
    assert "code_challenge=" in res["authorization_url"] and res["code_verifier"] and res["state"]


def test_providers_endpoint_and_connect(monkeypatch, tmp_path):
    # Swap in a fresh, isolated credential store WITHOUT reloading the module
    # (reloading would swap globals that other test files captured by reference).
    monkeypatch.setenv("SHADOW_PROVIDERS_FILE", str(tmp_path / "p.enc"))
    monkeypatch.setenv("SHADOW_PROVIDERS_KEY_FILE", str(tmp_path / "p.key"))
    for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
        monkeypatch.delenv(k, raising=False)
    import shadow_node.main as m
    monkeypatch.setattr(m, "credentials", provider_auth.CredentialStore())
    c = TestClient(m.app)
    data = c.get("/providers").json()
    assert {p["provider"] for p in data["providers"]} == {"anthropic", "openai", "gemini"}
    assert all(p["connected"] is False for p in data["providers"])
    assert c.post("/providers/openai/connect", json={"api_key": "sk-test"}).json()["connected"] is True
    after = {p["provider"]: p for p in c.get("/providers").json()["providers"]}
    assert after["openai"]["connected"] is True
    assert c.delete("/providers/openai").json()["connected"] is False


def test_ask_reports_route_and_savings():
    from shadow_node.main import app
    c = TestClient(app)
    c.post("/memory/ingest", json={"text": "Aurora ships in March.", "source_title": "notes"})
    body = c.post("/agent/ask", json={"prompt": "when does aurora ship?"}).json()
    assert body["route"] == "local" and "savings" in body
    assert "tokens_saved_estimate" in body["savings"]
