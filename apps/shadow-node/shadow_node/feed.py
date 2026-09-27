"""Editorial feed for the Shadow Node (Cookie/Muse.AI parity, local-first).

The feed is the node's personal newspaper: deterministic editorial units
rendered from live node state (approvals, executions, claims, goals, memory).
Units are generated on demand via POST /feed/generate and on the ambient
scheduler's interval via the built-in `feed_digest` ambient task.

Generation is fully offline: prose is rendered from structured data with
templates, never by a cloud model. Units persist encrypted in the runtime
store's "feed" collection when configured, in-memory otherwise.
"""
from __future__ import annotations

import time
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

MAX_TITLE_LEN = 140
MAX_BODY_LEN = 8000
FEED_CAP = 200  # keep the newest N units
MIN_REGEN_SECONDS = 20 * 3600  # one unit per kind per ~20h

FEED_KINDS = ("morning_brief", "goals_briefing", "memory_digest", "reminder")
# Kinds the feed_digest ambient task generates on its interval. "reminder"
# units are event-driven (fired reminders), never scheduled.
DIGEST_KINDS = ("morning_brief", "goals_briefing", "memory_digest")


class FeedUnit(BaseModel):
    id: str = Field(default_factory=lambda: f"feed_{uuid4().hex}")
    kind: str
    title: str
    body: str
    created_at: float = Field(default_factory=time.time)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in FEED_KINDS:
            raise ValueError(f"kind must be one of {FEED_KINDS}")
        return v


class FeedGenerateRequest(BaseModel):
    kinds: list[str] = Field(default_factory=list)  # empty = all kinds
    force: bool = False


def _lines(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- nothing to report"


def render_morning_brief(data: dict) -> tuple[str, str]:
    pending = data.get("pending_approvals", [])
    verdicts = data.get("verdicts_24h", {})
    recent = data.get("recent_executions_24h", 0)
    claims = data.get("unconfirmed_claims", [])
    devices = data.get("paired_devices", 0)

    parts = []
    if pending:
        parts.append(
            "Approvals waiting on you:\n"
            + _lines(f"[{p.get('risk', '?')}] {p.get('preview', p.get('id', '?'))}" for p in pending[:5])
        )
    if recent:
        parts.append(
            f"Agent activity (last 24h): {recent} executions — "
            + (", ".join(f"{k}: {v}" for k, v in verdicts.items()) if verdicts else "no verdicts yet")
        )
    if claims:
        parts.append(
            "Open claims to confirm or refute:\n"
            + _lines(c.get("statement", c.get("id", "?")) for c in claims[:5])
        )
    if devices:
        parts.append(f"Paired devices: {devices}")
    if not parts:
        parts.append("Quiet shift. No pending approvals, no recent executions, no open claims.")
    return "Morning brief", "\n\n".join(parts)


def render_goals_briefing(b) -> tuple[str, str]:
    parts = [f"{b.active_count} active goals, {b.completed_count} completed all-time."]
    if b.overdue:
        parts.append("Overdue:\n" + _lines(f"{g.title} (due {g.target_date})" for g in b.overdue[:5]))
    if b.due_soon:
        parts.append("Due within 7 days:\n" + _lines(f"{g.title} (due {g.target_date})" for g in b.due_soon[:5]))
    if b.stale:
        parts.append(
            "Stale — no progress in 7+ days:\n" + _lines(g.title for g in b.stale[:5])
        )
    if b.completed_this_week:
        parts.append(
            "Completed this week:\n" + _lines(g.title for g in b.completed_this_week[:5])
        )
    if b.recent_entries:
        parts.append(
            "Recent progress:\n"
            + _lines(
                f"{e.goal_title}: {e.note[:80]}" + (f" ({e.percent}%)" if e.percent is not None else "")
                for e in b.recent_entries[:5]
            )
        )
    return "Goals briefing", "\n\n".join(parts)


def render_memory_digest(data: dict) -> tuple[str, str]:
    total = data.get("total_items", 0)
    by_category = data.get("by_category", {})
    expiring = data.get("expiring_within_7_days", 0)
    parts = [f"{total} memory items stored locally."]
    if by_category:
        parts.append(
            "By category: " + ", ".join(f"{k}: {v}" for k, v in by_category.items())
        )
    if expiring:
        parts.append(f"{expiring} items expiring within 7 days.")
    return "Memory digest", "\n\n".join(parts)


class FeedStore:
    """Append-only feed journal with encrypted runtime-store persistence."""

    def __init__(self, runtime_store=None):
        self._store = runtime_store
        self.units: list[FeedUnit] = []
        self._last_generated: dict[str, float] = {}
        if runtime_store is not None:
            self.units = sorted(
                runtime_store.all("feed", FeedUnit),
                key=lambda u: u.created_at,
                reverse=True,
            )
            # One-time cleanup for rows persisted before retention deleted
            # them: drop anything beyond the cap from the store as well.
            for old in self.units[FEED_CAP:]:
                runtime_store.delete("feed", old.id)
            self.units = self.units[:FEED_CAP]
            for marker in runtime_store.all("feed_markers", _GenMarker):
                self._last_generated[marker.kind] = marker.at

    def _persist(self, unit: FeedUnit) -> None:
        if self._store is not None:
            self._store.put("feed", unit.id, unit)

    def _persist_marker(self, kind: str, at: float) -> None:
        if self._store is not None:
            self._store.put("feed_markers", f"marker:{kind}", _GenMarker(kind=kind, at=at))

    def add(self, unit: FeedUnit) -> FeedUnit:
        self.units.insert(0, unit)
        self._persist(unit)
        if len(self.units) > FEED_CAP:
            # Retention trims persisted rows too, not just the in-memory
            # list: otherwise the encrypted store grows without bound and
            # restarts resurrect units the cap was supposed to drop.
            evicted = self.units[FEED_CAP:]
            self.units = self.units[:FEED_CAP]
            if self._store is not None:
                for old in evicted:
                    self._store.delete("feed", old.id)
        return unit

    def list(self, limit: int = 20, offset: int = 0) -> tuple[list[FeedUnit], int]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        return self.units[offset:offset + limit], len(self.units)

    def due_kinds(self, kinds: list[str], now: float, force: bool = False) -> list[str]:
        if force:
            return list(kinds)
        return [
            k for k in kinds
            if now - self._last_generated.get(k, 0) >= MIN_REGEN_SECONDS
        ]

    def mark_generated(self, kind: str, at: float) -> None:
        self._last_generated[kind] = at
        self._persist_marker(kind, at)


class _GenMarker(BaseModel):
    kind: str
    at: float


def generate_units(
    feed_store: FeedStore,
    kinds: list[str],
    renderers: dict,
    now: float | None = None,
    force: bool = False,
) -> list[FeedUnit]:
    """Render and store one feed unit per due kind.

    `renderers` maps kind -> zero-arg callable returning (title, body).
    Unknown kinds are ignored. Returns the new units, newest first.
    """
    now = now if now is not None else time.time()
    wanted = [k for k in kinds if k in FEED_KINDS and k in renderers]
    due = feed_store.due_kinds(wanted, now, force=force)
    made: list[FeedUnit] = []
    for kind in due:
        try:
            title, body = renderers[kind]()
        except Exception:
            continue
        unit = FeedUnit(kind=kind, title=title[:MAX_TITLE_LEN], body=body[:MAX_BODY_LEN])
        feed_store.add(unit)
        feed_store.mark_generated(kind, now)
        made.append(unit)
    return made
