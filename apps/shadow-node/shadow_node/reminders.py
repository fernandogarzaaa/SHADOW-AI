"""Reminders for the Shadow Node (Phase 5: scheduling + proactive).

A reminder is a user-created nudge with a due time and optional recurrence.
Due reminders fire through the `reminder_check` ambient task (or the manual
`POST /reminders/check` endpoint): firing marks the reminder, advances
recurring ones to their next occurrence, and emits a push notification, an
SSE event, and a feed unit. During configured quiet hours nothing fires;
due reminders wait for the first tick after quiet hours end.

Reminders persist encrypted in the runtime store's "reminders" collection
when configured, in-memory otherwise.
"""
from __future__ import annotations

import time
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

MAX_TITLE_LEN = 140
MAX_NOTE_LEN = 500

RECURRENCES = ("none", "daily", "weekly")
STATUSES = ("pending", "fired", "dismissed")


class Reminder(BaseModel):
    id: str = Field(default_factory=lambda: f"rem_{uuid4().hex}")
    title: str
    note: str = ""
    due_at: float
    recurrence: str = "none"
    status: str = "pending"
    last_fired_at: float | None = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > MAX_TITLE_LEN:
            raise ValueError(f"title must be at most {MAX_TITLE_LEN} chars")
        return v

    @field_validator("note")
    @classmethod
    def _note(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) > MAX_NOTE_LEN:
            raise ValueError(f"note must be at most {MAX_NOTE_LEN} chars")
        return v

    @field_validator("recurrence")
    @classmethod
    def _recurrence(cls, v: str) -> str:
        if v not in RECURRENCES:
            raise ValueError(f"recurrence must be one of {RECURRENCES}")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        return v


class ReminderCreate(BaseModel):
    title: str
    note: str = ""
    due_at: float
    recurrence: str = "none"

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > MAX_TITLE_LEN:
            raise ValueError(f"title must be at most {MAX_TITLE_LEN} chars")
        return v


class ReminderUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    note: str | None = Field(default=None, max_length=MAX_NOTE_LEN)
    due_at: float | None = None
    recurrence: str | None = None
    status: str | None = None


class ReminderStore:
    def __init__(self, runtime_store=None):
        self._store = runtime_store
        self.reminders: dict[str, Reminder] = {}
        if runtime_store is not None:
            for r in runtime_store.all("reminders", Reminder):
                self.reminders[r.id] = r

    def _save(self, r: Reminder) -> None:
        if self._store is not None:
            self._store.put("reminders", r.id, r)

    def _drop(self, reminder_id: str) -> None:
        if self._store is not None:
            self._store.delete("reminders", reminder_id)

    def create(self, data: ReminderCreate) -> Reminder:
        r = Reminder(title=data.title, note=data.note or "",
                     due_at=data.due_at, recurrence=data.recurrence)
        self.reminders[r.id] = r
        self._save(r)
        return r

    def get(self, reminder_id: str) -> Reminder | None:
        return self.reminders.get(reminder_id)

    def list(self, status: str | None = None) -> list[Reminder]:
        items = list(self.reminders.values())
        if status:
            items = [r for r in items if r.status == status]
        items.sort(key=lambda r: (r.due_at, r.created_at))
        return items

    def due(self, now: float | None = None) -> list[Reminder]:
        now = now if now is not None else time.time()
        return [r for r in self.list("pending") if r.due_at <= now]

    def update(self, reminder_id: str, patch: ReminderUpdate) -> Reminder | None:
        r = self.reminders.get(reminder_id)
        if r is None:
            return None
        data = r.model_dump()
        for field in ("title", "note", "due_at", "recurrence", "status"):
            v = getattr(patch, field)
            if v is not None:
                data[field] = v
        data["updated_at"] = time.time()
        r = Reminder(**data)  # re-validate
        self.reminders[reminder_id] = r
        self._save(r)
        return r

    def delete(self, reminder_id: str) -> bool:
        if reminder_id not in self.reminders:
            return False
        del self.reminders[reminder_id]
        self._drop(reminder_id)
        return True

    def fire(self, reminder_id: str, now: float | None = None) -> Reminder | None:
        """Fire one due reminder. Recurring reminders advance to their next
        occurrence and stay pending; one-shots become fired."""
        now = now if now is not None else time.time()
        r = self.reminders.get(reminder_id)
        if r is None or r.status != "pending":
            return None
        if r.recurrence == "daily":
            step = 86400
        elif r.recurrence == "weekly":
            step = 7 * 86400
        else:
            step = 0
        if step:
            r.due_at += step
            # If the next occurrence is already past (node was down a while),
            # keep pushing forward so we do not fire a burst of catch-ups.
            while r.due_at <= now:
                r.due_at += step
        else:
            r.status = "fired"
        r.last_fired_at = now
        r.updated_at = now
        self._save(r)
        return r


def fire_due(store: "ReminderStore", now: float, is_quiet, notify, publish,
             feed_store) -> list[Reminder]:
    """Fire every due reminder: mark it (advancing recurrences), then notify.

    `is_quiet()` gates the whole pass: during quiet hours nothing fires and
    due reminders wait for the next check. `notify(title, body, data)` sends
    the push, `publish(event_type, payload)` emits the SSE event, and each
    firing is recorded as a "reminder" feed unit. Returns the fired reminders.
    """
    from .feed import FeedUnit, MAX_BODY_LEN

    if is_quiet():
        return []
    fired: list[Reminder] = []
    for r in store.due(now):
        updated = store.fire(r.id, now)
        if updated is None:
            continue
        body = updated.note or f"Reminder: {updated.title}"
        notify("Reminder", updated.title,
               {"type": "reminder.fired", "reminder_id": updated.id})
        publish("reminder.fired", {"reminder_id": updated.id, "title": updated.title,
                                   "fired_at": updated.last_fired_at,
                                   "recurrence": updated.recurrence})
        feed_store.add(FeedUnit(kind="reminder", title=updated.title,
                                body=body[:MAX_BODY_LEN]))
        fired.append(updated)
    return fired
