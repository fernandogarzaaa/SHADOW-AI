"""User-created glanceable data panels (Hark backlog item 3).

The user describes a panel in natural language ("make a panel showing my top
5 overdue goals"). A deterministic parser turns the request into a panel
definition; the definition persists in the node's KV store so panels survive
restarts. Definitions are inspectable (list/get) and editable (update);
deleting one requires explicit confirmation.

Custom panels render through the same panel JSON shape as the built-in
glanceable panels (title, headline insight sentence, stat tiles, compact
rows, generated_at freshness), so the client needs no new rendering code.
Every row comes from node-local stores; nothing is faked and nothing leaves
the device.
"""

from __future__ import annotations

import re
import time as _time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

# --- panel JSON shape (same shape as the built-in glanceable panels) -------


class PanelTile(BaseModel):
    label: str
    value: str  # rendered large; kept a string so "3" and "1.2k" both work


class PanelRow(BaseModel):
    title: str
    detail: str = ""
    timestamp: float | None = None  # epoch seconds


class Panel(BaseModel):
    id: str
    title: str
    headline: str
    tiles: list[PanelTile] = Field(default_factory=list)
    rows: list[PanelRow] = Field(default_factory=list)
    generated_at: float
    empty: bool = False


# --- panel definitions ------------------------------------------------------


class CustomPanelSource(str, Enum):
    APPROVALS = "approvals"
    GOALS = "goals"
    REMINDERS = "reminders"
    MEMORY = "memory"
    FEED = "feed"


class CustomPanelFilter(str, Enum):
    ALL = "all"
    PENDING = "pending"  # approvals, reminders
    OVERDUE = "overdue"  # goals
    DUE_SOON = "due_soon"  # goals
    STALE = "stale"  # goals
    ACTIVE = "active"  # goals
    COMPLETED = "completed"  # goals
    HIGH_RISK = "high_risk"  # approvals


class CustomPanelSort(str, Enum):
    NEWEST = "newest"
    OLDEST = "oldest"


#: Which filters make sense for each source. Anything else is rejected with
#: a clarifying question, never guessed.
VALID_FILTERS: dict[CustomPanelSource, frozenset[CustomPanelFilter]] = {
    CustomPanelSource.APPROVALS: frozenset(
        {CustomPanelFilter.ALL, CustomPanelFilter.PENDING, CustomPanelFilter.HIGH_RISK}
    ),
    CustomPanelSource.GOALS: frozenset(
        {
            CustomPanelFilter.ALL,
            CustomPanelFilter.ACTIVE,
            CustomPanelFilter.OVERDUE,
            CustomPanelFilter.DUE_SOON,
            CustomPanelFilter.STALE,
            CustomPanelFilter.COMPLETED,
        }
    ),
    CustomPanelSource.REMINDERS: frozenset(
        {CustomPanelFilter.ALL, CustomPanelFilter.PENDING}
    ),
    CustomPanelSource.MEMORY: frozenset({CustomPanelFilter.ALL}),
    CustomPanelSource.FEED: frozenset({CustomPanelFilter.ALL}),
}

MAX_NAME_LEN = 80
MAX_LIMIT = 20
ROW_FIELDS = ("title", "detail", "timestamp")


class CustomPanelDef(BaseModel):
    """An inspectable, editable panel definition. The definition is the panel:
    no hidden queries, no black box."""

    id: str = Field(default_factory=lambda: "cpanel_" + uuid4().hex[:12])
    name: str
    source: CustomPanelSource
    filter: CustomPanelFilter = CustomPanelFilter.ALL
    sort: CustomPanelSort = CustomPanelSort.NEWEST
    limit: int = 5
    fields: list[str] = Field(default_factory=lambda: ["title", "detail", "timestamp"])
    created_at: float = Field(default_factory=_time.time)
    updated_at: float = Field(default_factory=_time.time)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join((v or "").split())
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > MAX_NAME_LEN:
            raise ValueError(f"name must be at most {MAX_NAME_LEN} characters")
        return v

    @field_validator("limit")
    @classmethod
    def _limit(cls, v: int) -> int:
        if not 1 <= v <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
        return v

    @field_validator("fields")
    @classmethod
    def _fields(cls, v: list[str]) -> list[str]:
        if "title" not in v:
            raise ValueError("fields must include 'title'")
        bad = [f for f in v if f not in ROW_FIELDS]
        if bad:
            raise ValueError(f"unknown row fields: {bad}; allowed: {list(ROW_FIELDS)}")
        return v


def validate_definition(defn: CustomPanelDef) -> None:
    """Cross-field validation: the filter must make sense for the source."""
    if defn.filter not in VALID_FILTERS[defn.source]:
        allowed = sorted(
            f.value for f in VALID_FILTERS[defn.source] if f != defn.filter
        )
        raise ValueError(
            f"filter '{defn.filter.value}' does not apply to source "
            f"'{defn.source.value}'; allowed: {allowed}"
        )


# --- registry ---------------------------------------------------------------


class CustomPanelRegistry:
    """Stores custom panel definitions. In-memory by default; pass a KV store
    (put(collection, id, obj) / all(collection, model) / delete(collection, id))
    for durability across restarts."""

    COLLECTION = "custom_panels"

    def __init__(self, kv: Any | None = None) -> None:
        self._kv = kv
        self._panels: dict[str, CustomPanelDef] = {}
        if kv is not None:
            try:
                rows = kv.all(self.COLLECTION, CustomPanelDef)
            except Exception:  # noqa: BLE001
                rows = []
            for raw in rows:
                try:
                    panel = (
                        raw
                        if isinstance(raw, CustomPanelDef)
                        else CustomPanelDef.model_validate(raw)
                    )
                    validate_definition(panel)
                except Exception:  # noqa: BLE001, S112
                    # One corrupt row must not drop the rest of the collection.
                    continue
                self._panels[panel.id] = panel

    def _persist(self, panel: CustomPanelDef) -> None:
        if self._kv is None:
            return
        try:
            self._kv.put(self.COLLECTION, panel.id, panel)
        except Exception:  # noqa: BLE001, S110
            # Persistence is best-effort; memory is the source of truth.
            pass

    def _unpersist(self, panel_id: str) -> None:
        if self._kv is None:
            return
        try:
            self._kv.delete(self.COLLECTION, panel_id)
        except Exception:  # noqa: BLE001, S110
            pass

    def create(self, defn: CustomPanelDef) -> CustomPanelDef:
        validate_definition(defn)
        defn.updated_at = _time.time()
        self._panels[defn.id] = defn
        self._persist(defn)
        return defn

    def get(self, panel_id: str) -> CustomPanelDef:
        return self._panels[panel_id]  # KeyError for unknown ids: fail loud

    def list(self) -> list[CustomPanelDef]:
        return sorted(self._panels.values(), key=lambda p: p.created_at)

    def update(
        self,
        panel_id: str,
        *,
        name: str | None = None,
        filter: CustomPanelFilter | None = None,
        sort: CustomPanelSort | None = None,
        limit: int | None = None,
        fields: list[str] | None = None,
    ) -> CustomPanelDef:
        panel = self.get(panel_id)
        data = panel.model_dump()
        if name is not None:
            data["name"] = name
        if filter is not None:
            data["filter"] = filter
        if sort is not None:
            data["sort"] = sort
        if limit is not None:
            data["limit"] = limit
        if fields is not None:
            data["fields"] = fields
        data["updated_at"] = _time.time()
        updated = CustomPanelDef.model_validate(data)
        validate_definition(updated)
        self._panels[panel_id] = updated
        self._persist(updated)
        return updated

    def delete(self, panel_id: str) -> None:
        self.get(panel_id)  # KeyError for unknown ids: fail loud
        del self._panels[panel_id]
        self._unpersist(panel_id)


# --- natural-language parser ------------------------------------------------

#: Sources the node can actually build panels from. Anything else the user
#: names is rejected explicitly, never guessed.
_SOURCE_WORDS: dict[CustomPanelSource, tuple[str, ...]] = {
    CustomPanelSource.APPROVALS: ("approval", "approvals"),
    CustomPanelSource.GOALS: ("goal", "goals"),
    CustomPanelSource.REMINDERS: ("reminder", "reminders"),
    CustomPanelSource.MEMORY: ("memory", "memories"),
    CustomPanelSource.FEED: ("feed",),
}

#: Words for data the node does not have, so the user gets an honest no
#: instead of a hallucinated panel.
_UNSUPPORTED_WORDS = (
    "calendar",
    "weather",
    "stock",
    "stocks",
    "market",
    "email",
    "emails",
    "inbox",
    "portfolio",
    "news",
    "bank",
    "flight",
    "flights",
)

_FILTER_WORDS: dict[CustomPanelFilter, tuple[str, ...]] = {
    CustomPanelFilter.OVERDUE: ("overdue",),
    CustomPanelFilter.DUE_SOON: ("due soon",),
    CustomPanelFilter.PENDING: ("pending", "waiting", "awaiting"),
    CustomPanelFilter.HIGH_RISK: ("high risk", "high-risk", "risky"),
    CustomPanelFilter.ACTIVE: ("active",),
    CustomPanelFilter.COMPLETED: ("completed", "done", "finished"),
    CustomPanelFilter.STALE: ("stale", "neglected"),
}

_LIMIT_RE = re.compile(r"\btop\s+(\d{1,2})\b")
_LIMIT_OF_RE = re.compile(
    r"\b(\d{1,2})\s+(?:overdue\s+|pending\s+|active\s+)?"
    r"(?:goals?|approvals?|reminders?|memories|memory|feed)\b"
)
_NAME_QUOTED_RE = re.compile(r'(?:called|named)\s+"([^"]+)"')
_NAME_BARE_RE = re.compile(
    r"(?:called|named)\s+([A-Za-z0-9][A-Za-z0-9 _-]*?)"
    r"(?=\s+(?:showing|show|with|for|of|from|my|the)\b|[.,;]|$)"
)


@dataclass
class PanelProposal:
    name: str
    source: CustomPanelSource
    filter: CustomPanelFilter
    sort: CustomPanelSort
    limit: int
    matched: dict[str, str] = field(default_factory=dict)


@dataclass
class PanelClarification:
    question: str
    options: list[str] = field(default_factory=list)


def _find_source(text: str) -> CustomPanelSource | None:
    for source, words in _SOURCE_WORDS.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", text):
                return source
    return None


def _find_unsupported(text: str) -> str | None:
    for w in _UNSUPPORTED_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", text):
            return w
    return None


def parse_panel_request(text: str) -> PanelProposal | PanelClarification:
    """Deterministically parse "make a panel showing my top 5 overdue goals".

    Returns a PanelProposal when the request is unambiguous, otherwise a
    PanelClarification with a question. Ambiguous input is never guessed.
    """
    lowered = (text or "").lower()

    source = _find_source(lowered)
    if source is None:
        bad = _find_unsupported(lowered)
        if bad:
            return PanelClarification(
                question=(
                    f"I cannot build a panel from '{bad}' yet: the node has no "
                    "such data source. I can build panels from goals, approvals, "
                    "reminders, memory, or feed. Which one should I use?"
                ),
                options=["goals", "approvals", "reminders", "memory", "feed"],
            )
        return PanelClarification(
            question=(
                "Which data should this panel show? I can build panels from "
                "goals, approvals, reminders, memory, or feed."
            ),
            options=["goals", "approvals", "reminders", "memory", "feed"],
        )

    detected_filter = CustomPanelFilter.ALL
    matched_filter_word = ""
    for filt, words in _FILTER_WORDS.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", lowered):
                detected_filter = filt
                matched_filter_word = w
                break
        if matched_filter_word:
            break

    if detected_filter not in VALID_FILTERS[source]:
        allowed = sorted(
            f.value for f in VALID_FILTERS[source] if f != CustomPanelFilter.ALL
        )
        allowed_str = ", ".join(allowed) if allowed else "no filters"
        return PanelClarification(
            question=(
                f"'{matched_filter_word}' does not apply to {source.value}. "
                f"For {source.value} I can filter by: {allowed_str}, or show all. "
                "Which should I use?"
            ),
            options=["all", *allowed],
        )

    sort = CustomPanelSort.NEWEST
    if re.search(r"\boldest\b", lowered):
        sort = CustomPanelSort.OLDEST

    limit = 5
    m = _LIMIT_RE.search(lowered) or _LIMIT_OF_RE.search(lowered)
    if m:
        limit = max(1, min(MAX_LIMIT, int(m.group(1))))

    name_match = _NAME_QUOTED_RE.search(text or "") or _NAME_BARE_RE.search(text or "")
    name = (
        name_match.group(1).strip()
        if name_match and name_match.group(1).strip()
        else f"My {source.value} panel"
    )

    return PanelProposal(
        name=name,
        source=source,
        filter=detected_filter,
        sort=sort,
        limit=limit,
        matched={
            "source": source.value,
            "filter": detected_filter.value,
            "sort": sort.value,
        },
    )


# --- API request models -------------------------------------------------------


class PanelParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class PanelUpdateRequest(BaseModel):
    name: str | None = None
    filter: CustomPanelFilter | None = None
    sort: CustomPanelSort | None = None
    limit: int | None = None
    fields: list[str] | None = None


class PanelDeleteRequest(BaseModel):
    confirm: bool = False


# --- rendering --------------------------------------------------------------


def _epoch(v: Any) -> float | None:
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


def _truncate(text: str, limit: int = 80) -> str:
    text = " ".join((text or "").split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


@dataclass
class PanelInputs:
    """Node-local data a custom panel can draw from. All lists, all local."""

    approvals: list[Any] = field(default_factory=list)  # ApprovalRequest
    goal_active: list[Any] = field(default_factory=list)  # GoalSummary
    goal_overdue: list[Any] = field(default_factory=list)
    goal_due_soon: list[Any] = field(default_factory=list)
    goal_stale: list[Any] = field(default_factory=list)
    goal_completed: list[Any] = field(default_factory=list)
    reminders: list[Any] = field(default_factory=list)  # Reminder
    memory_items: list[Any] = field(default_factory=list)  # MemoryItem
    feed_units: list[Any] = field(default_factory=list)  # FeedUnit


@dataclass
class _Row:
    title: str
    detail: str
    timestamp: float | None


def _approval_rows(pending: list[Any]) -> tuple[list[_Row], int]:
    rows = []
    high = 0
    for r in pending:
        risk = getattr(r, "risk_label", None)
        risk_value = getattr(risk, "value", str(risk))
        if risk_value == "high":
            high += 1
        card = getattr(r, "card", {}) or {}
        rows.append(
            _Row(
                title=_truncate(str(card.get("title", r.id))),
                detail=f"{risk_value} risk"
                + (
                    " · needs double confirmation"
                    if getattr(r, "requires_double_confirmation", False)
                    else ""
                ),
                timestamp=_epoch(getattr(r, "created_at", None)),
            )
        )
    return rows, high


def _goal_rows(summaries: list[Any]) -> list[_Row]:
    rows = []
    for s in summaries:
        target = getattr(s, "target_date", None)
        rows.append(
            _Row(
                title=_truncate(getattr(s, "title", "")),
                detail=f"{getattr(s, 'status', '')}"
                + (f" · target {target}" if target else "")
                + (
                    f" · {getattr(s, 'latest_percent', None)}% complete"
                    if getattr(s, "latest_percent", None) is not None
                    else ""
                ),
                timestamp=_epoch(getattr(s, "updated_at", None)),
            )
        )
    return rows


def _reminder_rows(reminders: list[Any]) -> list[_Row]:
    return [
        _Row(
            title=_truncate(getattr(r, "title", "")),
            detail=f"{getattr(r, 'status', '')} · due "
            + datetime.fromtimestamp(float(getattr(r, "due_at", 0)), tz=UTC).strftime(
                "%Y-%m-%d %H:%M"
            ),
            timestamp=_epoch(getattr(r, "due_at", None)),
        )
        for r in reminders
    ]


def _memory_rows(items: list[Any]) -> list[_Row]:
    rows = []
    for i in items:
        text = getattr(i, "text", "") or ""
        source = getattr(i, "source", None)
        attribution = ""
        if source is not None:
            attribution = (
                f"{getattr(source, 'title', '')} ({getattr(source, 'kind', '')})"
            )
        rows.append(
            _Row(
                title=_truncate(text, 60),
                detail=attribution,
                timestamp=_epoch(getattr(i, "created_at", None)),
            )
        )
    return rows


def _feed_rows(units: list[Any]) -> list[_Row]:
    return [
        _Row(
            title=_truncate(getattr(u, "title", "")),
            detail=str(getattr(u, "kind", "")),
            timestamp=_epoch(getattr(u, "created_at", None)),
        )
        for u in units
    ]


def _source_rows(defn: CustomPanelDef, inputs: PanelInputs) -> tuple[list[_Row], int]:
    """Rows for the definition's source+filter, plus the source total."""
    if defn.source == CustomPanelSource.APPROVALS:
        rows, _high = _approval_rows(inputs.approvals)
        if defn.filter == CustomPanelFilter.PENDING:
            pass  # inputs.approvals is already pending-only
        elif defn.filter == CustomPanelFilter.HIGH_RISK:
            rows = [r for r in rows if "high risk" in r.detail]
        return rows, len(inputs.approvals)
    if defn.source == CustomPanelSource.GOALS:
        pool = {
            CustomPanelFilter.ALL: inputs.goal_active,
            CustomPanelFilter.ACTIVE: inputs.goal_active,
            CustomPanelFilter.OVERDUE: inputs.goal_overdue,
            CustomPanelFilter.DUE_SOON: inputs.goal_due_soon,
            CustomPanelFilter.STALE: inputs.goal_stale,
            CustomPanelFilter.COMPLETED: inputs.goal_completed,
        }[defn.filter]
        return _goal_rows(pool), len(inputs.goal_active)
    if defn.source == CustomPanelSource.REMINDERS:
        pool = inputs.reminders
        if defn.filter == CustomPanelFilter.PENDING:
            pool = [r for r in pool if getattr(r, "status", "") == "pending"]
        return _reminder_rows(pool), len(inputs.reminders)
    if defn.source == CustomPanelSource.MEMORY:
        return _memory_rows(inputs.memory_items), len(inputs.memory_items)
    if defn.source == CustomPanelSource.FEED:
        return _feed_rows(inputs.feed_units), len(inputs.feed_units)
    raise ValueError(f"unknown source: {defn.source}")


def _headline(defn: CustomPanelDef, n: int) -> str:
    noun = {
        CustomPanelSource.APPROVALS: "approval",
        CustomPanelSource.GOALS: "goal",
        CustomPanelSource.REMINDERS: "reminder",
        CustomPanelSource.MEMORY: "memory item",
        CustomPanelSource.FEED: "feed unit",
    }[defn.source]
    nouns = noun + "s" if n != 1 else noun
    qualifier = {
        CustomPanelFilter.ALL: "",
        CustomPanelFilter.PENDING: "pending ",
        CustomPanelFilter.OVERDUE: "overdue ",
        CustomPanelFilter.DUE_SOON: "due soon ",
        CustomPanelFilter.STALE: "stale ",
        CustomPanelFilter.ACTIVE: "active ",
        CustomPanelFilter.COMPLETED: "completed ",
        CustomPanelFilter.HIGH_RISK: "high-risk ",
    }[defn.filter]
    if n == 0:
        return f"No {qualifier}{nouns} to show."
    return f"{n} {qualifier}{nouns}."


def render_panel(
    defn: CustomPanelDef, inputs: PanelInputs, now: float | None = None
) -> Panel:
    """Render a custom panel definition into panel JSON. Pure: no I/O."""
    now = now if now is not None else _time.time()
    rows, total = _source_rows(defn, inputs)
    reverse = defn.sort == CustomPanelSort.NEWEST
    rows.sort(key=lambda r: r.timestamp or 0.0, reverse=reverse)
    shown = rows[: defn.limit]

    panel_rows = []
    for r in shown:
        detail = r.detail if "detail" in defn.fields else ""
        timestamp = r.timestamp if "timestamp" in defn.fields else None
        panel_rows.append(PanelRow(title=r.title, detail=detail, timestamp=timestamp))

    return Panel(
        id=defn.id,
        title=defn.name,
        headline=_headline(defn, len(shown)),
        tiles=[
            PanelTile(label="Shown", value=str(len(shown))),
            PanelTile(label="Source total", value=str(total)),
        ],
        rows=panel_rows,
        generated_at=now,
        empty=len(shown) == 0,
    )
