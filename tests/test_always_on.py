"""Tests for the always-on agent loop: lifecycle, wake triggers, durable
sessions, and automatic context compaction."""
import datetime
import time

import pytest

from agent_core import (
    AgentSession,
    AmbientLoop,
    AmbientScheduler,
    GoogleCalendarWakeTrigger,
    InMemoryKV,
    LoopRecord,
    LoopState,
    MessageWakeTrigger,
    PushWakeTrigger,
    ReminderWakeTrigger,
    RunJournal,
    SessionCompactor,
    SessionStore,
    WakeEvent,
)


@pytest.fixture()
def store():
    return InMemoryKV()


@pytest.fixture()
def scheduler(store):
    calls = []

    def probe(ctx):
        calls.append(1)
        return {"summary": "probe ok"}

    sched = AmbientScheduler(store=store, journal=RunJournal(store),
                             tasks={"probe": probe})
    sched.calls = calls
    return sched


def _loop(scheduler, store, **kw):
    journal = RunJournal(store)
    loop = AmbientLoop(scheduler=scheduler, store=store, journal=journal, **kw)
    return loop, journal


def _wait_for(fn, timeout=5.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# -- lifecycle -------------------------------------------------------------

def test_loop_starts_sleeping_and_stops_cleanly(scheduler, store):
    loop, _ = _loop(scheduler, store)
    loop.start()
    try:
        assert _wait_for(lambda: loop.state == LoopState.SLEEPING)
        assert loop.is_running
    finally:
        loop.stop(timeout=5)
    assert loop.state == LoopState.STOPPED
    assert not loop.is_running
    # persisted loop record says clean
    recs = store.all("ambient_loop", LoopRecord)
    assert recs and recs[0].stopped_cleanly is True


def test_wake_transitions_awake_then_back_to_sleeping(scheduler, store):
    scheduler.configure(enabled=True, interval_seconds=3600, tasks=["probe"])
    loop, journal = _loop(scheduler, store)
    loop.start()
    try:
        assert _wait_for(lambda: loop.state == LoopState.SLEEPING)
        evt = loop.wake("operator", "test wake")
        assert evt.source == "operator"
        assert _wait_for(lambda: scheduler.calls, timeout=5.0), "tick never ran"
        assert _wait_for(lambda: loop.state == LoopState.SLEEPING, timeout=5.0)
        assert loop.wake_count == 1
        assert loop.last_wake_at is not None
        notes = [e.message for e in journal.for_run(f"loop_{id(loop):x}")]
        assert any("wake received [operator]" in m for m in notes)
        assert any("sleeping -> awake" in m for m in notes)
    finally:
        loop.stop(timeout=5)


def test_wake_while_disabled_stays_sleeping_but_journals(scheduler, store):
    # scheduler default: disabled
    loop, journal = _loop(scheduler, store)
    loop.start()
    try:
        assert _wait_for(lambda: loop.state == LoopState.SLEEPING)
        loop.wake("message", "hello?")
        assert _wait_for(
            lambda: any("wake held (ambient disabled)" in e.message
                        for e in journal.for_run(f"loop_{id(loop):x}")),
            timeout=5.0)
        time.sleep(0.3)
        assert loop.state == LoopState.SLEEPING
        assert scheduler.calls == []
    finally:
        loop.stop(timeout=5)


def test_wake_on_stopped_loop_raises(scheduler, store):
    loop, _ = _loop(scheduler, store)
    with pytest.raises(RuntimeError):
        loop.wake("operator", "too late")
    with pytest.raises(ValueError):
        # unknown source is rejected even on a live loop
        loop.start()
        try:
            loop.wake("telepathy", "x")
        finally:
            loop.stop(timeout=5)


def test_unclean_shutdown_detected_on_restart(scheduler, store):
    from agent_core import LoopRecord
    store.put("ambient_loop", "loop",
              LoopRecord(state="stopped", stopped_cleanly=False, wake_count=3))
    loop, journal = _loop(scheduler, store)
    loop.start()
    try:
        assert _wait_for(
            lambda: any("did not shut down cleanly" in e.message
                        for e in journal.for_run(f"loop_{id(loop):x}")),
            timeout=5.0)
    finally:
        loop.stop(timeout=5)


def test_idle_timeout_stretches_to_next_tick(scheduler, store):
    loop, _ = _loop(scheduler, store, idle_poll_seconds=30.0)
    try:
        # disabled: full idle poll
        assert loop._idle_timeout() == 30.0
        # enabled, tick far away: capped by idle poll
        scheduler.configure(enabled=True, interval_seconds=3600, tasks=["probe"])
        scheduler.tick()  # sets last_tick_at to now
        assert loop._idle_timeout() == pytest.approx(30.0, abs=1.0)
        # enabled, tick due soon: stretches down to the due time
        scheduler.configure(enabled=True, interval_seconds=60, tasks=["probe"])
        scheduler.tick()  # sets last_tick_at to now
        cfg = scheduler.get_config()
        cfg.last_tick_at = datetime.datetime.now(datetime.timezone.utc) \
            - datetime.timedelta(seconds=50)
        scheduler._save_config(cfg)
        assert loop._idle_timeout() == pytest.approx(10.0, abs=2.0)
    finally:
        loop.stop(timeout=5)


# -- wake triggers ---------------------------------------------------------

def test_push_and_message_triggers_deliver_to_loop(scheduler, store):
    scheduler.configure(enabled=True, interval_seconds=3600, tasks=["probe"])
    push = PushWakeTrigger()
    msg = MessageWakeTrigger()
    loop, _ = _loop(scheduler, store, triggers=(push, msg))
    loop.start()
    try:
        assert _wait_for(lambda: loop.state == LoopState.SLEEPING)
        push.deliver(device_id="dev1", action="tap")
        msg.deliver(session_id="ses_1", preview="hi")
        assert _wait_for(lambda: loop.wake_count == 2, timeout=5.0)
        assert _wait_for(lambda: len(scheduler.calls) >= 1, timeout=5.0)
    finally:
        loop.stop(timeout=5)


def test_unbound_trigger_deliver_raises():
    with pytest.raises(RuntimeError):
        PushWakeTrigger().deliver(device_id="d")
    with pytest.raises(RuntimeError):
        MessageWakeTrigger().deliver(preview="x")


def test_reminder_trigger_fires_due_reminder_once():
    fired = []
    # fixed timestamps: a real reminder store returns stable due_at values
    t_due = time.time() - 10
    t_future = time.time() + 10000

    def source():
        return [
            {"id": "r1", "title": "Standup", "due_at": t_due},
            {"id": "r2", "title": "Later", "due_at": t_future},
            {"id": "r3", "title": "Broken", "due_at": "not-a-time"},
        ]

    trig = ReminderWakeTrigger(source, lead_seconds=300.0)
    trig.bind(lambda src, reason, payload: fired.append((src, reason, payload))
              or WakeEvent(source=src, reason=reason, payload=payload))
    now = time.time()
    first = trig.poll(now)
    assert len(first) == 1
    assert first[0].source == "reminder"
    assert first[0].payload["reminder_id"] == "r1"
    # second poll: already fired, nothing new
    assert trig.poll(now + 5) == []


def test_reminder_trigger_wakes_loop(scheduler, store):
    scheduler.configure(enabled=True, interval_seconds=3600, tasks=["probe"])
    trig = ReminderWakeTrigger(
        lambda: [{"id": "r9", "title": "Due now", "due_at": time.time() - 1}],
        lead_seconds=300.0)
    loop, _ = _loop(scheduler, store, triggers=(trig,), idle_poll_seconds=1.0)
    loop.start()
    try:
        # the reminder poll fires on the first idle wakeup without any
        # explicit wake() call
        assert _wait_for(lambda: len(scheduler.calls) >= 1, timeout=8.0)
    finally:
        loop.stop(timeout=5)


# -- durable sessions ------------------------------------------------------

def test_session_survives_restart(store):
    s1 = SessionStore(store)
    ses = s1.create("test chat")
    s1.append(ses.id, "user", "hello")
    s1.append(ses.id, "assistant", "hi there")
    # fresh store over the same KV: simulates a process restart
    s2 = SessionStore(store)
    got = s2.get(ses.id)
    assert [m.role for m in got.messages] == ["user", "assistant"]
    assert got.messages[0].content == "hello"
    assert len(s2.list()) == 1


def test_session_unknown_and_closed(store):
    s = SessionStore(store)
    with pytest.raises(KeyError):
        s.get("ses_nope")
    ses = s.create("t")
    s.close(ses.id)
    assert s.get(ses.id).closed is True
    assert s.list() == []  # closed filtered by default
    assert len(s.list(open_only=False)) == 1
    with pytest.raises(ValueError):
        s.append(ses.id, "user", "too late")


def test_rehydrate_flags_interrupted_session(store):
    s1 = SessionStore(store)
    ses = s1.create("interrupted")
    s1.append(ses.id, "user", "are you there?")  # no assistant reply
    ok = s1.create("fine")
    s1.append(ok.id, "user", "q")
    s1.append(ok.id, "assistant", "a")

    s2 = SessionStore(store)
    report = s2.rehydrate()
    assert report == {"open": 2, "closed": 0, "flagged_interrupted": 1}
    assert s2.get(ses.id).metadata["response_interrupted"] is True
    assert "response_interrupted" not in s2.get(ok.id).metadata
    # idempotent: second rehydrate does not double-flag
    assert s2.rehydrate()["flagged_interrupted"] == 0


# -- compaction ------------------------------------------------------------

def _memory_engine(tmp_path):
    from memory_engine import EncryptedMemoryStore, MemoryEngine
    return MemoryEngine(EncryptedMemoryStore(path=str(tmp_path / "mem.db")))


def test_compaction_triggers_and_preserves_continuity(store, tmp_path):
    mem = _memory_engine(tmp_path)
    compactor = SessionCompactor(budget_tokens=120, keep_recent=2)
    s = SessionStore(store, compactor=compactor, memory=mem)
    ses = s.create("long chat")
    s.append(ses.id, "user", "My favorite editor is helix and I prefer dark mode.")
    for i in range(6):
        s.append(ses.id, "user", f"question number {i} about agents and tooling")
        s.append(ses.id, "assistant", f"answer number {i} with some detail here")

    got = s.get(ses.id)
    assert got.messages[0].kind == "compaction_summary"
    assert got.messages[0].role == "system"
    summary = got.messages[0].content
    assert "folded" in summary
    assert "helix" in summary  # key fact carried forward
    assert "Opening intent" in summary
    # recent window kept verbatim
    assert got.messages[-1].content.startswith("answer number 5")
    assert got.estimated_tokens <= 120 + 200  # back under budget (plus summary)
    # folded summary landed in user-owned memory
    hits = mem.search("favorite editor")
    assert hits and any("helix" in h.item.text for h in hits)


def test_compactor_report_numbers():
    c = SessionCompactor(budget_tokens=100, keep_recent=2)
    ses = AgentSession(title="t")
    for i in range(6):
        ses.append_message("user", "x" * 80)
    before = ses.estimated_tokens
    assert c.needs_compaction(ses)
    report = c.compact(ses)
    assert report.folded_count == 4
    assert report.kept_count == 2
    assert report.tokens_before == before
    assert report.tokens_after == ses.estimated_tokens
    assert report.tokens_after < report.tokens_before
    assert not c.needs_compaction(ses)


def test_no_compaction_without_compactor(store):
    s = SessionStore(store)  # no compactor wired
    ses = s.create("t")
    for i in range(20):
        s.append(ses.id, "user", "y" * 100)
    assert len(s.get(ses.id).messages) == 20


# -- HTTP API --------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("SHADOW_AUTH_REQUIRED", "false")
    from fastapi.testclient import TestClient
    import shadow_node.main as main

    main.AUTH_REQUIRED = False

    def _reset_ambient():
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


def _journal_has(main, text, timeout=5.0):
    run_id = f"loop_{id(main.ambient_loop):x}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(text in e.message for e in main.ambient_journal.for_run(run_id)):
            return True
        time.sleep(0.05)
    return False


def test_wake_endpoint_wakes_loop(client):
    import shadow_node.main as main
    client.post("/ambient/config", json={"enabled": True, "interval_seconds": 3600,
                                         "tasks": ["morning_brief"]})
    r = client.post("/ambient/wake", json={"source": "operator", "reason": "test"})
    assert r.status_code == 200
    body = r.json()
    assert body["wake_id"]
    assert body["loop_state"] in ("sleeping", "awake", "starting")
    assert _journal_has(main, "wake received [operator]")
    # the tick actually ran: an ambient checkpoint exists
    deadline = time.time() + 8.0
    seen = False
    while time.time() < deadline:
        cps = client.get("/ambient/runs").json()
        if any(cp.get("kind") == "ambient" for cp in cps):
            seen = True
            break
        time.sleep(0.1)
    assert seen, "loop never ran its tick after the wake"


def test_wake_endpoint_rejects_unknown_source(client):
    r = client.post("/ambient/wake", json={"source": "telepathy"})
    assert r.status_code == 400


def test_wake_endpoint_push_and_message_sources(client):
    import shadow_node.main as main
    r = client.post("/ambient/wake", json={"source": "push",
                                           "payload": {"device_id": "d1", "action": "tap"}})
    assert r.status_code == 200
    assert _journal_has(main, "wake received [push]")
    r = client.post("/ambient/wake", json={"source": "message",
                                           "payload": {"preview": "hello"}})
    assert r.status_code == 200
    assert _journal_has(main, "wake received [message]")


def test_session_endpoints_and_ask_session_flow(client):
    r = client.post("/agent/sessions", json={"title": "ask flow"})
    assert r.status_code == 200
    sid = r.json()["id"]

    r = client.post("/agent/ask", json={"prompt": "what are you", "session_id": sid})
    assert r.status_code == 200
    assert r.json()["session_id"] == sid

    detail = client.get(f"/agent/sessions/{sid}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "what are you"

    listed = client.get("/agent/sessions").json()
    assert any(s["id"] == sid for s in listed)

    r = client.post(f"/agent/sessions/{sid}/close")
    assert r.json()["closed"] is True

    r = client.post("/agent/ask", json={"prompt": "hi", "session_id": sid})
    assert r.status_code == 400  # closed session

    r = client.post("/agent/ask", json={"prompt": "hi", "session_id": "ses_nope"})
    assert r.status_code == 404


def test_ask_without_session_stays_stateless(client):
    r = client.post("/agent/ask", json={"prompt": "what are you"})
    assert r.status_code == 200
    assert r.json()["session_id"] is None


def test_ambient_status_reports_loop(client):
    body = client.get("/ambient/status").json()
    assert body["loop"]["state"] in ("sleeping", "awake", "starting", "stopped")
    assert "wake_count" in body["loop"]
    assert "sessions_open" in body["loop"]
