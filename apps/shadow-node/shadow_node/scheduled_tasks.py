"""Unified scheduled-tasks surface for the Shadow Node.

One shape for everything on a schedule: user reminders (recurring or not)
plus the node's builtin ambient tasks. The client Scheduled Tasks screen
uses this instead of juggling /reminders and /ambient/* separately.
Every scheduled thing is visible here; there are no hidden schedules.
"""

from __future__ import annotations

import time as _time

from pydantic import BaseModel, Field

from .reminders import MAX_NOTE_LEN, MAX_TITLE_LEN, RECURRENCES
from .schedule_parse import describe_cadence

AMBIENT_ID_PREFIX = "ambient:"

AMBIENT_TASK_TITLES = {
    "morning_brief": (
        "Morning brief",
        "Digest of pending approvals, recent executions, claims, devices.",
    ),
    "memory_digest": ("Memory digest", "Inventory of the local memory store."),
    "feed_digest": (
        "Feed digest",
        "Renders editorial feed units into the feed journal.",
    ),
    "reminder_check": (
        "Reminder check",
        "Fires due reminders through notify/publish/feed.",
    ),
    "shadow_acts": (
        "Shadow acts",
        "Runs registered Shadow Acts through the policy gate.",
    ),
}


class ScheduledTask(BaseModel):
    id: str
    kind: str  # "reminder" | "ambient_task"
    title: str
    description: str = ""
    cadence: str  # plain words, e.g. "Every weekday at 7:00 AM"
    recurrence: str | None = None  # reminder recurrence, None for ambient
    enabled: bool = True
    status: str | None = None  # reminder status, None for ambient
    next_run: float | None = None  # epoch seconds, None when not scheduled
    last_run: float | None = None  # epoch seconds of last run/fire
    due_at: float | None = None  # reminder first/next due, None for ambient
    note: str = ""


def humanize_interval(seconds: int) -> str:
    if seconds % 86400 == 0:
        n = seconds // 86400
        return f"{n} day" if n == 1 else f"{n} days"
    if seconds % 3600 == 0:
        n = seconds // 3600
        return f"{n} hour" if n == 1 else f"{n} hours"
    if seconds % 60 == 0:
        n = seconds // 60
        return f"{n} minute" if n == 1 else f"{n} minutes"
    return f"{seconds} seconds"


def _as_epoch(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return v.timestamp()
    except AttributeError:
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def reminder_to_task(r) -> ScheduledTask:
    next_run = r.due_at if (r.enabled and r.status == "pending") else None
    return ScheduledTask(
        id=r.id,
        kind="reminder",
        title=r.title,
        description=r.note or "",
        cadence=describe_cadence(r.recurrence, r.due_at),
        recurrence=r.recurrence,
        enabled=r.enabled,
        status=r.status,
        next_run=next_run,
        last_run=r.last_fired_at,
        due_at=r.due_at,
        note=r.note or "",
    )


def ambient_task_to_task(name: str, scheduler, checkpoints) -> ScheduledTask:
    from .ambient_tasks import BUILTIN_TASKS

    cfg = scheduler.get_config()
    in_config = name in (cfg.tasks or [])
    enabled = bool(cfg.enabled and in_config)
    title, description = AMBIENT_TASK_TITLES.get(name, (name, ""))

    next_run = None
    if enabled:
        wait = scheduler.seconds_until_due()
        if wait != float("inf"):
            next_run = _time.time() + wait

    last_run = None
    for cp in checkpoints.all():
        if getattr(cp, "kind", None) != "ambient":
            continue
        results = getattr(cp, "results", None) or []
        if any(isinstance(res, dict) and res.get("task") == name for res in results):
            last_run = _as_epoch(getattr(cp, "updated_at", None))
            break

    cadence = f"Every {humanize_interval(cfg.interval_seconds)} (ambient tick)"
    if name not in BUILTIN_TASKS:
        description = (description + " [unknown task: not in builtin set]").strip()
    return ScheduledTask(
        id=f"{AMBIENT_ID_PREFIX}{name}",
        kind="ambient_task",
        title=title,
        description=description,
        cadence=cadence,
        recurrence=None,
        enabled=enabled,
        status=None,
        next_run=next_run,
        last_run=last_run,
    )


def list_scheduled_tasks(reminder_store, scheduler, checkpoints) -> list[ScheduledTask]:
    from .ambient_tasks import build_task_map

    tasks = [reminder_to_task(r) for r in reminder_store.list()]
    known = set(build_task_map())
    cfg = scheduler.get_config()
    # Every builtin task is visible, whether or not it is currently enabled.
    # Configured-but-unknown task names are surfaced too: no hidden schedules.
    names = sorted(known | set(cfg.tasks or []))
    tasks.extend(ambient_task_to_task(n, scheduler, checkpoints) for n in names)
    tasks.sort(key=lambda t: (t.next_run is None, t.next_run or 0.0, t.title))
    return tasks


def split_task_id(task_id: str) -> tuple[str, str] | None:
    """Split a unified id into ("reminder", id) or ("ambient", name)."""
    if task_id.startswith(AMBIENT_ID_PREFIX):
        name = task_id[len(AMBIENT_ID_PREFIX) :]
        return ("ambient", name) if name else None
    if ":" in task_id:
        return None
    return ("reminder", task_id)


class ScheduledTaskUpdate(BaseModel):
    """PATCH body for /scheduled-tasks/{id}. For ambient tasks only
    `enabled` is accepted; every other field is a 422 there."""

    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    note: str | None = Field(default=None, max_length=MAX_NOTE_LEN)
    due_at: float | None = None
    recurrence: str | None = None
    status: str | None = None
    enabled: bool | None = None


def is_valid_recurrence(v: str) -> bool:
    return v in RECURRENCES
