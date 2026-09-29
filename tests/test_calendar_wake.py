"""Tests for the real Google Calendar wake source.

The trigger is exercised with a fake runner standing in for
`hatch_gws_cli calendar +agenda --format json`, using the exact JSON
shape the CLI returns in production. The one live-thread test proves the
trigger wakes the ambient loop end to end.
"""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from agent_core import (
    AmbientLoop,
    AmbientScheduler,
    GoogleCalendarWakeTrigger,
    InMemoryKV,
    RunJournal,
    WakeEvent,
)

PLUS8 = timezone(timedelta(hours=8))


def iso(ts):
    return datetime.fromtimestamp(ts, tz=PLUS8).isoformat()


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_runner(events=None, returncode=0, stdout=None, stderr=""):
    """Fake hatch_gws_cli runner. Returns (runner, calls)."""
    calls = []
    payload = {"events": events if events is not None else []}

    def runner(argv):
        calls.append(argv)
        out = stdout if stdout is not None else json.dumps(payload)
        return FakeProc(returncode=returncode, stdout=out, stderr=stderr)

    return runner, calls


def bind(trig):
    fired = []
    trig.bind(lambda src, reason, payload:
              fired.append((src, reason, payload))
              or WakeEvent(source=src, reason=reason, payload=payload))
    return fired


def test_fires_once_for_event_in_lead_window():
    now = time.time()
    ev = {"summary": "Rust Developer Interview: Fernando",
          "calendar": "Work",
          "start": iso(now + 120),
          "end": iso(now + 3720)}
    runner, calls = make_runner(events=[ev])
    trig = GoogleCalendarWakeTrigger(runner=runner, lead_seconds=300.0)
    fired = bind(trig)

    first = trig.poll(now)
    assert len(first) == 1
    assert first[0].source == "calendar"
    assert first[0].payload["summary"] == "Rust Developer Interview: Fernando"
    assert first[0].payload["start"] == iso(now + 120)
    assert len(fired) == 1
    # CLI argv is the real agenda invocation
    assert calls[0] == ["calendar", "+agenda", "--days", "2", "--format", "json"]
    # second poll: same event, no double wake (and cache means no new fetch)
    assert trig.poll(now + 5) == []


def test_skips_far_out_long_over_and_all_day_events():
    now = time.time()
    events = [
        {"summary": "Too far", "start": iso(now + 3600)},
        {"summary": "Long over", "start": iso(now - 3600)},
        {"summary": "All day", "start": "2026-09-29"},  # date-only, no lead window
        {"summary": "Broken", "start": "not-a-time"},
        {"summary": "Just started", "start": iso(now - 120)},
    ]
    runner, _ = make_runner(events=events)
    trig = GoogleCalendarWakeTrigger(runner=runner, lead_seconds=300.0)
    bind(trig)
    got = trig.poll(now)
    assert [e.payload["summary"] for e in got] == ["Just started"]


def test_cli_failure_degrades_without_raising():
    now = time.time()
    runner, _ = make_runner(returncode=1, stdout="", stderr="auth expired")
    trig = GoogleCalendarWakeTrigger(runner=runner)
    bind(trig)
    assert trig.poll(now) == []
    st = trig.status()
    assert st["name"] == "calendar"
    assert "auth expired" in st["last_error"]
    assert st["fired_total"] == 0
    # still healthy afterwards: a recovered CLI fires normally
    ev = {"summary": "Standup", "start": iso(now + 60)}
    trig._runner, _ = make_runner(events=[ev])
    trig._cache_at = 0.0
    got = trig.poll(now + 1)
    assert len(got) == 1
    assert trig.status()["last_error"] is None


def test_unparsable_output_degrades_without_raising():
    runner, _ = make_runner(stdout="not json at all{")
    trig = GoogleCalendarWakeTrigger(runner=runner)
    bind(trig)
    assert trig.poll(time.time()) == []
    assert "unparsable" in trig.status()["last_error"]
    # an object without an events list also degrades
    trig._runner, _ = make_runner(stdout=json.dumps({"nope": 1}))
    trig._cache_at = 0.0
    assert trig.poll(time.time()) == []
    assert "no events list" in trig.status()["last_error"]


def test_missing_cli_degrades_without_raising():
    def boom(argv):
        raise FileNotFoundError("hatch_gws_cli not on PATH")
    trig = GoogleCalendarWakeTrigger(runner=boom)
    bind(trig)
    assert trig.poll(time.time()) == []
    assert "hatch_gws_cli" in trig.status()["last_error"]


def test_refresh_caches_between_polls():
    now = time.time()
    runner, calls = make_runner(events=[])
    trig = GoogleCalendarWakeTrigger(runner=runner, refresh_seconds=300.0)
    bind(trig)
    trig.poll(now)
    trig.poll(now + 10)
    assert len(calls) == 1  # second poll used the cache
    trig.poll(now + 301)
    assert len(calls) == 2  # refresh window passed: refetched


def test_unbound_poll_raises():
    with pytest.raises(RuntimeError):
        GoogleCalendarWakeTrigger(runner=make_runner()[0]).poll(time.time())


def test_calendar_trigger_wakes_loop():
    store = InMemoryKV()
    calls = []

    def probe(ctx):
        calls.append(1)
        return {"summary": "probe ok"}

    scheduler = AmbientScheduler(store=store, journal=RunJournal(store),
                                 tasks={"probe": probe})
    scheduler.configure(enabled=True, interval_seconds=3600, tasks=["probe"])
    runner, _ = make_runner(events=[
        {"summary": "Starting now", "start": iso(time.time() + 2)}])
    trig = GoogleCalendarWakeTrigger(runner=runner, lead_seconds=300.0,
                                     refresh_seconds=60.0)
    journal = RunJournal(store)
    loop = AmbientLoop(scheduler=scheduler, store=store, journal=journal,
                       triggers=(trig,), idle_poll_seconds=1.0)
    loop.start()
    try:
        deadline = time.time() + 8.0
        while len(calls) < 1 and time.time() < deadline:
            time.sleep(0.1)
        assert len(calls) >= 1, "calendar event did not wake the loop"
    finally:
        loop.stop(timeout=5)
