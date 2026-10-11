"""Tests for cross-device assistant continuity (Hark backlog item 11).

Covers the HandoffStore unit behavior, session device linkage, presence
heartbeats, and the HTTP routes: explicit handoff create/claim/cancel plus
the continuity overview.
"""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
import shadow_node.continuity as cont
import shadow_node.main as m
from agent_core import AgentAction, InMemoryKV, SessionStore
from fastapi.testclient import TestClient
from shadow_node.continuity import (
    HANDOFF_TTL,
    HandoffRecord,
    HandoffStatus,
    HandoffStore,
    build_session_snapshot,
    list_presence,
    note_presence,
)


@pytest.fixture()
def kv():
    return InMemoryKV()


@pytest.fixture()
def store():
    return HandoffStore(kv=InMemoryKV())


@pytest.fixture()
def no_auth(monkeypatch):
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)


@pytest.fixture()
def client(no_auth):
    return TestClient(m.app)


def _session(**kw):
    s = m.session_store.create(kw.get("title", "t"))
    s.append_message("user", "hello")
    s.append_message("assistant", "hi there")
    return s


def _device(name="phone"):
    return m.sessions.register(name=name, public_key="pubkey-" + name)


# --- HandoffStore unit tests -------------------------------------------------


def test_create_and_get_roundtrip(store):
    r = store.create(session_id="ses_1", from_device_id="dev_a")
    assert r.id.startswith("handoff_")
    assert r.status is HandoffStatus.PENDING
    assert store.get(r.id).id == r.id


def test_get_unknown_raises(store):
    with pytest.raises(KeyError):
        store.get("handoff_nope")


def test_snapshot_frozen_at_create(store):
    snap = {"session_id": "ses_1", "message_count": 2, "messages": []}
    r = store.create(session_id="ses_1", from_device_id="dev_a", snapshot=snap)
    assert store.get(r.id).snapshot["message_count"] == 2


def test_claim_marks_claimed(store):
    r = store.create(session_id="ses_1", from_device_id="dev_a")
    claimed = store.claim(r.id, "dev_b")
    assert claimed.status is HandoffStatus.CLAIMED
    assert claimed.claimed_by_device_id == "dev_b"
    assert claimed.claimed_at is not None


def test_double_claim_rejected(store):
    r = store.create(session_id="ses_1", from_device_id="dev_a")
    store.claim(r.id, "dev_b")
    with pytest.raises(ValueError, match="not pending"):
        store.claim(r.id, "dev_c")


def test_claim_targeted_at_other_device_is_indistinguishable(store):
    r = store.create(
        session_id="ses_1", from_device_id="dev_a", target_device_id="dev_b"
    )
    with pytest.raises(KeyError):
        store.claim(r.id, "dev_evil")
    # the intended target can still claim
    assert store.claim(r.id, "dev_b").status is HandoffStatus.CLAIMED


def test_expired_handoff_cannot_be_claimed(store):
    r = store.create(session_id="ses_1", from_device_id="dev_a")
    r.created_at = r.created_at - HANDOFF_TTL - timedelta(seconds=1)
    with pytest.raises(ValueError, match="expired"):
        store.claim(r.id, "dev_b")
    assert store.get(r.id).status is HandoffStatus.EXPIRED


def test_list_pending_marks_expired(store):
    r = store.create(session_id="ses_1", from_device_id="dev_a")
    r.created_at = r.created_at - HANDOFF_TTL - timedelta(seconds=1)
    pending = store.list_pending()
    assert all(h.id != r.id for h in pending)
    assert store.get(r.id).status is HandoffStatus.EXPIRED


def test_cancel_by_creator(store):
    r = store.create(session_id="ses_1", from_device_id="dev_a")
    cancelled = store.cancel(r.id, "dev_a")
    assert cancelled.status is HandoffStatus.CANCELLED


def test_cancel_by_other_device_is_indistinguishable(store):
    r = store.create(session_id="ses_1", from_device_id="dev_a")
    with pytest.raises(KeyError):
        store.cancel(r.id, "dev_evil")


def test_cancel_claimed_rejected(store):
    r = store.create(session_id="ses_1", from_device_id="dev_a")
    store.claim(r.id, "dev_b")
    with pytest.raises(ValueError, match="not pending"):
        store.cancel(r.id, "dev_a")


# --- snapshot + presence + device linkage ------------------------------------


def test_build_session_snapshot():
    s = SessionStore(store=InMemoryKV()).create("trip")
    s.append_message("user", "book flights")
    snap = build_session_snapshot(s)
    assert snap["session_id"] == s.id
    assert snap["message_count"] == 1
    assert snap["messages"][0]["content"] == "book flights"
    assert snap["compacted"] is False


def test_note_device_linkage():
    ss = SessionStore(store=InMemoryKV())
    s = ss.create("t")
    ss.note_device(s.id, "dev_a")
    ss.note_device(s.id, "dev_b")
    ss.note_device(s.id, "dev_a")  # idempotent
    got = ss.get(s.id)
    assert got.metadata["last_device_id"] == "dev_a"
    assert got.metadata["devices_seen"] == ["dev_a", "dev_b"]


def test_note_device_unknown_session():
    ss = SessionStore(store=InMemoryKV())
    with pytest.raises(KeyError):
        ss.note_device("ses_nope", "dev_a")


def test_presence_heartbeat_idempotent(kv):
    p1 = note_presence(kv, "dev_a", display_name="Phone", platform="ios")
    p2 = note_presence(kv, "dev_a", platform="ios")
    assert p1.device_id == p2.device_id == "dev_a"
    assert p2.display_name == "Phone"  # kept when not resupplied
    assert len(list_presence(kv)) == 1


# --- HTTP routes --------------------------------------------------------------


def test_create_handoff_route(client):
    s = _session()
    dev = _device("phone1")
    r = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={"note": "continue on desktop"},
        headers={"x-shadow-device-id": dev.id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == s.id
    assert body["from_device_id"] == dev.id
    assert body["status"] == "pending"
    assert body["snapshot"]["message_count"] == 2
    assert body["note"] == "continue on desktop"


def test_create_handoff_unknown_session_404(client):
    r = client.post("/agent/sessions/ses_nope/handoff", json={})
    assert r.status_code == 404


def test_create_handoff_closed_session_400(client):
    s = _session()
    m.session_store.close(s.id)
    r = client.post(f"/agent/sessions/{s.id}/handoff", json={})
    assert r.status_code == 400


def test_create_handoff_unknown_target_404(client):
    s = _session()
    r = client.post(
        f"/agent/sessions/{s.id}/handoff", json={"target_device_id": "dev_nope"}
    )
    assert r.status_code == 404


def test_claim_handoff_roundtrip(client):
    s = _session()
    dev_a = _device("phone2")
    dev_b = _device("desk2")
    created = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()
    # one pending approval so the package proves the wiring
    from agent_core import AgentAction

    apr = m.core.approvals.create(
        AgentAction(tool_name="shell", description="run tests", params={}),
        reason="test",
    )
    try:
        r = client.post(
            f"/continuity/handoffs/{created['id']}/claim",
            headers={"x-shadow-device-id": dev_b.id},
        )
        assert r.status_code == 200, r.text
        pkg = r.json()
        assert pkg["handoff"]["status"] == "claimed"
        assert pkg["session"]["id"] == s.id
        assert len(pkg["session"]["messages"]) == 2
        assert any(a["approval_id"] == apr.id for a in pkg["pending_approvals"])
        assert isinstance(pkg["active_plans"], list)
        # claiming device is now the last-active device on the session
        assert m.session_store.get(s.id).metadata["last_device_id"] == dev_b.id
    finally:
        m.core.approvals.decide(apr.id, True)


def test_claim_targeted_handoff_from_other_device_404(client):
    s = _session()
    dev_a = _device("phone3")
    dev_b = _device("desk3")
    dev_evil = _device("evil3")
    created = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={"target_device_id": dev_b.id},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()
    r = client.post(
        f"/continuity/handoffs/{created['id']}/claim",
        headers={"x-shadow-device-id": dev_evil.id},
    )
    assert r.status_code == 404


def test_double_claim_409(client):
    s = _session()
    dev_a = _device("phone4")
    dev_b = _device("desk4")
    hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    assert (
        client.post(
            f"/continuity/handoffs/{hid}/claim",
            headers={"x-shadow-device-id": dev_b.id},
        ).status_code
        == 200
    )
    r = client.post(
        f"/continuity/handoffs/{hid}/claim",
        headers={"x-shadow-device-id": dev_b.id},
    )
    assert r.status_code == 409


def test_cancel_handoff_by_creator(client):
    s = _session()
    dev_a = _device("phone5")
    hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    r = client.post(
        f"/continuity/handoffs/{hid}/cancel",
        headers={"x-shadow-device-id": dev_a.id},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_cancel_handoff_by_other_device_404(client):
    s = _session()
    dev_a = _device("phone6")
    dev_other = _device("other6")
    hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    r = client.post(
        f"/continuity/handoffs/{hid}/cancel",
        headers={"x-shadow-device-id": dev_other.id},
    )
    assert r.status_code == 404


def test_list_handoffs_visibility(client):
    s = _session()
    dev_a = _device("phone7")
    dev_b = _device("desk7")
    dev_evil = _device("evil7")
    open_hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    targeted_hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={"target_device_id": dev_b.id},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    ids_evil = {
        h["id"]
        for h in client.get(
            "/continuity/handoffs", headers={"x-shadow-device-id": dev_evil.id}
        ).json()["items"]
    }
    assert open_hid in ids_evil
    assert targeted_hid not in ids_evil
    ids_b = {
        h["id"]
        for h in client.get(
            "/continuity/handoffs", headers={"x-shadow-device-id": dev_b.id}
        ).json()["items"]
    }
    assert targeted_hid in ids_b


def test_presence_heartbeat_and_overview(client):
    dev = _device("phone8")
    r = client.post(
        "/continuity/presence",
        json={"platform": "ios", "display_name": "Inan's iPhone"},
        headers={"x-shadow-device-id": dev.id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["platform"] == "ios"
    ov = client.get("/continuity/overview").json()
    assert "devices" in ov and "open_sessions" in ov
    match = [d for d in ov["devices"] if d["device_id"] == dev.id]
    assert match and match[0]["last_seen_at"] is not None


def test_presence_without_device_header_400(client):
    r = client.post("/continuity/presence", json={"platform": "ios"})
    assert r.status_code == 400


def test_scope_allowlist_covers_continuity_routes():
    from shadow_node.runtime_scope import SCOPED_ROUTES

    assert SCOPED_ROUTES["/agent/sessions/{session_id}/handoff"] == frozenset({"POST"})
    assert SCOPED_ROUTES["/continuity/handoffs"] == frozenset({"GET"})
    assert SCOPED_ROUTES["/continuity/handoffs/{handoff_id}/claim"] == frozenset(
        {"POST"}
    )
    assert SCOPED_ROUTES["/continuity/handoffs/{handoff_id}/cancel"] == frozenset(
        {"POST"}
    )
    assert SCOPED_ROUTES["/continuity/overview"] == frozenset({"GET"})
    assert SCOPED_ROUTES["/continuity/presence"] == frozenset({"POST"})


# --- mutation-hardening: boundary, persistence, and error-path tests ---------


class _SerializingKV:
    """KV fake that round-trips records through JSON like the real encrypted
    runtime store, so a dropped _persist call becomes observable to a fresh
    store instance."""

    def __init__(self):
        self._data = {}

    def put(self, collection, id, obj):
        self._data.setdefault(collection, {})[id] = obj.model_dump(mode="json")

    def all(self, collection, model):
        return [
            model.model_validate(d) for d in self._data.get(collection, {}).values()
        ]


def test_expiry_boundary_exact_ttl_is_not_expired(monkeypatch):
    fixed = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(cont, "now", lambda: fixed)
    r = HandoffRecord(session_id="ses_1", created_at=fixed - HANDOFF_TTL)
    assert cont._expired(r) is False


def test_create_counts_default_to_zero(store):
    r = store.create(session_id="ses_1", from_device_id="dev_a")
    assert r.pending_approval_count == 0
    assert r.active_plan_count == 0


def test_get_without_kv_raises():
    with pytest.raises(KeyError):
        HandoffStore(kv=None).get("handoff_x")


def test_list_pending_without_kv_is_empty():
    assert HandoffStore(kv=None).list_pending() == []


def test_list_presence_without_kv_is_empty():
    assert list_presence(None) == []


def test_list_presence_empty_store(kv):
    assert list_presence(kv) == []


def test_list_presence_most_recent_first(kv, monkeypatch):
    monkeypatch.setattr(cont, "now", lambda: datetime(2026, 1, 1, tzinfo=UTC))
    note_presence(kv, "dev_old")
    monkeypatch.setattr(cont, "now", lambda: datetime(2026, 1, 2, tzinfo=UTC))
    note_presence(kv, "dev_new")
    assert [p.device_id for p in list_presence(kv)] == ["dev_new", "dev_old"]


def test_claim_persists_across_store_instances():
    kv = _SerializingKV()
    a, b = HandoffStore(kv=kv), HandoffStore(kv=kv)
    r = a.create(session_id="ses_1", from_device_id="dev_a")
    a.claim(r.id, "dev_b")
    got = b.get(r.id)
    assert got.status is HandoffStatus.CLAIMED
    assert got.claimed_by_device_id == "dev_b"


def test_cancel_persists_across_store_instances():
    kv = _SerializingKV()
    a, b = HandoffStore(kv=kv), HandoffStore(kv=kv)
    r = a.create(session_id="ses_1", from_device_id="dev_a")
    a.cancel(r.id, "dev_a")
    assert b.get(r.id).status is HandoffStatus.CANCELLED


def test_list_pending_expiry_mark_persists(monkeypatch):
    kv = _SerializingKV()
    a, b = HandoffStore(kv=kv), HandoffStore(kv=kv)
    r = a.create(session_id="ses_1", from_device_id="dev_a")
    monkeypatch.setattr(
        cont, "now", lambda: r.created_at + HANDOFF_TTL + timedelta(seconds=1)
    )
    assert a.list_pending() == []
    assert b.get(r.id).status is HandoffStatus.EXPIRED


def test_device_display_name_known_unknown_and_missing():
    dev = _device("named9")
    assert m._device_display_name(dev.id) == dev.name
    assert m._device_display_name(None) is None
    assert m._device_display_name("dev_missing") is None


def test_ask_appends_answer_verbatim_and_links_device(client):
    s = _session()
    dev = _device("phone9")
    r = client.post(
        "/agent/ask",
        json={"prompt": "what are you", "session_id": s.id},
        headers={"x-shadow-device-id": dev.id},
    )
    assert r.status_code == 200, r.text
    answer = r.json()["answer"]
    assert r.json()["session_id"] == s.id
    detail = client.get(f"/agent/sessions/{s.id}").json()
    assert detail["messages"][-1]["role"] == "assistant"
    assert detail["messages"][-1]["content"] == answer
    assert m.session_store.get(s.id).metadata["last_device_id"] == dev.id


def test_create_handoff_counts_only_pending_approvals(client):
    s = _session()
    apr = m.core.approvals.create(
        AgentAction(tool_name="shell", description="differential", params={}),
        reason="test",
    )
    try:
        c1 = client.post(f"/agent/sessions/{s.id}/handoff", json={}).json()[
            "pending_approval_count"
        ]
        m.core.approvals.decide(apr.id, True)
        c2 = client.post(f"/agent/sessions/{s.id}/handoff", json={}).json()[
            "pending_approval_count"
        ]
        assert c1 == c2 + 1
    finally:
        try:
            m.core.approvals.decide(apr.id, True)
        except Exception:  # noqa: BLE001, S110 - already decided
            pass


def test_create_handoff_counts_only_active_plans(client):
    s = _session()
    plans = m.shadow_act_runner._plans
    plan = plans.create(
        "test_act",
        [{"title": "step", "deliver_at": time.time() + 3600, "body": "b"}],
    )
    try:
        c1 = client.post(f"/agent/sessions/{s.id}/handoff", json={}).json()[
            "active_plan_count"
        ]
        m.shadow_act_runner.cancel_plan(plan.id)
        c2 = client.post(f"/agent/sessions/{s.id}/handoff", json={}).json()[
            "active_plan_count"
        ]
        assert c1 == c2 + 1
    finally:
        plans._plans.pop(plan.id, None)


def test_handoff_lifecycle_emits_audit_events(client, monkeypatch):
    monkeypatch.setattr(m, "sentinel_audit", MagicMock())
    s = _session()
    dev_a = _device("pa1")
    dev_b = _device("pa2")
    hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    client.post(
        f"/continuity/handoffs/{hid}/claim",
        headers={"x-shadow-device-id": dev_b.id},
    )
    hid2 = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    client.post(
        f"/continuity/handoffs/{hid2}/cancel",
        headers={"x-shadow-device-id": dev_a.id},
    )
    events = [c.args[1] for c in m.sentinel_audit.record.call_args_list]
    assert "continuity.handoff_created" in events
    assert "continuity.handoff_claimed" in events
    assert "continuity.handoff_cancelled" in events


def test_claim_unknown_handoff_404(client):
    r = client.post("/continuity/handoffs/handoff_nope/claim")
    assert r.status_code == 404


def test_claim_handoff_missing_session_404(client, monkeypatch):
    s = _session()
    dev = _device("ps1")
    hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev.id},
    ).json()["id"]

    def _gone(sid):
        raise KeyError(sid)

    monkeypatch.setattr(m.session_store, "get", _gone)
    r = client.post(f"/continuity/handoffs/{hid}/claim")
    assert r.status_code == 404


def test_claim_expired_handoff_410(client, monkeypatch):
    s = _session()
    dev_a = _device("pe1")
    dev_b = _device("pe2")
    hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    record = m.handoff_store.get(hid)
    future = record.created_at + HANDOFF_TTL + timedelta(seconds=1)
    monkeypatch.setattr(cont, "now", lambda: future)
    r = client.post(
        f"/continuity/handoffs/{hid}/claim",
        headers={"x-shadow-device-id": dev_b.id},
    )
    assert r.status_code == 410


def test_claim_records_claimer_presence(client):
    s = _session()
    dev_a = _device("pc1")
    dev_b = _device("pc2")
    hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    assert (
        client.post(
            f"/continuity/handoffs/{hid}/claim",
            headers={"x-shadow-device-id": dev_b.id},
        ).status_code
        == 200
    )
    ov = client.get("/continuity/overview").json()
    match = [d for d in ov["devices"] if d["device_id"] == dev_b.id]
    assert match and match[0]["last_seen_at"] is not None


def test_cancel_claimed_handoff_409(client):
    s = _session()
    dev_a = _device("px1")
    dev_b = _device("px2")
    hid = client.post(
        f"/agent/sessions/{s.id}/handoff",
        json={},
        headers={"x-shadow-device-id": dev_a.id},
    ).json()["id"]
    assert (
        client.post(
            f"/continuity/handoffs/{hid}/claim",
            headers={"x-shadow-device-id": dev_b.id},
        ).status_code
        == 200
    )
    r = client.post(
        f"/continuity/handoffs/{hid}/cancel",
        headers={"x-shadow-device-id": dev_a.id},
    )
    assert r.status_code == 409


def test_heartbeat_falls_back_to_registered_name(client):
    dev = _device("phone10")
    r = client.post(
        "/continuity/presence",
        json={"platform": "ios"},
        headers={"x-shadow-device-id": dev.id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == dev.name
