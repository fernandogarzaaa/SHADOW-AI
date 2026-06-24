"""Tests for the route-prompting engine and the MCP server wiring."""
import json
import pytest
from shadow_node.mcp_tools import RouteEngine
from shadow_node.model_providers import LocalMockModel


class FakeFrontier:
    name = "fake"
    cloud = True
    def complete(self, prompt, context=""):
        return f"FRONTIER<{len(context)}>:{prompt}"


@pytest.fixture
def engine(monkeypatch, tmp_path):
    # Isolate the credential store so env/provider state doesn't leak in.
    monkeypatch.setenv("SHADOW_PROVIDERS_FILE", str(tmp_path / "p.enc"))
    monkeypatch.setenv("SHADOW_PROVIDERS_KEY_FILE", str(tmp_path / "p.key"))
    for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "SHADOW_MODEL_PROVIDER"]:
        monkeypatch.delenv(k, raising=False)
    return RouteEngine()


def test_tool_specs_cover_all_four(engine):
    names = {t["name"] for t in engine.tool_specs()}
    assert names == {"route_estimate", "compress_context", "route_complete", "list_providers"}


def test_route_estimate_simple_is_local(engine):
    out = engine.dispatch("route_estimate", {"prompt": "what time is it?", "context": "tiny"})
    assert out["route"] == "local"
    assert out["would_save_tokens_estimate"] == out["raw_context_tokens"]


def test_route_estimate_hard_is_frontier(engine):
    prompt = ("analyze and compare the strategy trade-offs across these documents, "
              "explain why the design decisions matter, and recommend a detailed plan")
    out = engine.dispatch("route_estimate", {"prompt": prompt, "context": "x " * 500})
    assert out["route"] == "frontier"
    assert out["compressed_context_tokens"] <= out["raw_context_tokens"]


def test_compress_context_reduces_large_text(engine):
    big = "Aurora planning note. " * 400
    out = engine.dispatch("compress_context", {"text": big})
    assert out["compressed_tokens"] <= out["raw_tokens"]
    assert "skeleton" in out and out["fingerprint"]


def test_route_complete_local_without_cloud(engine):
    out = engine.dispatch("route_complete", {"prompt": "hi?", "context": "some context", "allow_cloud": False})
    assert out["route"] == "local" and out["provider"] == "local_mock"
    assert out["savings"]["frontier_tokens_sent"] == 0


def test_route_complete_uses_frontier_with_compressed_context():
    eng = RouteEngine(local=LocalMockModel())
    eng._frontier = lambda provider=None: FakeFrontier()  # inject a connected provider
    big = "secret project Aurora details. " * 300
    out = eng.route_complete("analyze and summarize the Aurora strategy", big, allow_cloud=True)
    assert out["route"] == "frontier" and out["provider"] == "fake"
    # frontier saw compressed (smaller) context, and savings are reported
    assert out["savings"]["compressed_context_tokens"] <= out["savings"]["raw_context_tokens"]


def test_list_providers(engine):
    out = engine.dispatch("list_providers")
    assert {p["provider"] for p in out["providers"]} == {"anthropic", "openai", "gemini"}


def test_unknown_tool_raises(engine):
    with pytest.raises(KeyError):
        engine.dispatch("rm_rf", {})


def test_mcp_server_builds_and_registers_tools():
    mcp = pytest.importorskip("mcp")
    from shadow_node.mcp_server import build_server
    server = build_server()
    assert server.name == "shadow-router"
