"""Glanceable data panels (Hark item 2): panel JSON rendered from node state."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from agent_core.models import (
    AgentAction,
    ApprovalRequest,
    ApprovalStatus,
    RiskClass,
)
from fastapi.testclient import TestClient
from memory_engine.models import MemoryItem, MemorySource
from shadow_node import main
from shadow_node.goals import GoalCreate, GoalStore, GoalUpdate, ProgressCreate
from shadow_node.main import app
from shadow_node.panels import (
    MAX_ROWS,
    approvals_panel,
    build_panels,
    goals_panel,
    memory_panel,
)


@pytest.fixture()
def client():
    main.AUTH_REQUIRED = False
    return TestClient(app)


def _approval(description="Run the deploy script", **kw):
    action = AgentAction(tool_name="shell", description=description)
    return ApprovalRequest(action=action, reason="test", action_preview="preview", **kw)


def _mem(text, days_ago=0, title="note"):
    src = MemorySource(kind="note", title=title)
    return MemoryItem(
        text=text,
        source=src,
        created_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


# --- approvals panel -------------------------------------------------------


def test_approvals_panel_empty():
    p = approvals_panel([], now=1000.0)
    assert p.id == "approvals"
    assert p.empty is True
    assert "No pending approvals" in p.headline
    assert p.rows == []
    assert p.tiles[0].label == "Pending" and p.tiles[0].value == "0"
    assert p.generated_at == 1000.0


def test_approvals_panel_singular():
    p = approvals_panel([_approval()])
    assert p.empty is False
    assert p.headline == "1 approval waiting for your decision."


def test_approvals_panel_counts_and_tiles():
    reqs = [
        _approval("low risk thing"),
        _approval("risky thing", risk_label=RiskClass.HIGH),
        _approval("double thing", requires_double_confirmation=True),
    ]
    p = approvals_panel(reqs)
    assert p.headline == "3 approvals waiting for your decision."
    by_label = {t.label: t.value for t in p.tiles}
    assert by_label == {"Pending": "3", "High risk": "1", "Double confirm": "1"}
    assert len(p.rows) == 3
    assert "high risk" in p.rows[1].detail
    assert "double confirmation" in p.rows[2].detail
    assert all(r.timestamp is not None for r in p.rows)


def test_approvals_panel_rows_capped_and_oldest_first():
    base = datetime.now(UTC)
    reqs = [
        _approval(f"task {i}", created_at=base - timedelta(minutes=i))
        for i in range(MAX_ROWS + 3)
    ]
    p = approvals_panel(reqs)
    assert len(p.rows) == MAX_ROWS
    # oldest first: task MAX_ROWS+2 is the oldest overall
    assert "task 10" in p.rows[0].title
    assert p.tiles[0].value == str(MAX_ROWS + 3)


def test_approvals_panel_row_title_truncated():
    p = approvals_panel([_approval("x" * 200)])
    assert len(p.rows[0].title) <= 80
    assert p.rows[0].title.endswith("...")


# --- goals panel -----------------------------------------------------------


def test_goals_panel_empty():
    p = goals_panel(GoalStore().briefing())
    assert p.id == "goals"
    assert p.empty is True
    assert "No goals yet" in p.headline
    assert p.rows == []


def test_goals_panel_overdue_headline_and_rows():
    store = GoalStore()
    past = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d")
    g = store.create(GoalCreate(title="Ship the thing", target_date=past))
    p = goals_panel(store.briefing())
    assert p.empty is False
    assert "1 overdue" in p.headline
    assert p.tiles[0].value == "1"  # Active
    assert p.tiles[2].value == "1"  # Overdue
    assert len(p.rows) == 1
    assert p.rows[0].title == "Ship the thing"
    assert "overdue" in p.rows[0].detail
    assert g.id  # keep reference used


def test_goals_panel_due_soon_and_stale():
    store = GoalStore()
    soon = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%d")
    store.create(GoalCreate(title="Due soon goal", target_date=soon))
    stale_goal = store.create(GoalCreate(title="Stale goal"))
    # backdate so the briefing treats it as stale (no progress in 7+ days)
    stale_goal.created_at = time.time() - 8 * 86400
    stale_goal.updated_at = stale_goal.created_at
    p = goals_panel(store.briefing())
    assert "due soon" in p.headline
    assert len(p.rows) == 2
    assert any("stale" in r.detail or "no recent progress" in r.detail for r in p.rows)


def test_goals_panel_completed_tile():
    store = GoalStore()
    g = store.create(GoalCreate(title="Done goal"))
    store.add_progress(g.id, ProgressCreate(note="finished", percent=100))
    store.update(g.id, GoalUpdate(status="completed"))
    p = goals_panel(store.briefing())
    assert p.tiles[1].label == "Completed" and p.tiles[1].value == "1"


# --- memory panel ----------------------------------------------------------


def test_memory_panel_empty():
    p = memory_panel([])
    assert p.id == "memory"
    assert p.empty is True
    assert "Memory is empty" in p.headline
    assert p.rows == []


def test_memory_panel_counts_and_week_window():
    items = [
        _mem("recent note one", days_ago=1),
        _mem("recent note two", days_ago=2),
        _mem("old note", days_ago=30),
    ]
    p = memory_panel(items)
    assert p.empty is False
    assert "3 memory items stored" in p.headline
    assert "2 added this week" in p.headline
    by_label = {t.label: t.value for t in p.tiles}
    assert by_label == {"Items": "3", "Added this week": "2"}


def test_memory_panel_rows_newest_first_and_capped():
    items = [_mem(f"note number {i}", days_ago=i) for i in range(MAX_ROWS + 4)]
    p = memory_panel(items)
    assert len(p.rows) == MAX_ROWS
    assert "note number 0" in p.rows[0].title
    assert all(r.timestamp is not None for r in p.rows)


def test_memory_panel_row_uses_source_title_as_detail():
    p = memory_panel([_mem("some text here", title="My Source")])
    assert p.rows[0].detail == "My Source"


def test_memory_panel_long_text_truncated_to_one_line():
    p = memory_panel([_mem("word " * 100)])
    assert len(p.rows[0].title) <= 80
    assert "\n" not in p.rows[0].title


# --- assembly --------------------------------------------------------------


def test_build_panels_returns_three_in_order():
    panels = build_panels([], GoalStore().briefing(), [], now=1234.0)
    assert [p.id for p in panels] == ["approvals", "goals", "memory"]
    assert [p.title for p in panels] == [
        "Pending approvals",
        "Goals",
        "Memory",
    ]
    assert all(p.generated_at == 1234.0 for p in panels)


# --- route -----------------------------------------------------------------


def test_panels_route_shape(client):
    r = client.get("/panels")
    assert r.status_code == 200, r.text
    panels = r.json()
    assert isinstance(panels, list) and len(panels) == 3
    for p in panels:
        assert set(p) >= {
            "id",
            "title",
            "headline",
            "tiles",
            "rows",
            "generated_at",
            "empty",
        }
        for t in p["tiles"]:
            assert {"label", "value"} <= set(t)
        for row in p["rows"]:
            assert {"title", "detail", "timestamp"} <= set(row)


def test_panels_route_reflects_created_goal(client):
    title = f"panel goal {time.time()}"
    r = client.post("/goals", json={"title": title})
    assert r.status_code == 201, r.text
    panels = {p["id"]: p for p in client.get("/panels").json()}
    assert panels["goals"]["empty"] is False
    assert int(panels["goals"]["tiles"][0]["value"]) >= 1


def test_panels_route_reflects_pending_approval(client):
    r = client.post(
        "/approvals",
        json={
            "action": {"tool_name": "shell", "description": "panel test action"},
            "reason": "panel test",
        },
    )
    assert r.status_code == 200, r.text
    approval_id = r.json()["id"]
    panels = {p["id"]: p for p in client.get("/panels").json()}
    ap = panels["approvals"]
    assert ap["empty"] is False
    assert "waiting for your decision" in ap["headline"]
    assert any("panel test action" in row["title"] for row in ap["rows"])
    # clean up so other tests see a stable approvals panel
    main.core.approvals.requests[approval_id].status = ApprovalStatus.DENIED
