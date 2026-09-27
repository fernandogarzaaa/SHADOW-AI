"""Reminders + quiet hours (Phase 5): CRUD, firing, recurrence, quiet gate, persistence, auth."""
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

from shadow_node.main import app
import shadow_node.main as main
from shadow_node.reminders import ReminderStore, ReminderCreate, fire_due
from shadow_node.feed import FeedStore
from shadow_node.runtime_store import EncryptedRuntimeStore
from agent_core.ambient import AmbientConfig


@pytest.fixture()
def client():
    main.AUTH_REQUIRED = False
    return TestClient(app)


def _mk(client, title="test reminder", due_at=None, **kw):
    r = client.post("/reminders", json={"title": title, "due_at": due_at or time.time() - 1, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_reminder_crud_validation(client):
    assert client.post("/reminders", json={"title": "  ", "due_at": 1}).status_code == 422
    assert client.post("/reminders", json={"title": "x", "due_at": 1, "recurrence": "yearly"}).status_code == 422
    r = _mk(client, "water the plants", note="the fern too", recurrence="daily")
    rid = r["id"]
    assert r["status"] == "pending"
    assert r["recurrence"] == "daily"

    assert client.get(f"/reminders/{rid}").status_code == 200
    assert client.get("/reminders/rem_missing").status_code == 404
    assert client.get("/reminders", params={"status": "bogus"}).status_code == 422

    p = client.patch(f"/reminders/{rid}", json={"status": "dismissed"})
    assert p.status_code == 200 and p.json()["status"] == "dismissed"
    assert client.patch(f"/reminders/{rid}", json={"status": "nope"}).status_code == 422
    assert client.patch(f"/reminders/{rid}", json={"recurrence": "nope"}).status_code == 422

    assert client.delete(f"/reminders/{rid}").status_code == 200
    assert client.get(f"/reminders/{rid}").status_code == 404
    assert client.delete(f"/reminders/{rid}").status_code == 404


def test_reminder_check_fires_and_records(client):
    r = _mk(client, "firing test", note="hello")
    rid = r["id"]
    try:
        due = client.get("/reminders/due").json()
        assert any(x["id"] == rid for x in due)

        res = client.post("/reminders/check").json()
        assert res["quiet"] is False
        assert any(x["id"] == rid for x in res["fired"])
        assert client.get(f"/reminders/{rid}").json()["status"] == "fired"

        # A reminder feed unit was recorded.
        kinds = [u["kind"] for u in client.get("/feed", params={"limit": 50}).json()["items"]]
        assert "reminder" in kinds
    finally:
        client.delete(f"/reminders/{rid}")


def test_reminder_recurrence_advances(client):
    now = time.time()
    r = _mk(client, "daily standup", due_at=now - 10, recurrence="daily")
    rid = r["id"]
    try:
        client.post("/reminders/check")
        got = client.get(f"/reminders/{rid}").json()
        assert got["status"] == "pending"  # stays pending, moves forward
        assert got["due_at"] > now
        assert got["last_fired_at"] is not None
    finally:
        client.delete(f"/reminders/{rid}")


def test_reminder_recurrence_no_catchup_burst():
    s = ReminderStore()
    now = time.time()
    r = s.create(ReminderCreate(title="old daily", due_at=now - 10 * 86400, recurrence="daily"))
    fired = s.fire(r.id, now)
    assert fired.status == "pending"
    assert fired.due_at > now
    assert fired.due_at <= now + 86400 + 1  # next occurrence only, no burst


def test_quiet_hours_hold_and_release(client):
    r = _mk(client, "quiet test")
    rid = r["id"]
    try:
        # Cover the whole day: quiet now.
        cfg = client.post("/ambient/config", json={"quiet_start": "00:00", "quiet_end": "23:59"}).json()
        assert cfg["quiet_start"] == "00:00"
        res = client.post("/reminders/check").json()
        assert res["quiet"] is True
        assert rid in res["held"]
        assert client.get(f"/reminders/{rid}").json()["status"] == "pending"

        # Bad HH:MM is rejected.
        assert client.post("/ambient/config", json={"quiet_start": "25:00"}).status_code == 400

        # Clearing quiet hours releases the reminder on the next check.
        client.post("/ambient/config", json={"quiet_start": "", "quiet_end": ""})
        res = client.post("/reminders/check").json()
        assert res["quiet"] is False
        assert any(x["id"] == rid for x in res["fired"])
    finally:
        client.post("/ambient/config", json={"quiet_start": "", "quiet_end": ""})
        client.delete(f"/reminders/{rid}")


def test_is_quiet_overnight():
    from datetime import datetime
    cfg = AmbientConfig(quiet_start="22:00", quiet_end="07:00")
    assert cfg.is_quiet(datetime(2026, 1, 1, 23, 30)) is True
    assert cfg.is_quiet(datetime(2026, 1, 1, 6, 59)) is True
    assert cfg.is_quiet(datetime(2026, 1, 1, 12, 0)) is False
    assert cfg.is_quiet(datetime(2026, 1, 1, 7, 0)) is False
    day = AmbientConfig(quiet_start="09:00", quiet_end="17:00")
    assert day.is_quiet(datetime(2026, 1, 1, 12, 0)) is True
    assert day.is_quiet(datetime(2026, 1, 1, 18, 0)) is False
    assert AmbientConfig().is_quiet(datetime(2026, 1, 1, 12, 0)) is False
    with pytest.raises(ValueError):
        AmbientConfig(quiet_start="nope")


def test_reminder_check_task_respects_quiet():
    from shadow_node.ambient_tasks import reminder_check
    store = ReminderStore()
    pushed = []
    ctx = {"reminders": store, "feed_store": FeedStore(),
           "is_quiet": lambda: True,
           "notify": lambda t, b, d: pushed.append(t),
           "publish": lambda e, p: None}
    store.create(ReminderCreate(title="held one", due_at=time.time() - 5))
    out = reminder_check(ctx)
    assert out["data"]["held"] == 1
    assert pushed == []
    assert store.list("pending") != []


def test_fire_due_unit_shape():
    store = ReminderStore()
    feed = FeedStore()
    events = []
    r = store.create(ReminderCreate(title="unit shape", note="body here", due_at=time.time() - 5))
    fired = fire_due(store, time.time(), lambda: False,
                     lambda t, b, d: None, lambda e, p: events.append((e, p)), feed)
    assert len(fired) == 1
    assert events[0][0] == "reminder.fired"
    assert events[0][1]["reminder_id"] == r.id
    units, _ = feed.list()
    assert units[0].kind == "reminder"
    assert units[0].title == "unit shape"
    assert "body here" in units[0].body


def test_reminder_persistence_across_restart():
    path = tempfile.NamedTemporaryFile().name
    key = EncryptedRuntimeStore(path, key=None).key
    s1 = ReminderStore(EncryptedRuntimeStore(path, key=key))
    r = s1.create(ReminderCreate(title="persistent reminder", due_at=time.time() + 3600))
    s2 = ReminderStore(EncryptedRuntimeStore(path, key=key))
    assert s2.get(r.id).title == "persistent reminder"
    assert s2.delete(r.id) is True
    s3 = ReminderStore(EncryptedRuntimeStore(path, key=key))
    assert s3.get(r.id) is None


def test_reminders_require_auth(client):
    main.AUTH_REQUIRED = True
    try:
        assert client.get("/reminders").status_code == 401
        assert client.post("/reminders", json={"title": "x", "due_at": 1}).status_code == 401
        assert client.get("/reminders/due").status_code == 401
        assert client.post("/reminders/check").status_code == 401
        assert client.get("/reminders/rem_x").status_code == 401
        assert client.patch("/reminders/rem_x", json={}).status_code == 401
        assert client.delete("/reminders/rem_x").status_code == 401
    finally:
        main.AUTH_REQUIRED = False
