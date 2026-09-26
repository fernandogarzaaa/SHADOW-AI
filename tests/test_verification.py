"""Tests for the evidence-based verification layer.

Covers the deterministic verifier state machine (all four statuses), evidence
attachment, world-state diffing, the /agent/execute -> /executions API surface,
approval-card verdict linkage (including the SSE fan-out), persistence, and
the operator CLI.
"""
import importlib
import json
import os

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from agent_core import (
    AgentAction,
    AgentCore,
    ExecutionRecord,
    VerificationStatus,
    WorldStateDiff,
    diff_snapshots,
    snapshot_workspace,
    verify_execution,
    workspace_root,
)
from ghost_adapter import LocalActionExecutor


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR", str(tmp_path))
    return tmp_path


def _action(tool, params=None, description="do the thing"):
    return AgentAction(tool_name=tool, description=description, params=params or {})


def _diff(added=(), modified=(), removed=()):
    return WorldStateDiff(added=list(added), modified=list(modified), removed=list(removed))


# --- verifier state machine: all four statuses ---

def test_verifier_verified_when_diff_matches_intent(workspace):
    (workspace / "hello.md").write_text("# Hello\n\nbody text\n")
    action = _action("note.create", {"title": "Hello", "body": "body text"})
    diff = _diff(added=["hello.md"])
    status, reason = verify_execution(action, True, "Allowed.", {"ok": True}, None, diff, workspace)
    assert status == VerificationStatus.VERIFIED
    assert "hello.md" in reason


def test_verifier_failed_when_policy_blocked():
    action = _action("note.create", {"title": "x"})
    status, reason = verify_execution(action, False, "Approval required before execution.",
                                      None, None, None, None)
    assert status == VerificationStatus.FAILED
    assert "Approval required" in reason


def test_verifier_failed_when_tool_raised():
    action = _action("note.create", {"title": "x"})
    status, _ = verify_execution(action, True, "Allowed.", None, "ValueError: boom",
                                 _diff(), workspace_root())
    assert status == VerificationStatus.FAILED


def test_verifier_failed_when_tool_reports_failure():
    action = _action("note.create", {"title": "x"})
    status, reason = verify_execution(action, True, "Allowed.", {"ok": False, "reason": "disk full"},
                                      None, _diff(), workspace_root())
    assert status == VerificationStatus.FAILED
    assert "disk full" in reason


def test_verifier_failed_on_false_success(workspace):
    """Spec Phase 22: a tool that claims success but changes nothing is FAILED, not success."""
    action = _action("note.create", {"title": "Ghost Note", "body": "nothing written"})
    status, reason = verify_execution(action, True, "Allowed.", {"ok": True, "action": "note.create"},
                                      None, _diff(), workspace)
    assert status == VerificationStatus.FAILED
    assert "did not change" in reason


def test_verifier_conflicting_when_state_contradicts_intent(workspace):
    (workspace / "wrong.md").write_text("unrelated content")
    action = _action("note.create", {"title": "Expected Title", "body": "expected body"})
    status, reason = verify_execution(action, True, "Allowed.", {"ok": True}, None,
                                      _diff(added=["wrong.md"]), workspace)
    assert status == VerificationStatus.CONFLICTING
    assert "contradicts" in reason


def test_verifier_uncertain_for_mock_tool():
    action = _action("mystery.tool", {}, description="unregistered")
    status, reason = verify_execution(action, True, "Allowed.", {"status": "mock_executed"},
                                      None, _diff(), workspace_root())
    assert status == VerificationStatus.UNCERTAIN
    assert "mock" in reason


def test_verifier_uncertain_for_unknown_registered_tool(workspace):
    action = _action("custom.widget", {}, description="unknown but registered")
    status, _ = verify_execution(action, True, "Allowed.", {"ok": True}, None,
                                 _diff(added=["widget.json"]), workspace)
    assert status == VerificationStatus.UNCERTAIN


def test_verifier_read_only_verified(workspace):
    (workspace / "a.md").write_text("x")
    action = _action("note.list", {}, description="list notes")
    status, reason = verify_execution(action, True, "Allowed.",
                                      {"ok": True, "action": "note.list", "notes": ["a.md"]},
                                      None, _diff(), workspace)
    assert status == VerificationStatus.VERIFIED
    assert "1 notes" in reason


# --- world-state snapshots and diffs ---

def test_snapshot_and_diff_detect_added_modified_removed(workspace):
    (workspace / "keep.md").write_text("v1")
    (workspace / "gone.md").write_text("bye")
    before = snapshot_workspace(workspace)
    (workspace / "new.md").write_text("hello")
    (workspace / "keep.md").write_text("v2")
    (workspace / "gone.md").unlink()
    diff = diff_snapshots(before, snapshot_workspace(workspace))
    assert diff.added == ["new.md"]
    assert diff.modified == ["keep.md"]
    assert diff.removed == ["gone.md"]
    assert diff.changed


def test_snapshot_missing_root_is_empty(tmp_path):
    assert snapshot_workspace(tmp_path / "nope") == {}


# --- AgentCore.execute integration ---

def _core_with_real_tools():
    core = AgentCore()
    ex = LocalActionExecutor()
    for name in ex.names():
        core.tools.register(name, lambda params, _ex=ex, _n=name: _ex.run(_n, params))
    return core


def test_execute_verified_end_to_end(workspace):
    core = _core_with_real_tools()
    action = _action("note.create", {"title": "Verified Note", "body": "proof inside"})
    res = core.execute(action, approved=True)
    assert res["ok"] is True
    assert res["verification"] == "verified"
    assert (workspace / "verified-note.md").exists()
    rec = core.executions[res["execution_id"]]
    assert rec.verification == VerificationStatus.VERIFIED
    assert rec.policy_allowed is True
    kinds = {e.kind for e in rec.evidence}
    assert {"policy_decision", "tool_output", "world_state_diff"} <= kinds
    assert rec.world_state is not None and rec.world_state.changed
    assert rec.finished_at is not None


def test_execute_failed_false_success_is_caught(workspace):
    core = AgentCore()
    core.tools.register("note.create", lambda params: {"ok": True, "action": "note.create"})
    res = core.execute(_action("note.create", {"title": "Liar", "body": "x"}), approved=True)
    assert res["ok"] is True  # the tool claimed success...
    assert res["verification"] == "failed"  # ...but verification caught the lie
    assert "did not change" in res["verification_reason"]


def test_execute_conflicting_when_tool_writes_wrong_thing(workspace):
    core = AgentCore()

    def sneaky(params):
        (workspace / "unrelated.md").write_text("not what was asked")
        return {"ok": True, "action": "note.create"}

    core.tools.register("note.create", sneaky)
    res = core.execute(_action("note.create", {"title": "Wanted", "body": "wanted body"}), approved=True)
    assert res["verification"] == "conflicting"


def test_execute_uncertain_for_unregistered_tool(workspace):
    core = AgentCore()
    res = core.execute(_action("send_email", {"to": "x@y.z"}, description="send mail"), approved=True)
    assert res["ok"] is True
    assert res["verification"] == "uncertain"


def test_execute_blocked_is_failed_with_evidence(workspace):
    core = _core_with_real_tools()
    res = core.execute(_action("note.create", {"title": "Blocked"}), approved=False)
    assert res["ok"] is False
    assert res["verification"] == "failed"
    rec = core.executions[res["execution_id"]]
    assert rec.tool_result is None
    assert any(e.kind == "policy_decision" for e in rec.evidence)
    assert not (workspace / "blocked.md").exists()


def test_execute_tool_exception_is_failed(workspace):
    core = AgentCore()

    def boom(params):
        raise RuntimeError("kaboom")

    core.tools.register("note.create", boom)
    res = core.execute(_action("note.create", {"title": "Boom"}), approved=True)
    assert res["verification"] == "failed"
    assert "kaboom" in res["verification_reason"]
    rec = core.executions[res["execution_id"]]
    assert any(e.kind == "error" for e in rec.evidence)


def test_execution_persists_to_encrypted_store(workspace, tmp_path, monkeypatch):
    from shadow_node.runtime_store import EncryptedRuntimeStore

    monkeypatch.setenv("SHADOW_RUNTIME_KEY", Fernet.generate_key().decode())
    store = EncryptedRuntimeStore(str(tmp_path / "runtime.db"))
    core = AgentCore(execution_store=store)
    ex = LocalActionExecutor()
    core.tools.register("note.create", lambda p: ex.run("note.create", p))
    res = core.execute(_action("note.create", {"title": "Persisted"}), approved=True)
    rows = store.all("executions", ExecutionRecord)
    assert [r.id for r in rows] == [res["execution_id"]]
    assert rows[0].verification == VerificationStatus.VERIFIED
    # A fresh core reloads history from the store.
    assert AgentCore(execution_store=store).executions[res["execution_id"]].intent == rows[0].intent


# --- HTTP API ---

@pytest.fixture
def api_client(workspace, monkeypatch):
    monkeypatch.setenv("SHADOW_AUTH_REQUIRED", "false")
    import shadow_node.main as m
    importlib.reload(m)
    return TestClient(m.app), m


def _note_action(title="API Note", body="via api"):
    return {"id": "act_api", "tool_name": "note.create", "description": "save note",
            "params": {"title": title, "body": body}, "risk": "low",
            "requires_approval": True, "destructive": False, "data_used": []}


def test_execute_endpoint_returns_verification(api_client, workspace):
    client, m = api_client
    r = client.post("/agent/execute", json={"action": _note_action(), "approved": True}).json()
    assert r["ok"] is True
    assert r["verification"] == "verified"
    assert r["execution_id"].startswith("exec_")
    assert (workspace / "api-note.md").exists()


def test_executions_list_and_detail(api_client):
    client, m = api_client
    eid = client.post("/agent/execute", json={"action": _note_action(), "approved": True}).json()["execution_id"]
    listing = client.get("/executions").json()
    assert any(e["id"] == eid and e["verification"] == "verified" for e in listing)
    filtered = client.get("/executions", params={"status": "failed"}).json()
    assert all(e["verification"] == "failed" for e in filtered)
    detail = client.get(f"/executions/{eid}").json()
    assert detail["verification"] == "verified"
    assert detail["action"]["tool_name"] == "note.create"
    assert any(e["kind"] == "world_state_diff" for e in detail["evidence"])
    assert client.get("/executions/exec_missing").status_code == 404


def test_approval_card_carries_verdict_and_sse_fires(api_client):
    client, m = api_client
    q = m.bus.subscribe()
    try:
        rid = client.post("/approvals", json={"action": _note_action("Card Note", "card body"),
                                              "reason": "test"}).json()["id"]
        client.post(f"/approvals/{rid}/approve")
        # Drain the approval.updated event from the approve() call itself.
        while True:
            try:
                q.get_nowait()
            except Exception:
                break
        r = client.post("/agent/execute", json={"action": _note_action("Card Note", "card body"),
                                                "approved": True, "approval_id": rid}).json()
        assert r["verification"] == "verified"
        card = next(a for a in client.get("/approvals").json() if a["id"] == rid)
        assert card["execution_id"] == r["execution_id"]
        assert card["verification_status"] == "verified"
        evt = q.get_nowait()
        assert evt["type"] == "approval.updated"
        assert evt["properties"]["verification_status"] == "verified"
        assert evt["properties"]["execution_id"] == r["execution_id"]
    finally:
        m.bus.unsubscribe(q)


def test_execute_with_unknown_approval_id_is_404(api_client):
    client, m = api_client
    r = client.post("/agent/execute", json={"action": _note_action(), "approved": True,
                                            "approval_id": "apr_missing"})
    assert r.status_code == 404


def test_execute_blocked_still_records_failed_execution(api_client):
    client, m = api_client
    r = client.post("/agent/execute", json={"action": _note_action(), "approved": False}).json()
    assert r["ok"] is False and r["verification"] == "failed"
    detail = client.get(f"/executions/{r['execution_id']}").json()
    assert detail["verification"] == "failed"
    assert detail["tool_result"] is None


# --- CLI ---

def test_cli_lists_and_shows_executions(workspace, tmp_path, monkeypatch, capsys):
    from shadow_node.runtime_store import EncryptedRuntimeStore
    from shadow_node.cli import main as cli_main

    db = str(tmp_path / "runtime.db")
    monkeypatch.setenv("SHADOW_RUNTIME_DB", db)
    monkeypatch.setenv("SHADOW_RUNTIME_KEY", Fernet.generate_key().decode())
    store = EncryptedRuntimeStore(db)
    core = AgentCore(execution_store=store)
    ex = LocalActionExecutor()
    core.tools.register("note.create", lambda p: ex.run("note.create", p))
    eid = core.execute(_action("note.create", {"title": "CLI Note"}, description="CLI Note"), approved=True)["execution_id"]

    assert cli_main(["executions", "list"]) == 0
    out = capsys.readouterr().out
    assert eid in out and "verified" in out

    assert cli_main(["executions", "list", "--status", "failed"]) == 0
    assert eid not in capsys.readouterr().out

    assert cli_main(["executions", "show", eid]) == 0
    shown = capsys.readouterr().out
    assert "verified" in shown and "world-state diff" in shown and "CLI Note" in shown

    assert cli_main(["executions", "show", "exec_missing"]) == 1


def test_cli_without_runtime_db_explains_itself(monkeypatch):
    from shadow_node.cli import main as cli_main

    monkeypatch.delenv("SHADOW_RUNTIME_DB", raising=False)
    assert cli_main(["executions", "list"]) == 1
