"""Custom panels (Hark backlog item 3): NL parsing, registry, rendering, routes.

Covers the adversarial cases: ambiguous requests are clarified (never
guessed), unknown data sources are rejected, fabricated panel ids 404, and
deletion without explicit confirmation is refused.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from shadow_node import main
from shadow_node.custom_panels import (
    CustomPanelDef,
    CustomPanelFilter,
    CustomPanelRegistry,
    CustomPanelSort,
    CustomPanelSource,
    PanelClarification,
    PanelInputs,
    PanelProposal,
    parse_panel_request,
    render_panel,
    validate_definition,
)
from shadow_node.main import app


@pytest.fixture()
def client():
    main.AUTH_REQUIRED = False
    return TestClient(app)


# --- NL parser --------------------------------------------------------------


def test_parse_top_overdue_goals():
    r = parse_panel_request("make a panel showing my top 5 overdue goals")
    assert isinstance(r, PanelProposal)
    assert r.source == CustomPanelSource.GOALS
    assert r.filter == CustomPanelFilter.OVERDUE
    assert r.limit == 5
    assert r.sort == CustomPanelSort.NEWEST


def test_parse_pending_approvals_count():
    r = parse_panel_request("show me my 3 pending approvals")
    assert isinstance(r, PanelProposal)
    assert r.source == CustomPanelSource.APPROVALS
    assert r.filter == CustomPanelFilter.PENDING
    assert r.limit == 3


def test_parse_oldest_reminders():
    r = parse_panel_request("panel of my oldest reminders")
    assert isinstance(r, PanelProposal)
    assert r.source == CustomPanelSource.REMINDERS
    assert r.sort == CustomPanelSort.OLDEST
    assert r.filter == CustomPanelFilter.ALL


def test_parse_memory_and_feed_sources():
    r = parse_panel_request("make a memory panel")
    assert isinstance(r, PanelProposal)
    assert r.source == CustomPanelSource.MEMORY
    r = parse_panel_request("show feed panel")
    assert isinstance(r, PanelProposal)
    assert r.source == CustomPanelSource.FEED


def test_parse_named_panel():
    r = parse_panel_request('create a panel called "Weekend review" showing my goals')
    assert isinstance(r, PanelProposal)
    assert r.name == "Weekend review"


def test_parse_default_name():
    r = parse_panel_request("make a panel of my goals")
    assert isinstance(r, PanelProposal)
    assert r.name == "My goals panel"


def test_parse_limit_clamped():
    r = parse_panel_request("show top 99 goals")
    assert isinstance(r, PanelProposal)
    assert r.limit == 20


def test_parse_ambiguous_asks_for_source():
    r = parse_panel_request("make a panel")
    assert isinstance(r, PanelClarification)
    assert "goals" in r.question
    assert "approvals" in r.options


def test_parse_unsupported_source_rejected_by_name():
    r = parse_panel_request("make a panel of my calendar")
    assert isinstance(r, PanelClarification)
    assert "calendar" in r.question
    assert "cannot build" in r.question


def test_parse_invalid_filter_for_source_clarifies():
    r = parse_panel_request("show me overdue approvals")
    assert isinstance(r, PanelClarification)
    assert "overdue" in r.question
    assert "approvals" in r.question


def test_parse_high_risk_approvals():
    r = parse_panel_request("panel of high risk approvals")
    assert isinstance(r, PanelProposal)
    assert r.source == CustomPanelSource.APPROVALS
    assert r.filter == CustomPanelFilter.HIGH_RISK


def test_parse_empty_text_clarifies():
    r = parse_panel_request("")
    assert isinstance(r, PanelClarification)


# --- definition validation --------------------------------------------------


def _def(**kw):
    base = {"name": "t", "source": CustomPanelSource.GOALS}
    base.update(kw)
    return CustomPanelDef(**base)


def test_validate_ok():
    validate_definition(_def(filter=CustomPanelFilter.OVERDUE))


def test_validate_filter_source_mismatch():
    with pytest.raises(ValueError, match="does not apply"):
        validate_definition(
            _def(filter=CustomPanelFilter.OVERDUE, source=CustomPanelSource.APPROVALS)
        )


def test_validate_limit_bounds():
    with pytest.raises(ValidationError):
        _def(limit=0)
    with pytest.raises(ValidationError):
        _def(limit=21)


def test_validate_empty_name():
    with pytest.raises(ValidationError):
        _def(name="   ")


def test_validate_fields_must_include_title():
    with pytest.raises(ValidationError, match="title"):
        _def(fields=["detail"])


def test_validate_unknown_field_rejected():
    with pytest.raises(ValidationError, match="unknown row fields"):
        _def(fields=["title", "bogus"])


# --- registry ---------------------------------------------------------------


def test_registry_crud_round_trip():
    reg = CustomPanelRegistry()
    created = reg.create(_def(name="my goals"))
    assert reg.get(created.id).name == "my goals"
    assert [p.id for p in reg.list()] == [created.id]
    updated = reg.update(created.id, name="renamed", limit=7)
    assert updated.name == "renamed" and updated.limit == 7
    reg.delete(created.id)
    assert reg.list() == []
    with pytest.raises(KeyError):
        reg.get(created.id)


def test_registry_unknown_ids_fail_loud():
    reg = CustomPanelRegistry()
    with pytest.raises(KeyError):
        reg.get("cpanel_nope")
    with pytest.raises(KeyError):
        reg.update("cpanel_nope", name="x")
    with pytest.raises(KeyError):
        reg.delete("cpanel_nope")


def test_registry_rejects_invalid_on_create_and_update():
    reg = CustomPanelRegistry()
    with pytest.raises(ValueError, match="does not apply"):
        reg.create(_def(filter=CustomPanelFilter.HIGH_RISK))
    created = reg.create(_def())
    with pytest.raises(ValueError, match="does not apply"):
        reg.update(created.id, filter=CustomPanelFilter.HIGH_RISK)
    with pytest.raises(ValidationError):
        reg.update(created.id, limit=99)


def test_registry_skips_corrupt_rows():
    from agent_core.ambient import InMemoryKV

    kv = InMemoryKV()
    kv.put("custom_panels", "cpanel_bad", {"not": "a panel"})
    good = _def(name="good")
    kv.put("custom_panels", good.id, good)
    reg = CustomPanelRegistry(kv)
    assert [p.id for p in reg.list()] == [good.id]


def test_registry_persists_through_kv():
    from agent_core.ambient import InMemoryKV

    kv = InMemoryKV()
    reg = CustomPanelRegistry(kv)
    created = reg.create(_def(name="persisted"))
    reg2 = CustomPanelRegistry(kv)
    assert reg2.get(created.id).name == "persisted"
    reg.delete(created.id)
    reg3 = CustomPanelRegistry(kv)
    assert reg3.list() == []


# --- rendering --------------------------------------------------------------


def _approval(ns_id, title, risk="low", double=False, created=1000.0):
    return SimpleNamespace(
        id=ns_id,
        card={"title": title},
        risk_label=SimpleNamespace(value=risk),
        requires_double_confirmation=double,
        created_at=created,
    )


def _goal(title, status="active", target=None, updated=2000.0):
    return SimpleNamespace(
        title=title,
        status=status,
        target_date=target,
        latest_percent=None,
        updated_at=updated,
    )


def test_render_approvals_panel_shape():
    defn = _def(
        name="Approvals",
        source=CustomPanelSource.APPROVALS,
        filter=CustomPanelFilter.PENDING,
        limit=2,
    )
    inputs = PanelInputs(
        approvals=[
            _approval("a1", "Deploy to prod", risk="high", created=100.0),
            _approval("a2", "Send report", created=200.0),
            _approval("a3", "Old one", created=50.0),
        ]
    )
    panel = render_panel(defn, inputs, now=9999.0)
    assert panel.id == defn.id
    assert panel.title == "Approvals"
    assert panel.headline == "2 pending approvals."
    assert panel.tiles[0].value == "2" and panel.tiles[1].value == "3"
    assert len(panel.rows) == 2  # limit applied
    assert panel.rows[0].title == "Send report"  # newest first
    assert "high risk" in panel.rows[1].detail
    assert panel.generated_at == 9999.0
    assert panel.empty is False


def test_render_oldest_sort():
    defn = _def(source=CustomPanelSource.APPROVALS, sort=CustomPanelSort.OLDEST)
    inputs = PanelInputs(
        approvals=[
            _approval("a1", "new", created=200.0),
            _approval("a2", "old", created=50.0),
        ]
    )
    panel = render_panel(defn, inputs)
    assert panel.rows[0].title == "old"


def test_render_high_risk_filter():
    defn = _def(source=CustomPanelSource.APPROVALS, filter=CustomPanelFilter.HIGH_RISK)
    inputs = PanelInputs(
        approvals=[
            _approval("a1", "risky", risk="high"),
            _approval("a2", "safe", risk="low"),
        ]
    )
    panel = render_panel(defn, inputs)
    assert len(panel.rows) == 1
    assert panel.rows[0].title == "risky"


def test_render_empty_state_is_honest():
    defn = _def(source=CustomPanelSource.GOALS, filter=CustomPanelFilter.OVERDUE)
    panel = render_panel(defn, PanelInputs())
    assert panel.empty is True
    assert panel.headline == "No overdue goals to show."
    assert panel.rows == []


def test_render_goals_overdue_pool():
    defn = _def(source=CustomPanelSource.GOALS, filter=CustomPanelFilter.OVERDUE)
    inputs = PanelInputs(
        goal_active=[_goal("active one"), _goal("late one")],
        goal_overdue=[_goal("late one")],
    )
    panel = render_panel(defn, inputs)
    assert len(panel.rows) == 1
    assert panel.rows[0].title == "late one"
    assert panel.tiles[1].value == "2"  # source total counts active goals


def test_render_fields_subset():
    defn = _def(source=CustomPanelSource.APPROVALS, fields=["title"])
    inputs = PanelInputs(approvals=[_approval("a1", "t", created=100.0)])
    panel = render_panel(defn, inputs)
    assert panel.rows[0].detail == ""
    assert panel.rows[0].timestamp is None


def test_render_memory_and_feed_rows():
    mem = SimpleNamespace(
        text="some remembered fact about the user",
        source=SimpleNamespace(title="notes", kind="file"),
        created_at=3000.0,
    )
    feed = SimpleNamespace(title="Morning brief", kind="briefing", created_at=4000.0)
    defn = _def(source=CustomPanelSource.MEMORY)
    panel = render_panel(defn, PanelInputs(memory_items=[mem]))
    assert panel.rows[0].title == "some remembered fact about the user"
    assert "notes" in panel.rows[0].detail
    defn2 = _def(source=CustomPanelSource.FEED)
    panel2 = render_panel(defn2, PanelInputs(feed_units=[feed]))
    assert panel2.rows[0].title == "Morning brief"


def test_render_reminders_pending_filter():
    r1 = SimpleNamespace(title="due soon", status="pending", due_at=5000.0)
    r2 = SimpleNamespace(title="done one", status="done", due_at=1000.0)
    defn = _def(source=CustomPanelSource.REMINDERS, filter=CustomPanelFilter.PENDING)
    panel = render_panel(defn, PanelInputs(reminders=[r1, r2]))
    assert len(panel.rows) == 1
    assert panel.rows[0].title == "due soon"


# --- routes -----------------------------------------------------------------


def _mk_panel(client, text="make a panel of my top 3 goals"):
    r = client.post("/custom-panels/parse", json={"text": text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "proposal", body
    p = body["proposal"]
    r = client.post(
        "/custom-panels",
        json={
            "name": p["name"],
            "source": p["source"],
            "filter": p["filter"],
            "sort": p["sort"],
            "limit": p["limit"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _rm_panel(client, panel_id):
    r = client.request("DELETE", f"/custom-panels/{panel_id}", json={"confirm": True})
    assert r.status_code == 200, r.text


def test_route_parse_proposal(client):
    r = client.post("/custom-panels/parse", json={"text": "top 5 overdue goals panel"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "proposal"
    assert body["proposal"]["source"] == "goals"
    assert body["proposal"]["filter"] == "overdue"
    assert body["proposal"]["limit"] == 5


def test_route_parse_ambiguous(client):
    r = client.post("/custom-panels/parse", json={"text": "make a panel"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "needs_clarification"
    assert body["options"]


def test_route_crud_and_render(client):
    panel = _mk_panel(client)
    pid = panel["id"]
    try:
        r = client.get(f"/custom-panels/{pid}")
        assert r.status_code == 200
        assert r.json()["name"] == panel["name"]

        r = client.get("/custom-panels")
        assert r.status_code == 200
        assert pid in [p["id"] for p in r.json()]

        r = client.patch(f"/custom-panels/{pid}", json={"limit": 2, "name": "n2"})
        assert r.status_code == 200
        assert r.json()["limit"] == 2

        r = client.get(f"/custom-panels/{pid}/render")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == pid
        assert "headline" in body and "tiles" in body and "rows" in body
        assert "generated_at" in body
    finally:
        _rm_panel(client, pid)


def test_route_create_invalid_filter_rejected(client):
    r = client.post(
        "/custom-panels",
        json={"name": "bad", "source": "approvals", "filter": "overdue"},
    )
    assert r.status_code == 422


def test_route_fabricated_ids_404(client):
    assert client.get("/custom-panels/cpanel_nope123").status_code == 404
    assert (
        client.patch("/custom-panels/cpanel_nope123", json={"limit": 2}).status_code
        == 404
    )
    assert client.get("/custom-panels/cpanel_nope123/render").status_code == 404
    r = client.request(
        "DELETE", "/custom-panels/cpanel_nope123", json={"confirm": True}
    )
    assert r.status_code == 404


def test_route_delete_requires_explicit_confirm(client):
    panel = _mk_panel(client)
    pid = panel["id"]
    try:
        r = client.request("DELETE", f"/custom-panels/{pid}", json={"confirm": False})
        assert r.status_code == 409
        # panel still there: nothing was deleted silently
        assert client.get(f"/custom-panels/{pid}").status_code == 200
    finally:
        _rm_panel(client, pid)


def test_route_update_invalid_rejected(client):
    panel = _mk_panel(client)
    pid = panel["id"]
    try:
        r = client.patch(f"/custom-panels/{pid}", json={"limit": 99})
        assert r.status_code == 422
        r = client.patch(f"/custom-panels/{pid}", json={"fields": ["bogus"]})
        assert r.status_code == 422
    finally:
        _rm_panel(client, pid)
