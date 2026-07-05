"""Tests for Phase-4+ enhancements: persistent approvals, expanded tools, AXIOM routing, Ed25519."""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
import shadow_node.main as main


@pytest.fixture()
def client():
    main.AUTH_REQUIRED = False
    return TestClient(main.app)

from agent_core import (
    AgentAction,
    AgentCore,
    ApprovalRequest,
    ApprovalStatus,
    PolicyEngine,
    RiskClass,
    UserProfile,
)
from axiom_adapter import AxiomAdapter, SemanticRouter
from ghost_adapter import LocalActionExecutor, GhostAdapter, GhostTaskIR


# ---------------------------------------------------------------------------
# Persistent approvals + expiry sweeping
# ---------------------------------------------------------------------------
class FakeApprovalStore:
    """In-memory store that mimics EncryptedRuntimeStore's interface."""

    def __init__(self):
        self._data: dict[str, dict] = {}

    def put(self, collection: str, id: str, obj) -> None:
        self._data[f"{collection}:{id}"] = obj

    def all(self, collection: str, model) -> list:
        out = []
        for key, val in self._data.items():
            if key.startswith(f"{collection}:"):
                if isinstance(val, model):
                    out.append(val)
                elif hasattr(val, "model_dump_json"):
                    out.append(model.model_validate_json(val.model_dump_json()))
        return out


def test_approval_workflow_with_store():
    store = FakeApprovalStore()
    from agent_core import ApprovalWorkflow
    wf = ApprovalWorkflow(store=store)
    a = AgentAction(tool_name="send_email", description="test")
    req = wf.create(a, "need approval")
    assert req.id in wf.requests
    # Store should have persisted it.
    assert len(store.all("approvals", ApprovalRequest)) == 1

    decided = wf.decide(req.id, True)
    assert decided.status == ApprovalStatus.APPROVED
    # After decision, the updated record should be in store.
    stored_records = store.all("approvals", ApprovalRequest)
    assert any(r.status == ApprovalStatus.APPROVED for r in stored_records)


def test_approval_decide_rejects_expired_requests():
    from agent_core import ApprovalWorkflow
    wf = ApprovalWorkflow()
    req = wf.create(AgentAction(tool_name="x", description="old"), "old")
    req.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    with pytest.raises(ValueError, match="expired"):
        wf.decide(req.id, True)
    assert wf.requests[req.id].status == ApprovalStatus.EXPIRED


def test_approval_decide_rejects_terminal_requests():
    from agent_core import ApprovalWorkflow
    wf = ApprovalWorkflow()
    req = wf.create(AgentAction(tool_name="x", description="one-shot"), "once")
    wf.decide(req.id, True)
    with pytest.raises(ValueError, match="already"):
        wf.decide(req.id, False)
    assert wf.requests[req.id].status == ApprovalStatus.APPROVED


def test_approval_sweep_expires_old_requests():
    from agent_core import ApprovalWorkflow
    wf = ApprovalWorkflow()
    a = AgentAction(tool_name="x", description="y")
    req = wf.create(a, "old")
    # Artificially back-date the request so it is already expired.
    req.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = wf.sweep_expired()
    assert req.id in expired
    assert wf.requests[req.id].status == ApprovalStatus.EXPIRED


def test_approval_sweep_leaves_fresh_requests():
    from agent_core import ApprovalWorkflow
    wf = ApprovalWorkflow()
    req = wf.create(AgentAction(tool_name="x", description="y"), "fresh")
    expired = wf.sweep_expired()
    assert req.id not in expired
    assert wf.requests[req.id].status == ApprovalStatus.PENDING


# ---------------------------------------------------------------------------
# Expanded tool catalog
# ---------------------------------------------------------------------------
def test_calendar_create_writes_event(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR", str(tmp_path))
    ex = LocalActionExecutor()
    res = ex.run("calendar.create", {"title": "Team Standup", "start": "2026-07-10T09:00"}, explicit_consent=True)
    assert res["ok"] and res["action"] == "calendar.create"
    assert "Team Standup" in (tmp_path / "calendar_events.jsonl").read_text()


def test_email_draft_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR", str(tmp_path))
    ex = LocalActionExecutor()
    res = ex.run("email.draft", {"to": "boss@example.com", "subject": "Update", "body": "Project is on track."}, explicit_consent=True)
    assert res["ok"] and res["action"] == "email.draft"
    drafts = list((tmp_path / "drafts").glob("update-*.md"))
    assert len(drafts) == 1
    assert "boss@example.com" in drafts[0].read_text()


def test_email_draft_duplicate_subjects_do_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR", str(tmp_path))
    ex = LocalActionExecutor()
    first = ex.run("email.draft", {"subject": "Update", "body": "first"}, explicit_consent=True)
    second = ex.run("email.draft", {"subject": "Update", "body": "second"}, explicit_consent=True)
    assert first["path"] != second["path"]
    assert "first" in __import__("pathlib").Path(first["path"]).read_text()
    assert "second" in __import__("pathlib").Path(second["path"]).read_text()


def test_email_draft_subject_fallback_is_consistent(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR", str(tmp_path))
    ex = LocalActionExecutor()
    res = ex.run("email.draft", {"to": "boss@example.com", "body": "No subject"}, explicit_consent=True)
    body = __import__("pathlib").Path(res["path"]).read_text()
    assert "# Draft: Draft Email" in body
    assert "**Subject:** Draft Email" in body


def test_consent_required_tools_block_direct_execution():
    ex = LocalActionExecutor()
    res = ex.run("email.draft", {"subject": "Blocked"})
    assert res == {"ok": False, "reason": "explicit_consent_required", "action": "email.draft"}


def test_tool_metadata_lists_consent_requirements():
    ex = LocalActionExecutor()
    meta = ex.tool_metadata()
    names = {m["name"] for m in meta}
    assert "calendar.create" in names
    assert "email.draft" in names
    consent_tools = {m["name"] for m in meta if m["needs_explicit_consent"]}
    assert "calendar.create" in consent_tools
    assert "email.draft" in consent_tools
    assert "note.create" not in consent_tools


def test_tools_endpoint_returns_metadata(client):
    r = client.get("/tools").json()
    assert "tool_metadata" in r
    assert "consent_required_tools" in r
    assert "calendar.create" in r["consent_required_tools"]


# ---------------------------------------------------------------------------
# Enhanced AXIOM semantic routing
# ---------------------------------------------------------------------------
def test_semantic_router_classifies_topics():
    router = SemanticRouter()
    scores = router.classify_topic("Project Aurora milestone deadline is Friday")
    assert scores["project"] >= 0.5
    assert scores["finance"] < 0.3


def test_semantic_router_classifies_punctuated_keywords():
    router = SemanticRouter()
    scores = router.classify_topic("budget, deadline.")
    assert scores["finance"] > 0
    assert scores["project"] > 0


def test_semantic_router_computes_relevance():
    router = SemanticRouter()
    score = router.relevance_score("Aurora deadline", "Project Aurora ships in March with a deadline")
    assert score > 0.5


def test_semantic_router_routing_decision():
    router = SemanticRouter()
    decision = router.build_routing_decision("When is Aurora shipping?", "Project Aurora ships in March. Deadline is the 15th.")
    assert decision["category"] == "project"
    assert decision["relevance"] > 0.0
    assert "priority" in decision


def test_axiom_package_includes_skeleton_and_routing():
    axiom = AxiomAdapter()
    pkg = axiom.package_context("Project Alpha uses encrypted local memory for storage.")
    assert "skeleton" in pkg
    assert "routing" in pkg
    assert pkg["skeleton"]["word_count"] > 0
    assert pkg["routing"]["category"] == "project"


def test_axiom_analyze_for_routing():
    axiom = AxiomAdapter()
    result = axiom.analyze_for_routing("What about the budget?", "Project Aurora has a budget of $50K.")
    assert "category" in result
    assert "topic_scores" in result


def test_axiom_skeleton_entities_are_deterministic():
    axiom = AxiomAdapter()
    text = "Email z@example.com then a@example.com about Project Aurora."
    first = axiom.package_context(text)["skeleton"]["entities"]
    second = axiom.package_context(text)["skeleton"]["entities"]
    assert first == second


# ---------------------------------------------------------------------------
# Ed25519 key support (when cryptography is available)
# ---------------------------------------------------------------------------
def test_ed25519_sign_and_verify():
    from agent_core.security import (
        generate_ed25519_keypair,
        sign_ed25519,
        verify_ed25519,
    )
    priv, pub = generate_ed25519_keypair()
    sig = sign_ed25519(priv, "POST", "/memory/ingest", "{}", "n1", 1700000000)
    assert verify_ed25519(pub, sig, "POST", "/memory/ingest", "{}", "n1", 1700000000)
    assert not verify_ed25519(pub, sig, "POST", "/memory/ingest", "{}", "n1", 1700000001)


def test_device_store_register_ed25519():
    from agent_core.security import DeviceSessionStore
    store = DeviceSessionStore()
    from agent_core.security import generate_ed25519_keypair
    priv, pub = generate_ed25519_keypair()
    dev = store.register_ed25519("iPhone", pub)
    assert dev.id in store.devices
    assert dev.id in store.ed25519_keys
    assert dev.id not in store.secrets


def test_device_store_ed25519_does_not_fallback_to_hmac():
    import importlib
    import os
    import agent_core.security as sec_mod
    os.environ["SHADOW_ED25519_KEYS"] = "false"
    importlib.reload(sec_mod)
    store = sec_mod.DeviceSessionStore()
    _priv, pub = sec_mod.generate_ed25519_keypair()
    dev = store.register_ed25519("iPhone", pub)
    fake_secret = __import__("hashlib").sha256(pub).hexdigest()
    sig = sec_mod.sign_request(fake_secret, "GET", "/health", "", "nonce-no-fallback", int(time.time()))
    ok, reason = store.verify(dev.id, sig, "nonce-no-fallback", str(int(time.time())), "GET", "/health", "")
    assert not ok
    assert reason == "ed25519_disabled"


def test_device_store_verify_ed25519_signature():
    import importlib
    import os
    import agent_core.security as sec_mod
    os.environ["SHADOW_ED25519_KEYS"] = "true"
    importlib.reload(sec_mod)
    store = sec_mod.DeviceSessionStore()
    priv, pub = sec_mod.generate_ed25519_keypair()
    dev = store.register_ed25519("iPhone", pub)
    sig = sec_mod.sign_ed25519(priv, "GET", "/health", "", "nonce1", int(time.time()))
    ok, reason = store.verify(dev.id, sig, "nonce1", str(int(time.time())), "GET", "/health", "")
    assert ok and reason == "ok"
    os.environ["SHADOW_ED25519_KEYS"] = "false"
    importlib.reload(sec_mod)


# ---------------------------------------------------------------------------
# Approval sweep endpoint
# ---------------------------------------------------------------------------
def test_approval_sweep_endpoint(client):
    # Create an approval then backdate it.
    r = client.post("/approvals", json={
        "action": {"tool_name": "x", "description": "old", "params": {}},
        "reason": "test sweep",
    }).json()
    aid = r["id"]

    # Backdate the approval so sweep will catch it.
    import shadow_node.main as main
    req = main.core.approvals.requests[aid]
    req.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    sweep = client.post("/approvals/sweep").json()
    assert aid in sweep["expired"]
    assert main.core.approvals.requests[aid].status == ApprovalStatus.EXPIRED
