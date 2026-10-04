"""Backlog #1: HITL approval pattern (suspend on tool call, decision card,
REST decide, (threadId, toolCallId) idempotency receipt, resume).

OpenDots source: src/client/PageReviewCard.tsx,
src/client/page-review-decision.ts, src/shared/page-review.ts,
src/server/pages.ts (117-147), src/server/page-routes.ts,
src/client/Chat.tsx (169-181). MIT (c) Atai Barkai. Adapted: SHADOW adds
the risk class OpenDots lacks, a persistent approvals inbox, and push on
approval.created (all pre-existing); this adds suspend-on-tool-call and
the idempotency receipt.
"""
import pytest
from fastapi.testclient import TestClient

import shadow_node.main as _main
from shadow_node.main import app
from agent_core import AgentAction, AgentCore, ApprovalStatus


@pytest.fixture
def no_auth(monkeypatch):
    monkeypatch.setattr(_main, "AUTH_REQUIRED", False)


def email_action():
    return AgentAction(tool_name="send_email", description="Send quarterly report to the team")


# --- suspend / resume ---------------------------------------------------------

def test_execute_suspends_on_approval_required():
    core = AgentCore(mock_tools=True)
    out = core.execute(email_action(), thread_id="thr_1", tool_call_id="tc_1")
    assert out["ok"] is False
    assert out["status"] == "approval_pending"
    assert out["approval_id"].startswith("apr_")
    assert out["thread_id"] == "thr_1" and out["tool_call_id"] == "tc_1"
    assert out["verification"] == "uncertain"  # suspended, not failed
    card = out["card"]
    assert card["tool_name"] == "send_email"
    assert card["risk"]  # SHADOW risk class, which OpenDots lacks
    assert "Nothing runs until you approve" in card["footnote"]


def test_receipt_idempotency_no_duplicate_card():
    core = AgentCore(mock_tools=True)
    first = core.execute(email_action(), thread_id="thr_2", tool_call_id="tc_2")
    second = core.execute(email_action(), thread_id="thr_2", tool_call_id="tc_2")
    assert first["approval_id"] == second["approval_id"]
    assert len(core.approvals.requests) == 1


def test_receipt_lookup_returns_pending_approval():
    core = AgentCore(mock_tools=True)
    out = core.execute(email_action(), thread_id="thr_3", tool_call_id="tc_3")
    req = core.approvals.receipt("thr_3", "tc_3")
    assert req is not None and req.id == out["approval_id"]
    assert core.approvals.receipt("thr_3", "nope") is None


def test_new_receipt_after_decision():
    core = AgentCore(mock_tools=True)
    first = core.execute(email_action(), thread_id="thr_4", tool_call_id="tc_4")
    core.approvals.decide(first["approval_id"], False, "nope")
    second = core.execute(email_action(), thread_id="thr_4", tool_call_id="tc_4")
    assert second["approval_id"] != first["approval_id"]


def test_resume_after_approval_runs_tool():
    core = AgentCore(mock_tools=True)
    suspended = core.execute(email_action(), thread_id="thr_5", tool_call_id="tc_5")
    core.approvals.decide(suspended["approval_id"], True)
    resumed = core.execute(email_action(), approved=True, approval_id=suspended["approval_id"])
    assert resumed["ok"] is True


def test_denied_approval_stays_denied_on_resume():
    core = AgentCore(mock_tools=True)
    suspended = core.execute(email_action(), thread_id="thr_6", tool_call_id="tc_6")
    core.approvals.decide(suspended["approval_id"], False, "declined by owner")
    resumed = core.execute(email_action(), approved=True, approval_id=suspended["approval_id"])
    assert resumed["ok"] is False


def test_hard_deny_still_fails_not_suspends():
    core = AgentCore(mock_tools=True)
    out = core.execute(AgentAction(tool_name="keylogger", description="hidden keylog"))
    assert out["ok"] is False
    assert out.get("status") != "approval_pending"


# --- REST round trip ----------------------------------------------------------

client = TestClient(app)


def test_rest_suspend_decide_resume_round_trip(no_auth):
    import uuid as _uuid
    title = f"hitl-test-{_uuid.uuid4().hex[:8]}"  # unique: verification diffs real world state
    action = {"tool_name": "note.create", "description": "Create test note",
              "params": {"title": title, "body": "hello"}}
    # 1. suspend
    r = client.post("/agent/execute", json={"action": action, "thread_id": "rt_1", "tool_call_id": "rtc_1"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approval_pending"
    approval_id = body["approval_id"]
    assert body["card"]["approval_id"] == approval_id
    # 2. receipt lookup (lost-response recovery)
    r = client.get("/approvals/receipt", params={"thread_id": "rt_1", "tool_call_id": "rtc_1"})
    assert r.status_code == 200
    assert r.json()["card"]["approval_id"] == approval_id
    # 3. decide via REST
    r = client.post(f"/approvals/{approval_id}/approve")
    assert r.status_code == 200
    # 4. resume: the approved tool actually runs
    r = client.post("/agent/execute", json={"action": action, "approval_id": approval_id})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_rest_receipt_404_when_missing(no_auth):
    r = client.get("/approvals/receipt", params={"thread_id": "nope", "tool_call_id": "nope"})
    assert r.status_code == 404
