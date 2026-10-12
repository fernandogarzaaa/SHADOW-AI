"""Glanceable data panels for the Shadow Node (Hark backlog item 2).

One JSON shape for every panel the client renders as a glanceable card:
a header row (title), one headline insight sentence, stat tiles (label +
large number), then compact rows with timestamps. The headline is the
value; the tiles and rows are the receipts.

The first panels are node-state only, so no external data is needed:
- approvals: pending approval decisions
- goals: goals progress from the goals briefing
- memory: local memory store inventory

Headlines are deterministic sentences derived from real counts. Empty
states say so honestly; nothing is faked. Panels are cheap to compute
(in-memory scans of existing stores) and carry a generated_at timestamp
so the client can poll or cache them.
"""

from __future__ import annotations

import time as _time
from datetime import UTC, datetime

from agent_core.models import ApprovalRequest, RiskClass
from memory_engine.models import MemoryItem
from pydantic import BaseModel, Field

from .goals import GoalsBriefing

MAX_ROWS = 8
MAX_TITLE_LEN = 80
WEEK_SECONDS = 7 * 86400


class PanelTile(BaseModel):
    label: str
    value: str  # rendered large; kept a string so "3" and "1.2k" both work


class PanelRow(BaseModel):
    title: str
    detail: str = ""
    timestamp: float | None = None  # epoch seconds


class Panel(BaseModel):
    id: str  # "approvals" | "goals" | "memory"
    title: str
    headline: str
    tiles: list[PanelTile] = Field(default_factory=list)
    rows: list[PanelRow] = Field(default_factory=list)
    generated_at: float
    empty: bool = False


def _epoch(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.timestamp()
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _truncate(text: str, limit: int = MAX_TITLE_LEN) -> str:
    text = " ".join((text or "").split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


# --- approvals -------------------------------------------------------------


def approvals_panel(pending: list[ApprovalRequest], now: float | None = None) -> Panel:
    """Panel over the currently pending approval requests."""
    now = now if now is not None else _time.time()
    ordered = sorted(pending, key=lambda r: _epoch(r.created_at) or 0.0)
    n = len(ordered)
    high = sum(1 for r in ordered if r.risk_label == RiskClass.HIGH)
    double = sum(1 for r in ordered if r.requires_double_confirmation)

    if n == 0:
        headline = "No pending approvals. Nothing needs your decision."
    elif n == 1:
        headline = "1 approval waiting for your decision."
    else:
        headline = f"{n} approvals waiting for your decision."

    rows = [
        PanelRow(
            title=_truncate(r.card["title"]),
            detail=f"{r.risk_label.value} risk"
            + (
                " · needs double confirmation" if r.requires_double_confirmation else ""
            ),
            timestamp=_epoch(r.created_at),
        )
        for r in ordered[:MAX_ROWS]
    ]
    return Panel(
        id="approvals",
        title="Pending approvals",
        headline=headline,
        tiles=[
            PanelTile(label="Pending", value=str(n)),
            PanelTile(label="High risk", value=str(high)),
            PanelTile(label="Double confirm", value=str(double)),
        ],
        rows=rows,
        generated_at=now,
        empty=n == 0,
    )


# --- goals -----------------------------------------------------------------


def _goal_row_detail(summary, kind: str) -> str:
    if kind == "overdue":
        return f"overdue · target {summary.target_date}"
    if kind == "due_soon":
        return f"due soon · target {summary.target_date}"
    return "no recent progress"


def goals_panel(briefing: GoalsBriefing, now: float | None = None) -> Panel:
    """Panel over goals progress, derived from the goals briefing."""
    now = now if now is not None else _time.time()
    active = briefing.active_count
    completed = briefing.completed_count
    overdue = briefing.overdue
    due_soon = briefing.due_soon
    stale = briefing.stale

    if active == 0 and completed == 0:
        headline = "No goals yet. Create one to start tracking an outcome."
        empty = True
    else:
        parts = [f"{active} active"]
        if overdue:
            parts.append(f"{len(overdue)} overdue")
        elif due_soon:
            parts.append(f"{len(due_soon)} due soon")
        elif stale:
            parts.append(f"{len(stale)} stale")
        headline = "Goals: " + ", ".join(parts) + "."
        empty = False

    rows: list[PanelRow] = []
    for kind, summaries in (
        ("overdue", overdue),
        ("due_soon", due_soon),
        ("stale", stale),
    ):
        for s in summaries[:MAX_ROWS]:
            rows.append(
                PanelRow(
                    title=_truncate(s.title),
                    detail=_goal_row_detail(s, kind),
                    timestamp=s.last_progress_at or s.updated_at,
                )
            )
            if len(rows) >= MAX_ROWS:
                break
        if len(rows) >= MAX_ROWS:
            break

    return Panel(
        id="goals",
        title="Goals",
        headline=headline,
        tiles=[
            PanelTile(label="Active", value=str(active)),
            PanelTile(label="Completed", value=str(completed)),
            PanelTile(label="Overdue", value=str(len(overdue))),
        ],
        rows=rows,
        generated_at=now,
        empty=empty,
    )


# --- memory ----------------------------------------------------------------


def memory_panel(items: list[MemoryItem], now: float | None = None) -> Panel:
    """Panel over the local memory store inventory.

    Takes the non-sensitive export; sensitive items are never surfaced in
    panel rows.
    """
    now = now if now is not None else _time.time()
    total = len(items)
    week_ago = now - WEEK_SECONDS
    added_week = sum(1 for i in items if (_epoch(i.created_at) or 0.0) >= week_ago)

    if total == 0:
        headline = "Memory is empty. Ingest something to remember it."
        empty = True
    else:
        headline = f"{total} memory items stored"
        headline += f", {added_week} added this week." if added_week else "."
        empty = False

    recent = sorted(items, key=lambda i: _epoch(i.created_at) or 0.0, reverse=True)
    rows = [
        PanelRow(
            title=_truncate(i.text),
            detail=_truncate(i.source.title or i.source.kind, 60),
            timestamp=_epoch(i.created_at),
        )
        for i in recent[:MAX_ROWS]
    ]
    return Panel(
        id="memory",
        title="Memory",
        headline=headline,
        tiles=[
            PanelTile(label="Items", value=str(total)),
            PanelTile(label="Added this week", value=str(added_week)),
        ],
        rows=rows,
        generated_at=now,
        empty=empty,
    )


# --- assembly --------------------------------------------------------------


def build_panels(
    pending_approvals: list[ApprovalRequest],
    briefing: GoalsBriefing,
    memory_items: list[MemoryItem],
    now: float | None = None,
) -> list[Panel]:
    """Build all glanceable panels from live node state, in panel order."""
    now = now if now is not None else _time.time()
    return [
        approvals_panel(pending_approvals, now),
        goals_panel(briefing, now),
        memory_panel(memory_items, now),
    ]
