"""Production hardening: grounding cascade, rate limiting, readiness probe."""
import importlib
import pytest
from fastapi.testclient import TestClient

from shadow_node.hybrid import HybridRouter, GroundingVerifier
from shadow_node.model_providers import LocalMockModel
from shadow_node.obs import RateLimiter


def test_grounding_verifier_scores():
    v = GroundingVerifier()
    ctx = "Aurora launches in March with a new encryption design."
    assert v.score("Aurora launches in March", ctx) > 0.6
    assert v.score("Bananas orbit Jupiter quietly", ctx) < 0.3
    assert v.score("", ctx) == 1.0  # nothing to ground


class TwoPassFrontier:
    """Returns an ungrounded answer for compressed context, grounded for full."""
    name = "twopass"
    cloud = True
    def __init__(self): self.calls = []
    def complete(self, prompt, context=""):
        self.calls.append(context)
        if len(self.calls) == 1:
            return "completely unrelated zzzz qqqq"        # ungrounded -> triggers retry
        return "Aurora milestone strategy planning details"  # grounded on retry


def test_cascade_retries_against_full_context_when_ungrounded():
    big = "Aurora milestone strategy planning details. " * 60
    fr = TwoPassFrontier()
    h = HybridRouter(LocalMockModel())
    out = h.run("analyze and summarize the Aurora strategy and recommend a plan",
                big, frontier=fr, verify=True)
    assert out["route"] == "frontier"
    assert out["regrounded"] is True
    assert len(fr.calls) == 2
    assert len(fr.calls[1]) > len(fr.calls[0])      # retry used the fuller context
    assert out["grounding"] >= 0.3


def test_cascade_off_by_default_no_retry():
    big = "Aurora milestone strategy planning details. " * 60
    fr = TwoPassFrontier()
    h = HybridRouter(LocalMockModel())
    out = h.run("analyze and summarize the Aurora strategy and recommend a plan", big, frontier=fr)
    assert out["regrounded"] is False and len(fr.calls) == 1


def test_rate_limiter_blocks_after_capacity():
    rl = RateLimiter(rpm=60, burst=2)
    assert rl.allow("a") and rl.allow("a")   # capacity 2
    assert rl.allow("a") is False            # third blocked
    assert rl.allow("b") is True             # different key independent


def test_ready_endpoint_reports_config(monkeypatch):
    monkeypatch.setenv("SHADOW_GROUNDING_VERIFY", "true")
    import shadow_node.main as m
    importlib.reload(m)
    c = TestClient(m.app)
    body = c.get("/ready").json()
    assert body["status"] == "ready"
    assert body["grounding_verify"] is True
    assert "rate_limit_rpm" in body and "providers_ready" in body


def test_rate_limit_middleware_returns_429(monkeypatch):
    monkeypatch.setenv("SHADOW_RATE_LIMIT_RPM", "1")
    monkeypatch.delenv("SHADOW_AUTH_REQUIRED", raising=False)
    import shadow_node.main as m
    importlib.reload(m)
    c = TestClient(m.app)
    assert c.get("/providers").status_code == 200   # first allowed
    assert c.get("/providers").status_code == 429   # burst exhausted
    assert c.get("/health").status_code == 200       # probes are never limited
    monkeypatch.delenv("SHADOW_RATE_LIMIT_RPM", raising=False)
    importlib.reload(m)
