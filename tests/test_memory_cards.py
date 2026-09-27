"""Memory cards (Phase 2): GET /memory/recent (newest-first, paginated) and
DELETE /memory/{item_id} (revoke a single item)."""
import time
import tempfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from shadow_node.main import app
import shadow_node.main as main
from memory_engine import EncryptedMemoryStore, MemoryItem, MemorySource


@pytest.fixture()
def client():
    main.AUTH_REQUIRED = False
    return TestClient(app)


def _ingest(client, text, **kw):
    r = client.post("/memory/ingest", json={"text": text, "source_kind": "manual",
                                            "source_title": "card-test", **kw})
    assert r.status_code == 200
    return r.json()["items"]


def _revoke_all(client, items):
    for it in items:
        client.delete(f"/memory/{it['id']}")


def test_store_recent_orders_newest_first():
    store = EncryptedMemoryStore(path=tempfile.NamedTemporaryFile().name)
    src = MemorySource(kind="manual", title="t")
    store.add(MemoryItem(text="old card note", source=src,
                         created_at=datetime(2020, 1, 1, tzinfo=timezone.utc)))
    store.add(MemoryItem(text="new card note", source=src,
                         created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    page, total = store.recent()
    assert total == 2
    assert [i.text for i in page] == ["new card note", "old card note"]


def test_recent_newest_first_and_paginated(client):
    made = []
    made += _ingest(client, "zebra card alpha one")
    time.sleep(0.02)
    made += _ingest(client, "zebra card beta two")
    time.sleep(0.02)
    made += _ingest(client, "zebra card gamma three")
    try:
        r = client.get("/memory/recent", params={"limit": 2})
        assert r.status_code == 200
        body = r.json()
        assert body["limit"] == 2 and body["count"] == 2 and body["total"] >= 3
        texts = [i["text"] for i in body["items"]]
        assert texts[0] == "zebra card gamma three"
        assert texts[1] == "zebra card beta two"
        # offset shifts the window
        r2 = client.get("/memory/recent", params={"limit": 2, "offset": 1})
        texts2 = [i["text"] for i in r2.json()["items"]]
        assert texts2[0] == "zebra card beta two"
    finally:
        _revoke_all(client, made)


def test_recent_excludes_sensitive_by_default(client):
    made = _ingest(client, "zebra api key is secret-12345")
    try:
        assert made[0]["sensitive"] is True
        r = client.get("/memory/recent", params={"limit": 200})
        ids = [i["id"] for i in r.json()["items"]]
        assert made[0]["id"] not in ids
        r = client.get("/memory/recent", params={"limit": 200, "include_sensitive": "true"})
        assert made[0]["id"] in [i["id"] for i in r.json()["items"]]
    finally:
        _revoke_all(client, made)


def test_delete_item_revokes_and_404s(client):
    made = _ingest(client, "zebra card to forget")
    item_id = made[0]["id"]
    r = client.delete(f"/memory/{item_id}")
    assert r.status_code == 200
    assert r.json()["deleted_item"] == item_id
    # gone from search and recent
    assert not client.get("/memory/search", params={"q": "zebra card to forget"}).json()
    ids = [i["id"] for i in client.get("/memory/recent", params={"limit": 200}).json()["items"]]
    assert item_id not in ids
    # second delete is a 404
    assert client.delete(f"/memory/{item_id}").status_code == 404
    assert client.delete("/memory/mem_does_not_exist").status_code == 404


def test_recent_limit_clamped(client):
    r = client.get("/memory/recent", params={"limit": 500})
    assert r.status_code == 200
    assert r.json()["limit"] == 200


def test_memory_cards_require_auth(client):
    main.AUTH_REQUIRED = True
    try:
        assert client.get("/memory/recent").status_code == 401
        assert client.delete("/memory/mem_x").status_code == 401
    finally:
        main.AUTH_REQUIRED = False
