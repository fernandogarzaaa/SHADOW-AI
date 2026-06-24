"""Tests for real, sandboxed GHOST action execution (no mock)."""
import importlib, os
import pytest
from fastapi.testclient import TestClient
from ghost_adapter import LocalActionExecutor, GhostAdapter, GhostTaskIR


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR", str(tmp_path))
    return tmp_path


def test_note_create_writes_real_file(workspace):
    ex = LocalActionExecutor()
    res = ex.run("note.create", {"title": "Grocery List", "body": "milk, eggs"})
    assert res["ok"] and res["action"] == "note.create"
    written = (workspace / "grocery-list.md").read_text()
    assert "milk, eggs" in written


def test_note_append_and_list(workspace):
    ex = LocalActionExecutor()
    ex.run("note.create", {"title": "Log", "body": "line1"})
    ex.run("note.append", {"title": "Log", "body": "line2"})
    assert "line1" in (workspace / "log.md").read_text()
    assert "line2" in (workspace / "log.md").read_text()
    assert "log.md" in ex.run("note.list", {})["notes"]


def test_reminder_create_appends_jsonl(workspace):
    ex = LocalActionExecutor()
    ex.run("reminder.create", {"text": "call dentist", "when": "tomorrow"})
    assert "call dentist" in (workspace / "reminders.jsonl").read_text()


def test_note_path_traversal_is_neutralized(workspace):
    ex = LocalActionExecutor()
    res = ex.run("note.create", {"title": "../../etc/passwd", "body": "x"})
    # The slugified file stays inside the workspace.
    assert str(workspace) in res["path"]
    assert ".." not in os.path.basename(res["path"])


def test_http_get_blocks_ssrf_to_private_hosts(workspace):
    ex = LocalActionExecutor()
    for url in ["http://127.0.0.1/secret", "http://localhost:8787/admin", "file:///etc/passwd"]:
        with pytest.raises(ValueError):
            ex.run("http.get", {"url": url})


def test_unknown_tool_raises(workspace):
    with pytest.raises(KeyError):
        LocalActionExecutor().run("rm.everything", {})


def test_ghost_local_mode_executes_real_steps(workspace):
    g = GhostAdapter("local")
    ir = GhostTaskIR(objective="note", steps=[{"tool": "note.create", "params": {"title": "Ghost", "body": "hi"}}])
    out = g.execute(ir, approved=True)
    assert out["status"] == "executed" and out["backend"] == "ghost-local-adapter"
    assert out["telemetry"]["executed"] == 1
    assert (workspace / "ghost.md").exists()


def test_execute_endpoint_runs_real_action_after_approval(workspace):
    import shadow_node.main as m
    importlib.reload(m)
    client = TestClient(m.app)
    action = {"id": "act_note", "tool_name": "note.create", "description": "save a note",
              "params": {"title": "FromAPI", "body": "persisted via endpoint"},
              "risk": "low", "requires_approval": True, "destructive": False, "data_used": []}
    r = client.post("/agent/execute", json={"action": action, "approved": True, "double_confirmed": False}).json()
    assert r["ok"] is True
    assert r["result"]["action"] == "note.create"
    assert (workspace / "fromapi.md").exists()
    # Tools are discoverable.
    assert "note.create" in client.get("/tools").json()["tools"]


def test_execute_endpoint_blocks_without_approval(workspace):
    import shadow_node.main as m
    importlib.reload(m)
    client = TestClient(m.app)
    action = {"id": "act_note2", "tool_name": "note.create", "description": "save a note",
              "params": {"title": "NoApprove", "body": "x"}, "risk": "low",
              "requires_approval": True, "destructive": False, "data_used": []}
    r = client.post("/agent/execute", json={"action": action, "approved": False}).json()
    assert r["ok"] is False
    assert not (workspace / "noapprove.md").exists()
