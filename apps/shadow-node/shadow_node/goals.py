"""User goals with progress tracking and briefings.

A goal is a durable outcome the user works toward (a Cookie/Muse.AI parity
feature, reimplemented local-first). Progress entries are timestamped notes
with an optional percent-complete; the briefing surfaces stale goals, goals
due soon, and recent progress.

Durability mirrors the persona module: when SHADOW_RUNTIME_DB is configured,
goals live encrypted in the runtime store's "goals" / "goal_progress"
collections; otherwise they are in-memory for the process lifetime.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

MAX_TITLE_LEN = 120
MAX_DESC_LEN = 2000
MAX_NOTE_LEN = 2000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STALE_AFTER_DAYS = 7
DUE_SOON_DAYS = 7


class GoalStatus(str):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

    @classmethod
    def values(cls):
        return (cls.ACTIVE, cls.COMPLETED, cls.ABANDONED)


def _clean_title(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("title must not be empty")
    if len(v) > MAX_TITLE_LEN:
        raise ValueError(f"title must be at most {MAX_TITLE_LEN} chars")
    return v


def _clean_description(v: str | None) -> str:
    v = (v or "").strip()
    if len(v) > MAX_DESC_LEN:
        raise ValueError(f"description must be at most {MAX_DESC_LEN} chars")
    return v


def _clean_target_date(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    v = v.strip()
    if not DATE_RE.match(v):
        raise ValueError("target_date must be YYYY-MM-DD")
    try:
        datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError("target_date is not a real calendar date")
    return v


class Goal(BaseModel):
    id: str = Field(default_factory=lambda: f"goal_{uuid4().hex}")
    title: str
    description: str = ""
    status: str = GoalStatus.ACTIVE
    target_date: str | None = None  # YYYY-MM-DD
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return _clean_title(v)

    @field_validator("description")
    @classmethod
    def _description(cls, v: str) -> str:
        return _clean_description(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in GoalStatus.values():
            raise ValueError(f"status must be one of {GoalStatus.values()}")
        return v

    @field_validator("target_date")
    @classmethod
    def _target_date(cls, v: str | None) -> str | None:
        return _clean_target_date(v)


class GoalCreate(BaseModel):
    title: str
    description: str = ""
    target_date: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return _clean_title(v)

    @field_validator("description")
    @classmethod
    def _description(cls, v: str) -> str:
        return _clean_description(v)

    @field_validator("target_date")
    @classmethod
    def _target_date(cls, v: str | None) -> str | None:
        return _clean_target_date(v)


class GoalUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    description: str | None = Field(default=None, max_length=MAX_DESC_LEN)
    status: str | None = None
    target_date: str | None = None  # None = unchanged; "" = clear


class ProgressEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"prog_{uuid4().hex}")
    goal_id: str
    note: str
    percent: int | None = None  # 0-100
    created_at: float = Field(default_factory=time.time)

    @field_validator("note")
    @classmethod
    def _note(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("note must not be empty")
        if len(v) > MAX_NOTE_LEN:
            raise ValueError(f"note must be at most {MAX_NOTE_LEN} chars")
        return v

    @field_validator("percent")
    @classmethod
    def _percent(cls, v: int | None) -> int | None:
        if v is not None and not 0 <= v <= 100:
            raise ValueError("percent must be 0-100")
        return v


class ProgressCreate(BaseModel):
    note: str
    percent: int | None = None


class GoalSummary(BaseModel):
    """Goal plus roll-up for list views."""

    id: str
    title: str
    description: str
    status: str
    target_date: str | None
    created_at: float
    updated_at: float
    entry_count: int
    latest_percent: int | None
    last_progress_at: float | None


class GoalDetail(Goal):
    entries: list[ProgressEntry] = []


class BriefingEntry(BaseModel):
    id: str
    goal_id: str
    goal_title: str
    note: str
    percent: int | None
    created_at: float


class GoalsBriefing(BaseModel):
    generated_at: float
    active_count: int
    completed_count: int
    stale: list[GoalSummary] = []
    due_soon: list[GoalSummary] = []
    overdue: list[GoalSummary] = []
    completed_this_week: list[GoalSummary] = []
    recent_entries: list[BriefingEntry] = []


def _day_start(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _target_day(target_date: str) -> datetime:
    return datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)


class GoalStore:
    """In-memory goal state with encrypted runtime-store persistence."""

    def __init__(self, runtime_store=None):
        self._store = runtime_store
        self.goals: dict[str, Goal] = {}
        self.entries: dict[str, ProgressEntry] = {}
        if runtime_store is not None:
            for g in runtime_store.all("goals", Goal):
                self.goals[g.id] = g
            for e in runtime_store.all("goal_progress", ProgressEntry):
                self.entries[e.id] = e

    # -- persistence helpers -------------------------------------------------
    def _save_goal(self, goal: Goal) -> None:
        if self._store is not None:
            self._store.put("goals", goal.id, goal)

    def _save_entry(self, entry: ProgressEntry) -> None:
        if self._store is not None:
            self._store.put("goal_progress", entry.id, entry)

    def _delete_persisted(self, collection: str, id: str) -> None:
        if self._store is not None:
            self._store.delete(collection, id)

    # -- goals ---------------------------------------------------------------
    def create(self, data: GoalCreate) -> Goal:
        goal = Goal(title=data.title, description=data.description or "",
                    target_date=data.target_date)
        self.goals[goal.id] = goal
        self._save_goal(goal)
        return goal

    def get(self, goal_id: str) -> Goal | None:
        return self.goals.get(goal_id)

    def list(self, status: str | None = None) -> list[Goal]:
        goals = list(self.goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        goals.sort(key=lambda g: g.updated_at, reverse=True)
        return goals

    def update(self, goal_id: str, patch: GoalUpdate) -> Goal | None:
        goal = self.goals.get(goal_id)
        if goal is None:
            return None
        data = goal.model_dump()
        if patch.title is not None:
            data["title"] = patch.title
        if patch.description is not None:
            data["description"] = patch.description
        if patch.status is not None:
            data["status"] = patch.status
        if patch.target_date is not None:
            data["target_date"] = patch.target_date
        data["updated_at"] = time.time()
        goal = Goal(**data)  # re-validate
        self.goals[goal_id] = goal
        self._save_goal(goal)
        return goal

    def delete(self, goal_id: str) -> bool:
        if goal_id not in self.goals:
            return False
        del self.goals[goal_id]
        for eid in [e for e, en in self.entries.items() if en.goal_id == goal_id]:
            del self.entries[eid]
            self._delete_persisted("goal_progress", eid)
        self._delete_persisted("goals", goal_id)
        return True

    # -- progress ------------------------------------------------------------
    def add_progress(self, goal_id: str, data: ProgressCreate) -> ProgressEntry | None:
        if goal_id not in self.goals:
            return None
        entry = ProgressEntry(goal_id=goal_id, note=data.note, percent=data.percent)
        self.entries[entry.id] = entry
        self._save_entry(entry)
        goal = self.goals[goal_id]
        goal.updated_at = entry.created_at
        self._save_goal(goal)
        return entry

    def entries_for(self, goal_id: str) -> list[ProgressEntry]:
        out = [e for e in self.entries.values() if e.goal_id == goal_id]
        out.sort(key=lambda e: e.created_at, reverse=True)
        return out

    # -- summaries & briefing ------------------------------------------------
    def summarize(self, goal: Goal) -> GoalSummary:
        entries = self.entries_for(goal.id)
        latest_percent = next(
            (e.percent for e in entries if e.percent is not None), None
        )
        return GoalSummary(
            **goal.model_dump(),
            entry_count=len(entries),
            latest_percent=latest_percent,
            last_progress_at=entries[0].created_at if entries else None,
        )

    def detail(self, goal_id: str) -> GoalDetail | None:
        goal = self.goals.get(goal_id)
        if goal is None:
            return None
        return GoalDetail(**goal.model_dump(), entries=self.entries_for(goal_id))

    def briefing(self, now: float | None = None) -> GoalsBriefing:
        now = now if now is not None else time.time()
        today = _day_start(now)
        stale_cutoff = now - STALE_AFTER_DAYS * 86400
        week_cutoff = now - 7 * 86400

        active = [g for g in self.goals.values() if g.status == GoalStatus.ACTIVE]
        summaries = {g.id: self.summarize(g) for g in active}

        stale, due_soon, overdue = [], [], []
        for g in active:
            s = summaries[g.id]
            if (s.last_progress_at or g.created_at) < stale_cutoff:
                stale.append(s)
            if g.target_date:
                target = _target_day(g.target_date)
                if target < today:
                    overdue.append(s)
                elif (target - today).days <= DUE_SOON_DAYS:
                    due_soon.append(s)

        completed_this_week = [
            self.summarize(g)
            for g in self.goals.values()
            if g.status == GoalStatus.COMPLETED and g.updated_at >= week_cutoff
        ]
        completed_this_week.sort(key=lambda s: s.updated_at, reverse=True)

        recent_entries = sorted(
            (e for e in self.entries.values() if e.created_at >= week_cutoff),
            key=lambda e: e.created_at,
            reverse=True,
        )[:10]
        recent = [
            BriefingEntry(
                id=e.id, goal_id=e.goal_id,
                goal_title=self.goals[e.goal_id].title if e.goal_id in self.goals else "?",
                note=e.note, percent=e.percent, created_at=e.created_at,
            )
            for e in recent_entries
        ]

        stale.sort(key=lambda s: s.last_progress_at or 0)
        due_soon.sort(key=lambda s: s.target_date or "")
        overdue.sort(key=lambda s: s.target_date or "")

        return GoalsBriefing(
            generated_at=now,
            active_count=len(active),
            completed_count=sum(
                1 for g in self.goals.values() if g.status == GoalStatus.COMPLETED
            ),
            stale=stale,
            due_soon=due_soon,
            overdue=overdue,
            completed_this_week=completed_this_week,
            recent_entries=recent,
        )
