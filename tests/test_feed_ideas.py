"""Feed + Ideas (Phase 4): generation, dedupe, pagination, persistence, auth; idea lifecycle and run."""
import tempfile

import pytest
from fastapi.testclient import TestClient

from shadow_node.main import app
import shadow_node.main as main
from shadow_node.feed import FeedStore, generate_units
from shadow_node.ideas import IdeaStore, IdeaCreate
from shadow_node.runtime_store import EncryptedRuntimeStore


@pytest.fixture()
def client():
    main.AUTH_REQUIRED = False
    return TestClient(app)


def test_feed_generate_and_list(client):
    r = client.post("/feed/generate", json={"force": True})
    assert r.status_code == 200, r.text
    kinds = {u["kind"] for u in r.json()["units"]}
    assert {"morning_brief", "goals_briefing", "memory_digest"} <= kinds

    r = client.get("/feed", params={"limit": 2})
    body = r.json()
    assert body["count"] == 2
    assert body["total"] >= 3
    assert body["limit"] == 2
    items = body["items"]
    assert items[0]["created_at"] >= items[1]["created_at"]  # newest first
    assert all(u["title"] and u["body"] for u in items)


def test_feed_dedupe_per_kind(client):
    # Without force, kinds generated recently are skipped.
    r = client.post("/feed/generate", json={"force": True})
    assert r.json()["count"] >= 3
    r = client.post("/feed/generate", json={})
    assert r.json()["count"] == 0
    r = client.post("/feed/generate", json={"force": True})
    assert r.json()["count"] >= 3


def test_feed_generate_validation(client):
    assert client.post("/feed/generate", json={"kinds": ["nope"]}).status_code == 422
    r = client.post("/feed/generate", json={"kinds": ["goals_briefing"], "force": True})
    assert r.status_code == 200
    assert {u["kind"] for u in r.json()["units"]} == {"goals_briefing"}


def test_feed_persistence_across_restart():
    path = tempfile.NamedTemporaryFile().name
    key = EncryptedRuntimeStore(path, key=None).key
    s1 = FeedStore(EncryptedRuntimeStore(path, key=key))
    units = generate_units(s1, ["morning_brief"], {"morning_brief": lambda: ("T", "B")}, force=True)
    assert len(units) == 1
    s2 = FeedStore(EncryptedRuntimeStore(path, key=key))
    items, total = s2.list()
    assert total == 1
    assert items[0].title == "T"
    # The dedupe marker survived the restart too.
    assert s2.due_kinds(["morning_brief"], now=units[0].created_at + 1) == []


def test_idea_lifecycle(client):
    r = client.post("/ideas", json={"title": "  ", "description": "x"})
    assert r.status_code == 422
    r = client.post("/ideas", json={"title": "Build a habit tracker", "description": "local-first"})
    assert r.status_code == 201, r.text
    idea = r.json()
    assert idea["status"] == "new"
    iid = idea["id"]

    assert client.get(f"/ideas/{iid}").status_code == 200
    assert client.get("/ideas/idea_missing").status_code == 404
    assert client.get("/ideas", params={"status": "bogus"}).status_code == 422

    r = client.patch(f"/ideas/{iid}", json={"status": "dismissed"})
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"
    assert any(i["id"] == iid for i in client.get("/ideas", params={"status": "dismissed"}).json())
    assert client.patch(f"/ideas/{iid}", json={"status": "nope"}).status_code == 422

    r = client.delete(f"/ideas/{iid}")
    assert r.status_code == 200
    assert client.get(f"/ideas/{iid}").status_code == 404
    assert client.delete(f"/ideas/{iid}").status_code == 404


def test_idea_run_produces_plan_and_approvals(client):
    r = client.post("/ideas", json={"title": "Summarize my recent memory items", "description": "read-only digest"})
    iid = r.json()["id"]
    try:
        r = client.post(f"/ideas/{iid}/run")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["idea"]["status"] == "running"
        assert len(body["idea"]["plan"]) == len(body["plan"]["actions"])
        assert len(body["plan"]["actions"]) >= 1
        # The run itself executes nothing; it only plans. Approval-gating
        # happens through the normal /agent/execute path.
        assert client.post(f"/ideas/idea_missing/run").status_code == 404
    finally:
        client.delete(f"/ideas/{iid}")


def test_idea_persistence_across_restart():
    path = tempfile.NamedTemporaryFile().name
    key = EncryptedRuntimeStore(path, key=None).key
    s1 = IdeaStore(EncryptedRuntimeStore(path, key=key))
    idea = s1.create(IdeaCreate(title="persistent idea"))
    s2 = IdeaStore(EncryptedRuntimeStore(path, key=key))
    assert s2.get(idea.id).title == "persistent idea"
    assert s2.delete(idea.id) is True
    s3 = IdeaStore(EncryptedRuntimeStore(path, key=key))
    assert s3.get(idea.id) is None


def test_feed_ideas_require_auth(client):
    main.AUTH_REQUIRED = True
    try:
        assert client.get("/feed").status_code == 401
        assert client.post("/feed/generate", json={}).status_code == 401
        assert client.get("/ideas").status_code == 401
        assert client.post("/ideas", json={"title": "x"}).status_code == 401
        assert client.get("/ideas/idea_x").status_code == 401
        assert client.patch("/ideas/idea_x", json={}).status_code == 401
        assert client.delete("/ideas/idea_x").status_code == 401
        assert client.post("/ideas/idea_x/run").status_code == 401
    finally:
        main.AUTH_REQUIRED = False
