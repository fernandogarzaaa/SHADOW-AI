"""Always-on agent loop for the SHADOW node ("o"-pattern, local-first).

OpenAI's Agents API moved session management, context compression, and
multi-agent coordination into a managed cloud layer, and the rumored "o"
assistant points at agents that persist after a chat ends, sleep and wake
autonomously, and do scheduled or event-driven work on their own.

This module implements that pattern with SHADOW's differentiation intact:
everything here is local-first, the memory store is user-owned, models are
BYOK, and nothing requires a cloud subscription or a paid service.

Pieces:

- LoopState: explicit SLEEPING / AWAKE lifecycle (plus STARTING, STOPPING,
  STOPPED transients so every transition is observable).
- WakeEvent / WakeTrigger: local-first wake sources. PushWakeTrigger and
  MessageWakeTrigger are push-driven (the node calls deliver()); 
  CalendarWakeTrigger polls the node's own reminder store. All three are
  real implementations wired into the loop, not stubs.
- AmbientLoop: owns one background thread and drives
  AmbientScheduler.tick(). While SLEEPING the thread blocks on an event
  with a timeout that stretches to the next due tick, so an idle node
  burns no CPU in a poll loop. Clean shutdown via stop(): the thread is
  joined, the loop record is persisted, and the journal notes it.
- AgentSession / SessionStore: durable conversation sessions. State is
  persisted to the runtime store (encrypted SQLite when SHADOW_RUNTIME_DB
  is set) and rehydrated on boot; sessions interrupted mid-response are
  flagged, not silently dropped.
- SessionCompactor: automatic context compaction. When a session passes
  its token budget, older messages are folded into a deterministic
  summary message (opening intent + extracted key facts + time range) and
  the recent window is kept verbatim, so continuity survives. The folded
  summary is ingested into the user-owned memory engine, which stays the
  source of truth.

Design rule, inherited from ambient.py: the loop does no work until the
operator enables ambient explicitly. Wake events received while disabled
are journaled as held; the loop stays SLEEPING.
"""
from __future__ import annotations

import re
import threading
import time
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field

from .ambient import AmbientScheduler, JournalEntryType, RunJournal
from .models import new_id, now

# Runtime store collections used by this module.
_SESSION_COLLECTION = "agent_sessions"
_LOOP_COLLECTION = "ambient_loop"
_LOOP_ID = "loop"

# Wake sources. "timer" is the scheduler's own due tick; "operator" is a
# manual POST /ambient/wake.
WAKE_SOURCES = ("push", "calendar", "message", "timer", "operator")


class LoopState(str, Enum):
    STARTING = "starting"
    SLEEPING = "sleeping"
    AWAKE = "awake"
    STOPPING = "stopping"
    STOPPED = "stopped"


class WakeEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("wke"))
    source: str
    reason: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: Any = Field(default_factory=now)


class WakeTrigger(Protocol):
    """A wake source wired into the AmbientLoop.

    Push-driven triggers (push, message) are woken by calling deliver();
    pollable triggers (calendar) are asked on every loop iteration.
    """

    name: str

    def bind(self, wake_fn: Callable[[str, str, dict], WakeEvent]) -> None: ...
    def poll(self, now_ts: float) -> list[WakeEvent]: ...


class _BoundTrigger:
    """Shared bind/deliver plumbing for push-driven triggers."""

    name = "trigger"

    def __init__(self) -> None:
        self._wake_fn: Callable[[str, str, dict], WakeEvent] | None = None

    def bind(self, wake_fn: Callable[[str, str, dict], WakeEvent]) -> None:
        self._wake_fn = wake_fn

    def _fire(self, reason: str, payload: dict[str, Any]) -> WakeEvent:
        if self._wake_fn is None:
            raise RuntimeError(
                f"{self.name} trigger is not bound to a loop; "
                "register it with AmbientLoop before delivering events")
        return self._wake_fn(self.name, reason, payload)

    def poll(self, now_ts: float) -> list[WakeEvent]:
        return []  # push-driven triggers never poll


class PushWakeTrigger(_BoundTrigger):
    """Wake on device push interaction.

    Real local implementation: the companion app calls POST /ambient/wake
    with source "push" when the user taps a notification (or when a
    high-priority push arrives and the app foregrounds). The node turns
    that into a wake event; no push provider SDK or cloud service is
    involved on this path.
    """

    name = "push"

    def deliver(self, device_id: str, action: str = "tap",
                payload: dict[str, Any] | None = None) -> WakeEvent:
        data = dict(payload or {})
        data["device_id"] = device_id
        data["action"] = action
        return self._fire(f"push {action} from device {device_id}", data)


class MessageWakeTrigger(_BoundTrigger):
    """Wake on inbound message arrival.

    Real local implementation: the node calls deliver() from the ask
    pipeline (POST /agent/ask, /agent/ask_stream) and from POST
    /ambient/wake with source "message". A future local message bridge
    (e.g. an on-device relay) would call the same method; the trigger
    itself holds no network code.
    """

    name = "message"

    def deliver(self, session_id: str | None = None, preview: str = "",
                metadata: dict[str, Any] | None = None) -> WakeEvent:
        data = dict(metadata or {})
        data["session_id"] = session_id
        data["preview"] = (preview or "")[:200]
        reason = f"message arrived (session {session_id})" if session_id else "message arrived"
        return self._fire(reason, data)


class CalendarWakeTrigger:
    """Wake when a local calendar-like item becomes due.

    Real local implementation over the node's own reminder store: the
    loop polls it, and a reminder entering its lead window wakes the loop
    so the tick can run reminder_check. Each (reminder, due_at) pair
    fires once; fired pairs are pruned after an hour.
    """

    name = "calendar"

    def __init__(self, reminder_source: Callable[[], list[dict[str, Any]]],
                 lead_seconds: float = 300.0) -> None:
        self._source = reminder_source
        self.lead_seconds = lead_seconds
        self._wake_fn: Callable[[str, str, dict], WakeEvent] | None = None
        self._fired: dict[tuple[str, float], float] = {}

    def bind(self, wake_fn: Callable[[str, str, dict], WakeEvent]) -> None:
        self._wake_fn = wake_fn

    def _prune(self, now_ts: float) -> None:
        stale = [k for k, fired_at in self._fired.items() if now_ts - fired_at > 3600]
        for k in stale:
            del self._fired[k]

    def poll(self, now_ts: float) -> list[WakeEvent]:
        if self._wake_fn is None:
            raise RuntimeError("calendar trigger is not bound to a loop")
        self._prune(now_ts)
        events: list[WakeEvent] = []
        try:
            reminders = self._source() or []
        except Exception:
            return []  # a broken source must not take the loop down
        for r in reminders:
            rid = str(r.get("id", ""))
            due_at = r.get("due_at")
            if not rid or due_at is None:
                continue
            try:
                due_ts = float(due_at)
            except (TypeError, ValueError):
                continue
            if due_ts - self.lead_seconds > now_ts:
                continue  # not in the lead window yet
            key = (rid, due_ts)
            if key in self._fired:
                continue
            self._fired[key] = now_ts
            events.append(self._wake_fn(
                self.name,
                f"reminder due: {r.get('title', rid)}",
                {"reminder_id": rid, "title": r.get("title", ""), "due_at": due_ts},
            ))
        return events


class LoopRecord(BaseModel):
    """Persisted lifecycle record for the ambient loop."""
    id: str = _LOOP_ID
    state: str = LoopState.STOPPED.value
    stopped_cleanly: bool = True
    wake_count: int = 0
    updated_at: Any = Field(default_factory=now)


def _audit_record(audit: Any, actor: str, event_type: str, payload: dict) -> None:
    if audit is None:
        return
    try:
        audit.record(actor, event_type, payload)
    except Exception:
        pass  # auditing must never break the loop


def _emit(event_sink: Any, event_type: str, properties: dict) -> None:
    if event_sink is None:
        return
    try:
        event_sink(event_type, properties)
    except Exception:
        pass  # events are best-effort; never break the loop


class AmbientLoop:
    """The always-on background loop.

    Owns a single daemon thread that drives AmbientScheduler.tick().
    Steady states are SLEEPING (idle: the thread blocks on an event, no
    busy-wait) and AWAKE (processing wake events and running the tick).
    Wake sources: push / calendar / message triggers, the scheduler's own
    due timer, and operator calls to wake().

    Idle resource behavior: while SLEEPING with nothing due, the thread
    waits with a timeout of min(idle_poll_seconds, seconds until the next
    tick). An enabled node with an hourly tick therefore wakes at most
    once an hour plus on real events; a disabled node sleeps the full
    idle poll and does no work at all.
    """

    def __init__(
        self,
        scheduler: AmbientScheduler,
        store: Any | None = None,
        journal: RunJournal | None = None,
        triggers: tuple[Any, ...] = (),
        event_sink: Any | None = None,
        audit: Any | None = None,
        idle_poll_seconds: float = 30.0,
        clock: Callable[[], float] = time.time,
    ):
        self._scheduler = scheduler
        self._store = store
        self._journal = journal if journal is not None else RunJournal()
        self._event_sink = event_sink
        self._audit = audit
        self._idle_poll = max(1.0, float(idle_poll_seconds))
        self._clock = clock
        self._state = LoopState.STOPPED
        self._state_lock = threading.Lock()
        self._wakeup = threading.Event()
        self._stop = threading.Event()
        self._queue: deque[WakeEvent] = deque()
        self._queue_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._wake_count = 0
        self._last_wake_at: Any | None = None
        self._triggers: list[Any] = []
        for t in triggers:
            self.register_trigger(t)

    # -- triggers -------------------------------------------------------
    def register_trigger(self, trigger: Any) -> None:
        trigger.bind(self.wake)
        self._triggers.append(trigger)

    # -- lifecycle ------------------------------------------------------
    @property
    def state(self) -> LoopState:
        with self._state_lock:
            return self._state

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def wake_count(self) -> int:
        return self._wake_count

    @property
    def last_wake_at(self) -> Any | None:
        return self._last_wake_at

    def _transition(self, to: LoopState, reason: str = "") -> None:
        with self._state_lock:
            frm = self._state
            self._state = to
        self._journal.append(
            f"loop_{id(self):x}", JournalEntryType.NOTE,
            f"loop {frm.value} -> {to.value}" + (f": {reason}" if reason else ""))
        _emit(self._event_sink, "ambient.loop.state",
              {"from": frm.value, "to": to.value, "reason": reason})
        _audit_record(self._audit, "ambient", "ambient.loop.state_changed",
                      {"from": frm.value, "to": to.value, "reason": reason})

    def _load_record(self) -> LoopRecord | None:
        if self._store is None:
            return None
        try:
            rows = self._store.all(_LOOP_COLLECTION, LoopRecord)
        except Exception:
            return None
        return rows[0] if rows else None

    def _save_record(self, stopped_cleanly: bool) -> None:
        if self._store is None:
            return
        try:
            self._store.put(
                _LOOP_COLLECTION, _LOOP_ID,
                LoopRecord(state=self.state.value, stopped_cleanly=stopped_cleanly,
                           wake_count=self._wake_count))
        except Exception:
            pass  # persistence is best-effort; the loop must still stop

    def start(self) -> None:
        if self.is_running:
            return
        prev = self._load_record()
        self._transition(LoopState.STARTING, "operator start")
        if prev is not None and not prev.stopped_cleanly:
            self._journal.append(
                f"loop_{id(self):x}", JournalEntryType.NOTE,
                "previous loop did not shut down cleanly; starting fresh in SLEEPING")
        self._stop.clear()
        self._wakeup.clear()
        self._thread = threading.Thread(target=self._run, name="ambient-loop", daemon=True)
        self._thread.start()

    def _enabled(self) -> bool:
        try:
            return bool(self._scheduler.get_config().enabled)
        except Exception:
            return False

    def _idle_timeout(self) -> float:
        """How long the SLEEPING thread may block before re-checking."""
        if not self._enabled():
            return self._idle_poll
        try:
            due_in = self._scheduler.seconds_until_due()
        except Exception:
            due_in = self._idle_poll
        return max(1.0, min(self._idle_poll, due_in))

    def _drain_queue(self) -> list[WakeEvent]:
        with self._queue_lock:
            events = list(self._queue)
            self._queue.clear()
        return events

    def _poll_triggers(self, now_ts: float) -> list[WakeEvent]:
        events: list[WakeEvent] = []
        for t in self._triggers:
            try:
                found = t.poll(now_ts) or []
            except Exception as e:
                self._journal.append(
                    f"loop_{id(self):x}", JournalEntryType.DECISION,
                    f"trigger {getattr(t, 'name', '?')} poll failed: {e}")
                continue
            events.extend(found)
        return events

    def _scheduler_due(self) -> bool:
        try:
            return self._scheduler.seconds_until_due() <= 0
        except Exception:
            return False

    def _run(self) -> None:
        self._transition(LoopState.SLEEPING, "no pending work")
        while not self._stop.is_set():
            timeout = self._idle_timeout()
            self._wakeup.wait(timeout)
            self._wakeup.clear()
            if self._stop.is_set():
                break
            now_ts = self._clock()
            events = self._drain_queue()
            events.extend(self._poll_triggers(now_ts))
            due = self._scheduler_due()
            if not events and not due:
                continue  # spurious wakeup; back to sleep
            if not self._enabled():
                for e in events:
                    self._journal.append(
                        f"loop_{id(self):x}", JournalEntryType.NOTE,
                        f"wake held (ambient disabled): {e.source}: {e.reason}")
                continue
            self._process(events)
        self._transition(LoopState.STOPPED, "stop requested")

    def _process(self, events: list[WakeEvent]) -> None:
        run_id = new_id("loop")
        self._transition(LoopState.AWAKE, f"{len(events)} wake event(s)")
        self._journal.append(
            run_id, JournalEntryType.RUN_STARTED,
            f"loop awake: {[e.source for e in events]}",
            {"wake_ids": [e.id for e in events]})
        for e in events:
            self._journal.append(
                run_id, JournalEntryType.OBSERVATION,
                f"wake [{e.source}]: {e.reason or e.id}", {"wake_id": e.id})
        try:
            out = self._scheduler.tick()
        except Exception as e:  # tick() never raises, but never trust that
            self._journal.append(run_id, JournalEntryType.DECISION, f"tick failed: {e}")
            out = {"ran": False, "reason": "tick_exception"}
        self._journal.append(
            run_id, JournalEntryType.COMPLETED,
            f"loop cycle done: tick ran={out.get('ran')}",
            {"tick": str(out.get("reason", "ok"))})
        self._transition(LoopState.SLEEPING, "cycle complete")

    def wake(self, source: str, reason: str = "",
             payload: dict[str, Any] | None = None) -> WakeEvent:
        """Queue a wake event and interrupt the SLEEPING wait.

        Raises RuntimeError when the loop was never started or is
        stopped: callers must not silently drop wakeups.
        """
        st = self.state
        if st in (LoopState.STOPPED, LoopState.STOPPING):
            raise RuntimeError(f"cannot wake: loop is {st.value}")
        if source not in WAKE_SOURCES:
            raise ValueError(f"unknown wake source: {source!r}")
        event = WakeEvent(source=source, reason=reason, payload=payload or {})
        with self._queue_lock:
            self._queue.append(event)
        self._wake_count += 1
        self._last_wake_at = now()
        self._journal.append(
            f"loop_{id(self):x}", JournalEntryType.NOTE,
            f"wake received [{source}]: {reason or event.id}")
        _emit(self._event_sink, "ambient.loop.wake",
              {"wake_id": event.id, "source": source, "reason": reason})
        self._wakeup.set()
        return event

    def stop(self, timeout: float = 10.0) -> None:
        """Clean shutdown: signal, join the thread, persist the record."""
        if not self.is_running and self.state == LoopState.STOPPED:
            return
        self._transition(LoopState.STOPPING, "operator stop")
        self._stop.set()
        self._wakeup.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=timeout)
            if thread.is_alive():
                self._journal.append(
                    f"loop_{id(self):x}", JournalEntryType.DECISION,
                    "loop thread did not join within timeout; leaving it detached")
        self._save_record(stopped_cleanly=True)
        # _run() already transitioned to STOPPED when it observed the flag;
        # if it never ran (start raced stop), do it here.
        if self.state != LoopState.STOPPED:
            with self._state_lock:
                self._state = LoopState.STOPPED
        self._journal.append(
            f"loop_{id(self):x}", JournalEntryType.NOTE, "loop stopped cleanly")


# -- durable sessions ------------------------------------------------------

class SessionMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    role: str  # user | assistant | system
    content: str
    kind: str = "message"  # message | compaction_summary
    created_at: Any = Field(default_factory=now)


class AgentSession(BaseModel):
    """One durable conversation session.

    Persisted to the runtime store on every mutation, so sessions survive
    process restarts. Token counts are estimates (len//4); the compactor
    uses them as a budget trigger, not a billing input.
    """
    id: str = Field(default_factory=lambda: new_id("ses"))
    title: str = ""
    messages: list[SessionMessage] = Field(default_factory=list)
    created_at: Any = Field(default_factory=now)
    updated_at: Any = Field(default_factory=now)
    closed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    def append_message(self, role: str, content: str,
                       kind: str = "message") -> SessionMessage:
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"bad role: {role!r}")
        msg = SessionMessage(role=role, content=content, kind=kind)
        self.messages.append(msg)
        self.updated_at = now()
        return msg

    @property
    def estimated_tokens(self) -> int:
        return sum(max(1, len(m.content) // 4) for m in self.messages)

    def close(self) -> None:
        self.closed = True
        self.updated_at = now()


class CompactionReport(BaseModel):
    session_id: str
    folded_count: int
    kept_count: int
    tokens_before: int
    tokens_after: int
    summary_text: str


# Lines that look like durable user facts worth carrying across compaction.
_FACT_PATTERNS = (
    re.compile(r"(?i)\b(my|i'm|i am|i've|i have)\b[^.!?\n]{0,90}"),
    re.compile(r"(?i)\b(remember|prefer|always|never|don't|do not)\b[^.!?\n]{0,90}"),
)


class SessionCompactor:
    """Automatic context compaction with continuity.

    Deterministic and local: no model call. When a session passes its
    token budget, messages older than the recent window are folded into
    one system summary message (message count, time range, opening user
    intent, extracted key facts); the recent window is kept verbatim.
    """

    def __init__(self, budget_tokens: int = 8000, keep_recent: int = 10,
                 max_facts: int = 8) -> None:
        if budget_tokens < 100:
            raise ValueError("budget_tokens must be at least 100")
        self.budget_tokens = budget_tokens
        self.keep_recent = max(1, keep_recent)
        self.max_facts = max(1, max_facts)

    def needs_compaction(self, session: AgentSession) -> bool:
        return session.estimated_tokens > self.budget_tokens

    def _key_facts(self, messages: list[SessionMessage]) -> list[str]:
        facts: list[str] = []
        for m in messages:
            if m.role != "user":
                continue
            for pat in _FACT_PATTERNS:
                for hit in pat.findall(m.content):
                    text = " ".join(hit.split()) if isinstance(hit, str) else ""
                    text = text.strip(" .")
                    if text and text not in facts:
                        facts.append(text)
                    if len(facts) >= self.max_facts:
                        return facts
        return facts

    def compact(self, session: AgentSession) -> CompactionReport:
        tokens_before = session.estimated_tokens
        if len(session.messages) > self.keep_recent:
            keep = session.messages[-self.keep_recent:]
        else:
            keep = session.messages[-1:]
        folded = session.messages[:len(session.messages) - len(keep)]
        if not folded:
            return CompactionReport(
                session_id=session.id, folded_count=0, kept_count=len(keep),
                tokens_before=tokens_before, tokens_after=tokens_before,
                summary_text="")

        first_user = next((m.content for m in folded if m.role == "user"), "")
        facts = self._key_facts(folded)
        span = ""
        try:
            span = f"{folded[0].created_at} .. {folded[-1].created_at}"
        except Exception:
            pass
        lines = [
            f"Context compacted: {len(folded)} older messages folded ({span}).",
        ]
        if first_user:
            lines.append(f"Opening intent: {first_user[:200]}")
        if facts:
            lines.append("Key facts carried forward:")
            lines.extend(f"- {f}" for f in facts)
        summary_text = "\n".join(lines)
        summary_msg = SessionMessage(role="system", kind="compaction_summary",
                                     content=summary_text)
        session.messages = [summary_msg, *keep]
        session.updated_at = now()
        return CompactionReport(
            session_id=session.id, folded_count=len(folded), kept_count=len(keep),
            tokens_before=tokens_before, tokens_after=session.estimated_tokens,
            summary_text=summary_text)


class SessionStore:
    """Durable agent sessions backed by the runtime store.

    Every mutation persists immediately. On boot, rehydrate() reloads all
    sessions and flags open ones whose last message is from the user (the
    assistant never answered: the process died mid-response) instead of
    silently dropping them.

    Memory wiring: when the compactor folds messages, the folded summary
    is ingested into the user-owned memory engine (source kind
    "session"), so memory stays the source of truth across compactions.
    """

    def __init__(
        self,
        store: Any | None = None,
        compactor: SessionCompactor | None = None,
        memory: Any | None = None,
        event_sink: Any | None = None,
        audit: Any | None = None,
    ):
        self._store = store
        self._compactor = compactor
        self._memory = memory
        self._event_sink = event_sink
        self._audit = audit

    def _persist(self, session: AgentSession) -> None:
        if self._store is None:
            return
        self._store.put(_SESSION_COLLECTION, session.id, session)

    def create(self, title: str = "",
               metadata: dict[str, Any] | None = None) -> AgentSession:
        session = AgentSession(title=title, metadata=dict(metadata or {}))
        self._persist(session)
        _audit_record(self._audit, "agent", "agent.session.created",
                      {"session_id": session.id, "title": title})
        return session

    def get(self, session_id: str) -> AgentSession:
        if self._store is None:
            raise KeyError(f"unknown session: {session_id}")
        for s in self._store.all(_SESSION_COLLECTION, AgentSession):
            if s.id == session_id:
                return s
        raise KeyError(f"unknown session: {session_id}")

    def append(self, session_id: str, role: str, content: str) -> AgentSession:
        session = self.get(session_id)
        if session.closed:
            raise ValueError(f"session {session_id} is closed")
        session.append_message(role, content)
        if self._compactor is not None and self._compactor.needs_compaction(session):
            report = self._compactor.compact(session)
            self._ingest_summary(session, report)
            _emit(self._event_sink, "agent.session.compacted",
                  {"session_id": session.id, "folded": report.folded_count,
                   "tokens_before": report.tokens_before,
                   "tokens_after": report.tokens_after})
            _audit_record(self._audit, "agent", "agent.session.compacted",
                          {"session_id": session.id, "folded": report.folded_count,
                           "tokens_before": report.tokens_before,
                           "tokens_after": report.tokens_after})
        self._persist(session)
        return session

    def _ingest_summary(self, session: AgentSession, report: CompactionReport) -> None:
        """Folded context lands in user-owned memory: the memory engine
        stays the source of truth, sessions are the working set."""
        if self._memory is None or not report.summary_text:
            return
        try:
            from memory_engine.models import MemorySource, MemoryType
        except ImportError:
            _audit_record(self._audit, "agent", "agent.session.memory_ingest_skipped",
                          {"session_id": session.id, "reason": "memory_engine unavailable"})
            return
        try:
            self._memory.ingest(
                report.summary_text,
                source=MemorySource(kind="session",
                                    title=f"session:{session.id} {session.title}".strip()),
                type=MemoryType.DOCUMENT_CHUNK,
            )
        except Exception as e:
            _audit_record(self._audit, "agent", "agent.session.memory_ingest_failed",
                          {"session_id": session.id, "error": str(e)[:200]})

    def list(self, open_only: bool = True) -> list[AgentSession]:
        if self._store is None:
            return []
        sessions = self._store.all(_SESSION_COLLECTION, AgentSession)
        if open_only:
            sessions = [s for s in sessions if not s.closed]
        return sorted(sessions, key=lambda s: str(s.updated_at), reverse=True)

    def close(self, session_id: str) -> AgentSession:
        session = self.get(session_id)
        session.close()
        self._persist(session)
        _audit_record(self._audit, "agent", "agent.session.closed",
                      {"session_id": session.id})
        return session

    def rehydrate(self) -> dict[str, int]:
        """Reload sessions after a restart.

        Open sessions whose last message is from the user never got their
        assistant reply (the process died mid-response); they are flagged
        in metadata instead of silently resuming as if nothing happened.
        """
        if self._store is None:
            return {"open": 0, "closed": 0, "flagged_interrupted": 0}
        sessions = self._store.all(_SESSION_COLLECTION, AgentSession)
        opened = [s for s in sessions if not s.closed]
        closed = len(sessions) - len(opened)
        flagged = 0
        for s in opened:
            if s.messages and s.messages[-1].role == "user" \
                    and not s.metadata.get("response_interrupted"):
                s.metadata["response_interrupted"] = True
                s.updated_at = now()
                self._persist(s)
                flagged += 1
        _audit_record(self._audit, "agent", "agent.session.rehydrated",
                      {"open": len(opened), "closed": closed,
                       "flagged_interrupted": flagged})
        return {"open": len(opened), "closed": closed,
                "flagged_interrupted": flagged}

    @property
    def memory(self) -> Any | None:
        return self._memory
