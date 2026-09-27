"""Regression tests for server-side approval binding on /agent/execute.

The client-supplied `approved` flag is never trusted: executing an
approval-requiring action must reference a granted, unexpired approval
record whose action matches the request. All rejections happen BEFORE
any execution takes place.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from agent_core import now


@pytest.fixture
def api(tmp_path, monkeypatch):
    # No importlib.reload here: reloading shadow_node.main re-executes the
    # module in place, which silently rebinds the globals that other test
    # modules' already-imported app/sessions objects read through. Isolate
    # with env + attr patching and a cleared approvals registry instead.
    workspace = tmp_path
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR", str(workspace))
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    m.core.approvals.requests.clear()
    yield TestClient(m.app), m, workspace
    m.core.approvals.requests.clear()


def _action(title="Bind Note", body="bind body"):
    return {"id": "act_bind", "tool_name": "note.create", "description": "save note",
            "params": {"title": title, "body": body}, "risk": "low",
            "requires_approval": True, "destructive": False, "data_used": []}


def _grant(client, action):
    rid = client.post("/approvals", json={"action": action, "reason": "test"}).json()["id"]
    client.post(f"/approvals/{rid}/approve")
    return rid


def test_client_approved_flag_ignored_without_approval_id(api):
    client, m, workspace = api
    action = _action(title="FlagIgnored")
    r = client.post("/agent/execute", json={"action": action, "approved": True}).json()
    assert r["ok"] is False
    assert not (workspace / "flagnored.md").exists()


def test_unknown_approval_id_404s_before_execution(api):
    client, m, workspace = api
    action = _action(title="UnknownApr")
    r = client.post("/agent/execute",
                    json={"action": action, "approved": True, "approval_id": "apr_missing"})
    assert r.status_code == 404
    assert not (workspace / "unknownapr.md").exists()


def test_pending_approval_rejected(api):
    client, m, workspace = api
    action = _action(title="PendingApr")
    rid = client.post("/approvals", json={"action": action, "reason": "test"}).json()["id"]
    r = client.post("/agent/execute", json={"action": action, "approval_id": rid})
    assert r.status_code == 403
    assert not (workspace / "pendingapr.md").exists()


def test_denied_approval_rejected(api):
    client, m, workspace = api
    action = _action(title="DeniedApr")
    rid = client.post("/approvals", json={"action": action, "reason": "test"}).json()["id"]
    client.post(f"/approvals/{rid}/deny", json={"reason": "no"})
    r = client.post("/agent/execute", json={"action": action, "approval_id": rid})
    assert r.status_code == 403
    assert not (workspace / "deniedapr.md").exists()


def test_mismatched_action_rejected(api):
    client, m, workspace = api
    rid = _grant(client, _action(title="GrantedTitle", body="granted"))
    other = _action(title="OtherTitle", body="different")
    r = client.post("/agent/execute", json={"action": other, "approval_id": rid})
    assert r.status_code == 403
    assert not (workspace / "othertitle.md").exists()


def test_expired_approval_rejected(api):
    client, m, workspace = api
    action = _action(title="ExpiredApr")
    rid = _grant(client, action)
    m.core.approvals.requests[rid].expires_at = now() - timedelta(seconds=1)
    r = client.post("/agent/execute", json={"action": action, "approval_id": rid})
    assert r.status_code == 403
    assert not (workspace / "expiredapr.md").exists()


def test_granted_matching_approval_executes(api):
    client, m, workspace = api
    action = _action(title="GrantedExec")
    rid = _grant(client, action)
    r = client.post("/agent/execute", json={"action": action, "approval_id": rid}).json()
    assert r["ok"] is True
    assert (workspace / "grantedexec.md").exists()
    # The approval card is linked to the execution after the run.
    card = next(a for a in client.get("/approvals").json() if a["id"] == rid)
    assert card["execution_id"] == r["execution_id"]


def test_ghost_handoff_without_approval_blocked_by_policy(api):
    # ghost_handoff flows through central policy like every other tool:
    # no valid approval means no execution, even in mock mode.
    client, m, workspace = api
    action = {"id": "act_ghost2", "tool_name": "ghost_handoff",
              "description": "Safe Ghost mock", "params": {}, "risk": "low",
              "requires_approval": True, "destructive": False, "data_used": []}
    r = client.post("/agent/execute", json={"action": action, "approved": True}).json()
    assert r["ok"] is False


def test_ghost_handoff_with_approval_gets_evidence_and_audit(api):
    client, m, workspace = api
    action = {"id": "act_ghost3", "tool_name": "ghost_handoff",
              "description": "Safe Ghost mock", "params": {}, "risk": "low",
              "requires_approval": True, "destructive": False, "data_used": []}
    rid = _grant(client, action)
    r = client.post("/agent/execute", json={"action": action, "approval_id": rid}).json()
    assert r["ok"] is True
    assert r["result"]["status"] == "mock_executed"
    # Execution record with evidence exists; approval card is linked.
    rec = client.get(f"/executions/{r['execution_id']}").json()
    assert rec["action"]["tool_name"] == "ghost_handoff"
    assert len(rec["evidence"]) > 0
    card = next(a for a in client.get("/approvals").json() if a["id"] == rid)
    assert card["execution_id"] == r["execution_id"]
