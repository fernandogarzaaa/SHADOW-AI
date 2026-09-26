"""Tests for ambient GHOST capabilities: journals, checkpoints, claims, scheduler."""
import os
import time

import pytest
from cryptography.fernet import Fernet

from agent_core import (
    AgentCore,
    AmbientScheduler,
    CheckpointStore,
    ClaimRegistry,
    ClaimStatus,
    GhostRunSession,
    InMemoryKV,
    JournalEntryType,
    RunCheckpoint,
    RunJournal,
)


@pytest.fixture()
def store():
    return InMemoryKV()


@pytest.fixture()
def core(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR", str(tmp_path / "ws"))
    return AgentCore()


def _register_probe(core, calls):
    def probe(params):
        calls.append(params.get("n"))
        return {"ok": True, "n": params.get("n")}

    core.tools.register("probe", probe)


def _session(core, store, **kw):
    return GhostRunSession(
        core,
        journal=RunJournal(store),
        checkpoints=CheckpointStore(store),
        claims=ClaimRegistry(store),
        **kw,
    )


# -- journal ---------------------------------------------------------------

def test_journal_append_orders_and_persists(store):
    j1 = RunJournal(store)
    j1.append("run_a", JournalEntryType.NOTE, "first")
    j1.append("run_a", "attempt", "second")
    j1.append("run_b", JournalEntryType.NOTE, "other run")
    j2 = RunJournal(store)  # fresh reader over the same store
    entries = j2.for_run("run_a")
    assert [e.seq for e in entries] == [1, 2]
    assert [e.message for e in entries] == ["first", "second"]
    assert [e.run_id for e in j2.for_run("run_b")] == ["run_b"]
    assert j2.for_run("missing") == []


def test_journal_run_ids(store):
    j = RunJournal(store)
    j.append("run_old", JournalEntryType.NOTE, "x")
    time.sleep(0.01)
    j.append("run_new", JournalEntryType.NOTE, "y")
    ids = j.run_ids()
    assert set(ids) == {"run_old", "run_new"}


# -- checkpoints ------------------------------------------------------------

def test_checkpoint_save_load_roundtrip(store):
    cps = CheckpointStore(store)
    cp = RunCheckpoint(run_id="run_1", objective="demo", steps=[{"tool": "probe"}],
                       step_index=1, status="running")
    cps.save(cp)
    loaded = CheckpointStore(store).load("run_1")
    assert loaded is not None and loaded.step_index == 1 and loaded.status == "running"
    assert CheckpointStore(store).load("nope") is None


# -- ghost run sessions ------------------------------------------------------

def test_run_completes_with_journal_and_executions(core, store):
    calls = []
    _register_probe(core, calls)
    sess = _session(core, store)
    steps = [
        {"tool": "probe", "description": "first", "params": {"n": 1}},
        {"tool": "probe", "description": "second", "params": {"n": 2}},
    ]
    run_id = sess.start("count to two", steps)
    out = sess.run_all(run_id)
    assert out["status"] == "completed"
    assert calls == [1, 2]
    assert len(out["results"]) == 2
    assert all(r["execution_id"] for r in out["results"])
    # every step produced a real execution record
    for r in out["results"]:
        assert r["execution_id"] in core.executions
    # journal captured the whole story
    kinds = [e.entry_type for e in sess.journal.for_run(run_id)]
    assert JournalEntryType.RUN_STARTED in kinds
    assert kinds.count(JournalEntryType.ATTEMPT) == 2
    assert kinds.count(JournalEntryType.OBSERVATION) == 2
    assert JournalEntryType.COMPLETED in kinds
    # checkpoint is terminal
    cp = sess.checkpoints.load(run_id)
    assert cp.status == "completed" and cp.step_index == 2


def test_interrupt_mid_run_and_resume_skips_finished_steps(core, store):
    """The core checkpoint promise: kill the session mid-run, resume with a
    fresh session over the same store, finished steps never re-execute."""
    calls = []
    _register_probe(core, calls)
    sess = _session(core, store)
    steps = [{"tool": "probe", "description": f"s{i}", "params": {"n": i}} for i in range(3)]
    run_id = sess.start("three steps", steps)
    out = sess.run_all(run_id, max_steps=1)  # models a process dying after step 1
    assert out["status"] == "paused"
    assert sess.checkpoints.load(run_id).step_index == 1

    # brand-new session objects, same durable store: this is the "restart"
    sess2 = _session(core, store)
    resumed = sess2.resume(run_id)
    assert resumed["status"] == "completed"
    assert calls == [0, 1, 2], "step 0 must not re-execute after resume"
    assert len(resumed["results"]) == 3


def test_explicit_interrupt_then_resume(core, store):
    calls = []
    _register_probe(core, calls)
    sess = _session(core, store)
    run_id = sess.start("two steps", [
        {"tool": "probe", "description": "a", "params": {"n": "a"}},
        {"tool": "probe", "description": "b", "params": {"n": "b"}},
    ])
    sess.run_next(run_id)
    stopped = sess.interrupt(run_id, "operator stop")
    assert stopped["status"] == "interrupted"
    assert sess.checkpoints.load(run_id).status == "interrupted"
    out = sess.resume(run_id)
    assert out["status"] == "completed"
    assert calls == ["a", "b"]


def test_resume_completed_is_noop_and_unknown_raises(core, store):
    sess = _session(core, store)
    calls = []
    _register_probe(core, calls)
    run_id = sess.start("one", [{"tool": "probe", "description": "x", "params": {}}])
    sess.run_all(run_id)
    out = sess.resume(run_id)
    assert out["status"] == "already_completed"
    assert calls == [None]
    with pytest.raises(KeyError):
        sess.resume("run_missing")


def test_start_rejects_empty_steps(core, store):
    sess = _session(core, store)
    with pytest.raises(ValueError):
        sess.start("nothing", [])


def test_run_emits_sse_events(core, store):
    events = []
    sess = _session(core, store, event_sink=lambda t, p: events.append(t))
    calls = []
    _register_probe(core, calls)
    run_id = sess.start("ev", [{"tool": "probe", "description": "x", "params": {}}])
    sess.run_all(run_id)
    assert "ghost.run.started" in events
    assert "ghost.run.completed" in events


# -- claims -------------------------------------------------------------------

def test_claim_lifecycle(store):
    reg = ClaimRegistry(store)
    claim = reg.register("note X exists", run_id="run_1")
    assert claim.status == ClaimStatus.UNCONFIRMED
    decided = reg.confirm(claim.id, "read back the note file")
    assert decided.status == ClaimStatus.CONFIRMED
    assert decided.evidence == ["read back the note file"]
    with pytest.raises(ValueError):
        reg.confirm(claim.id, "again")  # decided claims are final
    other = reg.register("service Z is up")
    reg.refute(other.id, "connection refused")
    assert reg.get(other.id).status == ClaimStatus.REFUTED
    with pytest.raises(KeyError):
        reg.get("clm_missing")
    assert {c.id for c in reg.list(status="confirmed")} == {claim.id}
    assert {c.id for c in reg.for_run("run_1")} == {claim.id}


def test_step_claim_auto_confirmed_by_verified_step(core, store, tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_WORKSPACE_DIR", str(tmp_path / "ws2"))
    core.tools.register("note.list", lambda params: {"ok": True, "notes": []})
    sess = _session(core, store)
    run_id = sess.start("check notes", [
        {"tool": "note.list", "description": "list notes", "params": {},
         "claim": "the notes index is readable"},
    ])
    out = sess.run_all(run_id)
    assert out["results"][0]["verification"] == "verified"
    claims = sess.claims.for_run(run_id)
    assert len(claims) == 1 and claims[0].status == ClaimStatus.CONFIRMED
    assert claims[0].execution_ids == [out["results"][0]["execution_id"]]


def test_step_claim_auto_refuted_by_failed_step(core, store):
    core.tools.register("broken", lambda params: {"ok": False, "reason": "boom"})
    sess = _session(core, store)
    run_id = sess.start("broken run", [
        {"tool": "broken", "description": "fails", "params": {},
         "claim": "the broken tool works"},
    ])
    out = sess.run_all(run_id)
    assert out["results"][0]["verification"] == "failed"
    claims = sess.claims.for_run(run_id)
    assert len(claims) == 1 and claims[0].status == ClaimStatus.REFUTED


# -- scheduler ------------------------------------------------------------------

def test_scheduler_disabled_by_default(store):
    sched = AmbientScheduler(store=store, tasks={"t": lambda ctx: {"summary": "x"}})
    assert sched.get_config().enabled is False
    out = sched.tick()
    assert out == {"ran": False, "reason": "ambient_disabled"}


def test_scheduler_tick_runs_tasks_and_journals(store):
    sched = AmbientScheduler(store=store, tasks={"t1": lambda ctx: {"summary": "did t1", "data": {"n": 1}}})
    sched.configure(enabled=True, interval_seconds=60, tasks=["t1"])
    out = sched.tick()
    assert out["ran"] is True
    assert out["results"]["t1"]["ok"] is True
    entries = sched.journal.for_run(out["run_id"])
    kinds = [e.entry_type.value for e in entries]
    assert "run_started" in kinds and "attempt" in kinds and "observation" in kinds and "completed" in kinds
    # second immediate tick is not due
    assert sched.tick()["reason"] == "not_due"


def test_scheduler_stealth_suppresses_events(store):
    events = []
    sched = AmbientScheduler(store=store, tasks={"t1": lambda ctx: {"summary": "quiet"}},
                             event_sink=lambda t, p: events.append(t))
    sched.configure(enabled=True, interval_seconds=60, stealth_mode=True, tasks=["t1"])
    events.clear()  # ambient.config.changed is user-initiated, not ambient activity
    out = sched.tick()
    assert out["ran"] is True and out["stealth_mode"] is True
    assert events == [], "stealth mode must emit no SSE events for ambient activity"
    # journal still records everything
    assert len(sched.journal.for_run(out["run_id"])) > 0
    # normal mode emits
    sched.configure(stealth_mode=False)
    out2 = sched.tick(at=time.time() + 3600)
    assert out2["ran"] is True
    assert "ambient.tick" in events and "ambient.task.completed" in events


def test_scheduler_rejects_short_interval(store):
    sched = AmbientScheduler(store=store)
    with pytest.raises(ValueError):
        sched.configure(enabled=True, interval_seconds=5)


def test_scheduler_unknown_task_is_journaled_not_fatal(store):
    sched = AmbientScheduler(store=store, tasks={})
    sched.configure(enabled=True, interval_seconds=60, tasks=["nope"])
    out = sched.tick()
    assert out["results"]["nope"]["ok"] is False
    assert any("unknown ambient task" in e.message for e in sched.journal.for_run(out["run_id"]))


def test_scheduler_task_failure_does_not_kill_tick(store):
    def bad(ctx):
        raise RuntimeError("task exploded")

    sched = AmbientScheduler(store=store, tasks={"bad": bad, "good": lambda ctx: {"summary": "ok"}})
    sched.configure(enabled=True, interval_seconds=60, tasks=["bad", "good"])
    out = sched.tick()
    assert out["ran"] is True
    assert out["results"]["bad"]["ok"] is False
    assert out["results"]["good"]["ok"] is True


# -- HTTP API ---------------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("SHADOW_AUTH_REQUIRED", "false")
    from fastapi.testclient import TestClient
    import shadow_node.main as main

    main.AUTH_REQUIRED = False

    def _reset_ambient():
        # isolate ambient state per test: disabled config, no last-tick memory
        sched = main.ambient_scheduler
        cfg = sched.get_config()
        cfg.enabled = False
        cfg.stealth_mode = False
        cfg.tasks = ["morning_brief"]
        cfg.last_tick_at = None
        sched._save_config(cfg)

    _reset_ambient()
    yield TestClient(main.app)
    _reset_ambient()


def test_ambient_status_default_disabled(client):
    r = client.get("/ambient/status").json()
    assert r["config"]["enabled"] is False
    assert "morning_brief" in r["tasks_available"]


def test_ambient_config_enable_and_manual_tick(client):
    r = client.post("/ambient/config", json={"enabled": True, "interval_seconds": 120,
                                             "tasks": ["morning_brief", "memory_digest"]})
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    tick = client.post("/ambient/tick").json()
    assert tick["ran"] is True
    assert set(tick["results"]) == {"morning_brief", "memory_digest"}
    assert tick["results"]["morning_brief"]["ok"] is True
    runs = client.get("/ambient/runs").json()
    assert any(cp["run_id"] == tick["run_id"] for cp in runs)


def test_ambient_config_rejects_short_interval(client):
    r = client.post("/ambient/config", json={"enabled": True, "interval_seconds": 5})
    assert r.status_code == 400


def test_ghost_run_endpoint_checkpoints_and_details(client):
    body = {"objective": "list notes twice", "steps": [
        {"tool": "note.list", "description": "first list", "params": {}},
        {"tool": "note.list", "description": "second list", "params": {}},
    ]}
    r = client.post("/ghost/runs", json=body).json()
    assert r["status"] == "completed"
    assert len(r["results"]) == 2
    run_id = r["run_id"]
    detail = client.get(f"/ambient/runs/{run_id}").json()
    assert detail["checkpoint"]["status"] == "completed"
    assert len(detail["journal"]) >= 6
    assert len(detail["executions"]) == 2
    # resume on a completed run is a no-op
    assert client.post(f"/ghost/runs/{run_id}/resume").json()["status"] == "already_completed"


def test_ghost_run_endpoint_validates_input(client):
    assert client.post("/ghost/runs", json={"objective": "", "steps": []}).status_code == 400
    assert client.post("/ghost/runs", json={"objective": "x", "steps": []}).status_code == 400
    assert client.post("/ghost/runs", json={"objective": "x", "steps": [{"nodesc": 1}]}).status_code == 400
    assert client.post("/ghost/runs/run_missing/resume").status_code == 404
    assert client.get("/ambient/runs/run_missing").status_code == 404


def test_claims_endpoints(client):
    c = client.post("/claims", json={"statement": "the node is reachable"}).json()
    assert c["status"] == "unconfirmed"
    got = client.get("/claims", params={"status": "unconfirmed"}).json()
    assert any(x["id"] == c["id"] for x in got)
    confirmed = client.post(f"/claims/{c['id']}/confirm", json={"evidence": "health check 200"}).json()
    assert confirmed["status"] == "confirmed"
    assert client.post(f"/claims/{c['id']}/confirm", json={"evidence": "again"}).status_code == 409
    assert client.post("/claims/clm_missing/confirm", json={"evidence": "x"}).status_code == 404
    c2 = client.post("/claims", json={"statement": "uptime is infinite"}).json()
    refuted = client.post(f"/claims/{c2['id']}/refute", json={"evidence": "restarted today"}).json()
    assert refuted["status"] == "refuted"


def test_ambient_tick_emits_sse_events(client):
    import shadow_node.main as main

    seen = []
    q = main.bus.subscribe()
    try:
        client.post("/ambient/config", json={"enabled": True, "interval_seconds": 60,
                                              "stealth_mode": False, "tasks": ["morning_brief"]})
        client.post("/ambient/tick")
        while not q.empty():
            seen.append(q.get_nowait()["type"])
    finally:
        main.bus.unsubscribe(q)
    assert "ambient.tick" in seen
    assert "ambient.task.completed" in seen


def test_ambient_tick_stealth_emits_no_sse(client):
    import shadow_node.main as main

    seen = []
    q = main.bus.subscribe()
    try:
        client.post("/ambient/config", json={"enabled": True, "interval_seconds": 60,
                                              "stealth_mode": True, "tasks": ["morning_brief"]})
        while not q.empty():
            q.get_nowait()  # drain the user-initiated config event; stealth covers the tick
        out = client.post("/ambient/tick").json()
        assert out["stealth_mode"] is True
        while not q.empty():
            seen.append(q.get_nowait()["type"])
    finally:
        main.bus.unsubscribe(q)
    assert not [t for t in seen if t.startswith("ambient.")]


# -- CLI ----------------------------------------------------------------------------

@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    db = str(tmp_path / "runtime.db")
    monkeypatch.setenv("SHADOW_RUNTIME_DB", db)
    monkeypatch.setenv("SHADOW_RUNTIME_KEY", Fernet.generate_key().decode())
    return db


def _run_cli(argv, capsys):
    from shadow_node.cli import main as cli_main

    rc = cli_main(argv)
    out = capsys.readouterr().out
    return rc, out


def test_cli_ambient_on_off_status(cli_env, capsys):
    rc, out = _run_cli(["ambient", "on", "--interval", "120"], capsys)
    assert rc == 0 and "ambient enabled" in out
    rc, out = _run_cli(["ambient", "status"], capsys)
    assert rc == 0 and "enabled:         True" in out and "interval:        120s" in out
    rc, out = _run_cli(["ambient", "off"], capsys)
    assert rc == 0 and "ambient disabled" in out
    rc, out = _run_cli(["ambient", "status"], capsys)
    assert "enabled:         False" in out


def test_cli_ambient_on_rejects_short_interval(cli_env, capsys):
    rc, out = _run_cli(["ambient", "on", "--interval", "5"], capsys)
    assert rc == 1


def test_cli_ambient_on_stealth(cli_env, capsys):
    rc, out = _run_cli(["ambient", "on", "--stealth", "--tasks", "morning_brief"], capsys)
    assert rc == 0 and "stealth" in out
    rc, out = _run_cli(["ambient", "status"], capsys)
    assert "stealth_mode:    True" in out


def test_cli_journal_and_claims(cli_env, capsys):
    from shadow_node.runtime_store import EncryptedRuntimeStore
    from agent_core import RunJournal, ClaimRegistry

    store = EncryptedRuntimeStore(cli_env)
    journal = RunJournal(store)
    journal.append("run_cli", "note", "hello journal")
    claims = ClaimRegistry(store)
    claim = claims.register("cli claim", run_id="run_cli")

    rc, out = _run_cli(["journal", "show", "run_cli"], capsys)
    assert rc == 0 and "hello journal" in out
    rc, out = _run_cli(["journal", "show", "run_missing"], capsys)
    assert rc == 1

    rc, out = _run_cli(["claims", "list"], capsys)
    assert rc == 0 and "cli claim" in out
    rc, out = _run_cli(["claims", "confirm", claim.id, "--evidence", "saw it"], capsys)
    assert rc == 0 and "confirmed" in out
    rc, out = _run_cli(["claims", "confirm", claim.id, "--evidence", "again"], capsys)
    assert rc == 1  # decided claims are final
    rc, out = _run_cli(["claims", "list", "--status", "confirmed"], capsys)
    assert "cli claim" in out
