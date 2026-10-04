"""Goals (Phase 3): CRUD, progress entries, briefing, persistence, auth."""
import tempfile
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from shadow_node.main import app
import shadow_node.main as main
from shadow_node.goals import GoalStore, GoalCreate, ProgressCreate
from shadow_node.runtime_store import EncryptedRuntimeStore


@pytest.fixture()
def client():
    main.AUTH_REQUIRED = False
    return TestClient(app)


def _create(client, title="Ship SHADOW iOS", **kw):
    r = client.post("/goals", json={"title": title, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_goal_crud_roundtrip(client):
    g = _create(client, description="via TestFlight")
    assert g["status"] == "active"
    assert g["id"].startswith("goal_")

    r = client.get(f"/goals/{g['id']}")
    assert r.status_code == 200
    assert r.json()["entries"] == []

    r = client.patch(f"/goals/{g['id']}", json={"status": "completed"})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"

    r = client.get("/goals", params={"status": "active"})
    assert all(x["id"] != g["id"] for x in r.json())
    r = client.get("/goals", params={"status": "completed"})
    assert any(x["id"] == g["id"] for x in r.json())

    r = client.delete(f"/goals/{g['id']}")
    assert r.status_code == 200
    assert client.get(f"/goals/{g['id']}").status_code == 404
    assert client.delete(f"/goals/{g['id']}").status_code == 404


def test_goal_validation(client):
    assert client.post("/goals", json={"title": "   "}).status_code == 422
    assert client.post("/goals", json={"title": "t" * 121}).status_code == 422
    assert client.post("/goals", json={"title": "x", "target_date": "next friday"}).status_code == 422
    assert client.post("/goals", json={"title": "x", "target_date": "2026-02-30"}).status_code == 422
    g = _create(client, title="validation target")
    assert client.patch(f"/goals/{g['id']}", json={"status": "done-ish"}).status_code == 422
    assert client.patch(f"/goals/{g['id']}", json={"title": ""}).status_code == 422
    assert client.get("/goals", params={"status": "bogus"}).status_code == 422
    client.delete(f"/goals/{g['id']}")


def test_target_date_set_and_clear(client):
    g = _create(client, title="dated goal", target_date="2026-12-31")
    assert g["target_date"] == "2026-12-31"
    r = client.patch(f"/goals/{g['id']}", json={"target_date": ""})
    assert r.status_code == 200
    assert r.json()["target_date"] is None
    client.delete(f"/goals/{g['id']}")


def test_progress_entries_newest_first_and_rollup(client):
    g = _create(client, title="progress goal")
    gid = g["id"]
    assert client.post(f"/goals/{gid}/progress", json={"note": ""}).status_code == 422
    assert client.post(f"/goals/{gid}/progress", json={"note": "ok", "percent": 101}).status_code == 422
    assert client.post("/goals/goal_missing/progress", json={"note": "x"}).status_code == 404

    client.post(f"/goals/{gid}/progress", json={"note": "first step", "percent": 10})
    time.sleep(0.02)
    client.post(f"/goals/{gid}/progress", json={"note": "second step"})
    detail = client.get(f"/goals/{gid}").json()
    assert [e["note"] for e in detail["entries"]] == ["second step", "first step"]

    summaries = {x["id"]: x for x in client.get("/goals").json()}
    s = summaries[gid]
    assert s["entry_count"] == 2
    assert s["latest_percent"] == 10  # newest entry with a percent
    assert s["last_progress_at"] is not None
    client.delete(f"/goals/{gid}")


def test_briefing_flags_stale_due_overdue(client):
    stale = _create(client, title="stale goal")
    due = _create(client, title="due goal",
                  target_date=(date.today() + timedelta(days=2)).isoformat())
    over = _create(client, title="overdue goal", target_date="2020-01-01")
    fresh = _create(client, title="fresh goal")
    client.post(f"/goals/{fresh['id']}/progress", json={"note": "moving"})
    try:
        # Backdate the stale goal: no progress since creation 30 days ago.
        main.goal_store.goals[stale["id"]].created_at = time.time() - 30 * 86400
        main.goal_store.goals[stale["id"]].updated_at = time.time() - 30 * 86400
        main.goal_store.goals[due["id"]].created_at = time.time()
        main.goal_store.goals[over["id"]].created_at = time.time()

        b = client.get("/goals/briefing").json()
        assert b["active_count"] >= 4
        stale_ids = [x["id"] for x in b["stale"]]
        assert stale["id"] in stale_ids
        assert fresh["id"] not in stale_ids
        assert due["id"] in [x["id"] for x in b["due_soon"]]
        assert over["id"] in [x["id"] for x in b["overdue"]]
        assert fresh["id"] in [e["goal_id"] for e in b["recent_entries"]]

        # Completing a goal moves it to completed_this_week.
        client.patch(f"/goals/{fresh['id']}", json={"status": "completed"})
        b = client.get("/goals/briefing").json()
        assert fresh["id"] in [x["id"] for x in b["completed_this_week"]]
        assert b["completed_count"] >= 1
    finally:
        for g in (stale, due, over, fresh):
            client.delete(f"/goals/{g['id']}")


def test_goal_persistence_across_restart():
    path = tempfile.NamedTemporaryFile().name
    key = EncryptedRuntimeStore(path, key=None).key
    s1 = GoalStore(EncryptedRuntimeStore(path, key=key))
    g = s1.create(GoalCreate(title="persistent goal", target_date="2026-11-01"))
    e = s1.add_progress(g.id, ProgressCreate(note="kept", percent=25))
    # Fresh store over the same DB file: everything comes back.
    s2 = GoalStore(EncryptedRuntimeStore(path, key=key))
    assert s2.get(g.id).title == "persistent goal"
    assert s2.get(g.id).target_date == "2026-11-01"
    assert s2.entries[e.id].note == "kept"
    assert s2.delete(g.id) is True
    s3 = GoalStore(EncryptedRuntimeStore(path, key=key))
    assert s3.get(g.id) is None
    assert e.id not in s3.entries


def test_goals_require_auth(client):
    main.AUTH_REQUIRED = True
    try:
        assert client.get("/goals").status_code == 401
        assert client.post("/goals", json={"title": "x"}).status_code == 401
        assert client.get("/goals/briefing").status_code == 401
        assert client.get("/goals/goal_x").status_code == 401
        assert client.patch("/goals/goal_x", json={}).status_code == 401
        assert client.delete("/goals/goal_x").status_code == 401
        assert client.post("/goals/goal_x/progress", json={"note": "x"}).status_code == 401
    finally:
        main.AUTH_REQUIRED = False
