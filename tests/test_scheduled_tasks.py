"""Scheduled tasks (Hark item 4): NL parser, unified API, new recurrences."""

import datetime
import time

import pytest
from fastapi.testclient import TestClient
from shadow_node import main
from shadow_node.main import app
from shadow_node.reminders import (
    RECURRENCES,
    ReminderCreate,
    ReminderStore,
    ReminderUpdate,
)
from shadow_node.schedule_parse import describe_cadence, parse_schedule


@pytest.fixture()
def client():
    main.AUTH_REQUIRED = False
    return TestClient(app)


def _mk(client, title="sched test", due_at=None, **kw):
    r = client.post(
        "/reminders", json={"title": title, "due_at": due_at or time.time() - 1, **kw}
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- NL parser -----------------------------------------------------------

# Monday 2026-10-12 10:00 local, fixed for deterministic tests.
_NOW = datetime.datetime(2026, 10, 12, 10, 0).timestamp()


def _due_str(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%a %m-%d %H:%M")


@pytest.mark.parametrize(
    "text,title,rec,due",
    [
        (
            "remind me to water the plants every weekday at 7am",
            "water the plants",
            "weekdays",
            "Tue 10-13 07:00",
        ),
        (
            "remind me every day at 7am to stretch",
            "stretch",
            "daily",
            "Tue 10-13 07:00",
        ),
        (
            "remind me every hour to drink water",
            "drink water",
            "hourly",
            "Mon 10-12 11:00",
        ),
        (
            "remind me every monday at 9am to review PRs",
            "review PRs",
            "weekly",
            "Mon 10-19 09:00",
        ),
        ("remind me in 2 hours to call mom", "call mom", "none", "Mon 10-12 12:00"),
        (
            "remind me in 30 minutes to check the oven",
            "check the oven",
            "none",
            "Mon 10-12 10:30",
        ),
        (
            "remind me tomorrow at 9am to send the report",
            "send the report",
            "none",
            "Tue 10-13 09:00",
        ),
        ("remind me at 3pm to pick up kids", "pick up kids", "none", "Mon 10-12 15:00"),
        ("remind me on friday at 5pm to log off", "log off", "none", "Fri 10-16 17:00"),
        ("remind me at noon to eat lunch", "eat lunch", "none", "Mon 10-12 12:00"),
    ],
)
def test_parse_cadences(text, title, rec, due):
    r = parse_schedule(text, now=_NOW)
    assert r.status == "parsed", (text, r.question)
    p = r.proposal
    assert p.title == title
    assert p.recurrence == rec
    assert _due_str(p.due_at) == due
    assert p.plain_cadence  # non-empty plain words


@pytest.mark.parametrize(
    "text,question_part",
    [
        ("remind me every 2 hours to stand", "every hour"),
        ("remind me every 30 minutes to blink", "hourly"),
        ("remind me at 7 to eat", "Morning or evening"),
        ("remind me every day at 7am", "What should I remind you about"),
        ("remind me every day", "What time each day"),
        ("remind me to buy milk", "couldn't tell when"),
        ("remind me", "What should I remind you about"),
    ],
)
def test_parse_ambiguous_never_guesses(text, question_part):
    r = parse_schedule(text, now=_NOW)
    assert r.status == "needs_clarification", text
    assert r.proposal is None
    assert question_part in r.question, r.question


def test_parse_not_a_request():
    r = parse_schedule("what is the weather like", now=_NOW)
    assert r.status == "not_a_request"
    assert r.proposal is None and r.question is None


def test_parse_plain_cadence_words():
    assert describe_cadence("hourly", _NOW, now=_NOW) == "Every hour"
    assert describe_cadence("daily", _NOW, now=_NOW).startswith("Every day at")
    assert describe_cadence("weekdays", _NOW, now=_NOW).startswith("Every weekday at")
    assert describe_cadence("weekly", _NOW, now=_NOW).startswith("Every Monday")
    assert describe_cadence("none", _NOW, now=_NOW).startswith("Once today")
    with pytest.raises(ValueError):
        describe_cadence("yearly", _NOW)


def test_parse_weekday_first_run_skips_weekend():
    # Friday 2026-10-16 18:00: next weekday 7am is Monday 10-19.
    fri = datetime.datetime(2026, 10, 16, 18, 0).timestamp()
    r = parse_schedule("remind me to stand up every weekday at 7am", now=fri)
    assert r.status == "parsed"
    assert _due_str(r.proposal.due_at) == "Mon 10-19 07:00"


# --- new recurrences + enabled flag --------------------------------------


def test_recurrences_include_new():
    assert set(RECURRENCES) == {"none", "hourly", "daily", "weekdays", "weekly"}


def test_hourly_fire_advances_one_hour():
    store = ReminderStore()
    now = time.time()
    r = store.create(ReminderCreate(title="h", due_at=now - 10, recurrence="hourly"))
    due_before = r.due_at
    fired = store.fire(r.id, now)
    assert fired.status == "pending"
    assert abs(fired.due_at - (due_before + 3600)) < 1


def test_weekdays_fire_skips_weekend():
    store = ReminderStore()
    # Friday 2026-10-16 07:00 local -> next is Monday 10-19 07:00.
    fri = datetime.datetime(2026, 10, 16, 7, 0).timestamp()
    r = store.create(ReminderCreate(title="w", due_at=fri, recurrence="weekdays"))
    fired = store.fire(r.id, fri + 60)
    assert fired.status == "pending"
    assert _due_str(fired.due_at) == "Mon 10-19 07:00"


def test_weekdays_fire_midweek_advances_one_day():
    store = ReminderStore()
    tue = datetime.datetime(2026, 10, 13, 7, 0).timestamp()
    r = store.create(ReminderCreate(title="w", due_at=tue, recurrence="weekdays"))
    fired = store.fire(r.id, tue + 60)
    assert _due_str(fired.due_at) == "Wed 10-14 07:00"


def test_disabled_reminder_never_due_or_fires():
    store = ReminderStore()
    now = time.time()
    r = store.create(ReminderCreate(title="d", due_at=now - 10, enabled=False))
    assert r.id not in [x.id for x in store.due(now)]
    assert store.fire(r.id, now) is None
    # Re-enabling makes it due again.
    store.update(r.id, ReminderUpdate(enabled=True))
    assert r.id in [x.id for x in store.due(now)]


# --- unified API ----------------------------------------------------------


def test_parse_endpoint(client):
    r = client.post(
        "/reminders/parse", json={"text": "remind me every weekday at 7am to stretch"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "parsed"
    assert body["proposal"]["recurrence"] == "weekdays"
    assert body["proposal"]["title"] == "stretch"

    r = client.post("/reminders/parse", json={"text": "remind me at 7"})
    assert r.json()["status"] == "needs_clarification"
    assert "Morning or evening" in r.json()["question"]

    r = client.post("/reminders/parse", json={"text": "hello there"})
    assert r.json()["status"] == "not_a_request"

    assert client.post("/reminders/parse", json={"text": ""}).status_code == 422


def test_scheduled_tasks_lists_reminders_and_ambient(client):
    r = _mk(client, "unified list probe", recurrence="daily")
    rid = r["id"]
    try:
        items = client.get("/scheduled-tasks").json()
        kinds = {i["kind"] for i in items}
        assert "reminder" in kinds and "ambient_task" in kinds
        mine = next(i for i in items if i["id"] == rid)
        assert mine["title"] == "unified list probe"
        assert mine["cadence"].startswith("Every day at")
        assert mine["enabled"] is True
        assert mine["next_run"] is not None
        # All five builtin ambient tasks are visible: no hidden schedules.
        ambient_ids = {i["id"] for i in items if i["kind"] == "ambient_task"}
        for name in (
            "morning_brief",
            "memory_digest",
            "feed_digest",
            "reminder_check",
            "shadow_acts",
        ):
            assert f"ambient:{name}" in ambient_ids
    finally:
        client.delete(f"/reminders/{rid}")


def test_scheduled_tasks_crud_roundtrip(client):
    r = client.post(
        "/scheduled-tasks",
        json={
            "title": "unified create",
            "due_at": time.time() + 3600,
            "recurrence": "weekdays",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "reminder"
    assert body["recurrence"] == "weekdays"
    assert body["cadence"].startswith("Every weekday at")
    tid = body["id"]

    got = client.get(f"/scheduled-tasks/{tid}").json()
    assert got["title"] == "unified create"

    p = client.patch(f"/scheduled-tasks/{tid}", json={"enabled": False})
    assert p.status_code == 200 and p.json()["enabled"] is False
    assert p.json()["next_run"] is None  # disabled: nothing scheduled

    p = client.patch(
        f"/scheduled-tasks/{tid}", json={"enabled": True, "title": "renamed"}
    )
    assert p.json()["enabled"] is True and p.json()["title"] == "renamed"

    assert client.delete(f"/scheduled-tasks/{tid}").status_code == 200
    assert client.get(f"/scheduled-tasks/{tid}").status_code == 404


def test_scheduled_tasks_ambient_toggle(client):
    tid = "ambient:morning_brief"
    before = client.get(f"/scheduled-tasks/{tid}").json()
    assert before["kind"] == "ambient_task"

    p = client.patch(f"/scheduled-tasks/{tid}", json={"enabled": False})
    assert p.status_code == 200
    assert p.json()["enabled"] is False

    p = client.patch(f"/scheduled-tasks/{tid}", json={"enabled": True})
    assert p.json()["enabled"] is False  # scheduler itself is disabled by default

    # Ambient tasks only accept `enabled`.
    assert (
        client.patch(f"/scheduled-tasks/{tid}", json={"title": "x"}).status_code == 422
    )
    assert client.delete(f"/scheduled-tasks/{tid}").status_code == 422
    assert client.get("/scheduled-tasks/ambient:nope").status_code == 404
    assert client.get("/scheduled-tasks/rem_missing").status_code == 404
    assert client.get("/scheduled-tasks/bogus:id").status_code == 404


def test_scheduled_tasks_validation(client):
    r = client.post(
        "/scheduled-tasks", json={"title": "x", "due_at": 1, "recurrence": "yearly"}
    )
    assert r.status_code == 422
    r = client.post(
        "/scheduled-tasks", json={"title": "unified val", "due_at": time.time() + 60}
    )
    tid = r.json()["id"]
    try:
        assert (
            client.patch(
                f"/scheduled-tasks/{tid}", json={"recurrence": "yearly"}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                f"/scheduled-tasks/{tid}", json={"status": "bogus"}
            ).status_code
            == 422
        )
    finally:
        client.delete(f"/scheduled-tasks/{tid}")
