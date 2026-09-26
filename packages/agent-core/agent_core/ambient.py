"""Ambient GHOST capabilities for the SHADOW node.

Three durable primitives plus a user-controlled background scheduler:

- RunJournal: append-only per-run record of what was attempted, observed,
  and decided. Survives restarts via the runtime store.
- CheckpointStore / GhostRunSession: real checkpoint save/restore around
  multi-step agent runs. Each completed step is checkpointed; a new session
  can resume an interrupted run without re-executing finished steps.
- ClaimRegistry: agents register claims about world state
  ("note X exists", "service Z is up"); later observations confirm or refute
  them. Deterministic: confirm/refute are explicit calls with evidence, no
  LLM acts as judge.
- AmbientScheduler: node-side background scheduler for periodic ambient work
  (morning brief draft, memory digest). Default OFF. Nothing ambient runs
  without explicit user opt-in.

Stealth mode: the scheduler runs with surface=False. Journal entries, audit
log lines, and checkpoints are still written, but no SSE events and no push
notifications are emitted. See docs/AMBIENT.md for the exact definition.
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

from .core import AgentCore
from .models import AgentAction, new_id, now

# Runtime store collections used by this module.
_JOURNAL_COLLECTION = "ambient_journals"
_CHECKPOINT_COLLECTION = "ambient_checkpoints"
_CLAIM_COLLECTION = "ambient_claims"
_CONFIG_COLLECTION = "ambient_config"
_CONFIG_ID = "ambient_config"

# Smallest allowed ambient interval: 60 seconds. Shorter intervals would turn
# a background digest into a busy loop on a phone-paired node.
MIN_INTERVAL_SECONDS = 60


class InMemoryKV:
    """In-memory stand-in for the subset of EncryptedRuntimeStore used here.

    Used when SHADOW_RUNTIME_DB is unset (tests / ephemeral dev). Shares the
    put(collection, id, obj) / all(collection, model) interface so callers do
    not care which backend is active.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def put(self, collection: str, id: str, obj: Any) -> None:
        self._data.setdefault(collection, {})[id] = obj

    def all(self, collection: str, model: Any) -> list[Any]:
        return list(self._data.get(collection, {}).values())


class JournalEntryType(str, Enum):
    RUN_STARTED = "run_started"
    ATTEMPT = "attempt"
    OBSERVATION = "observation"
    DECISION = "decision"
    NOTE = "note"
    CHECKPOINT = "checkpoint"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    CLAIM = "claim"


class JournalEntry(BaseModel):
    id: str = Field(default_factory=lambda: new_id("jnl"))
    run_id: str
    seq: int = 0
    entry_type: JournalEntryType = JournalEntryType.NOTE
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    execution_id: str | None = None
    created_at: Any = Field(default_factory=now)


class RunCheckpoint(BaseModel):
    run_id: str
    kind: str = "ghost"  # "ghost" for agent runs, "ambient" for scheduler ticks
    objective: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)
    step_index: int = 0  # next step to execute
    status: str = "running"  # running | interrupted | completed | failed
    approval_id: str | None = None
    double_confirmed: bool = False
    error: str | None = None
    updated_at: Any = Field(default_factory=now)


class ClaimStatus(str, Enum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: new_id("clm"))
    statement: str
    status: ClaimStatus = ClaimStatus.UNCONFIRMED
    evidence: list[str] = Field(default_factory=list)
    run_id: str | None = None
    execution_ids: list[str] = Field(default_factory=list)
    created_at: Any = Field(default_factory=now)
    decided_at: Any | None = None


class AmbientConfig(BaseModel):
    enabled: bool = False
    interval_seconds: int = 3600
    stealth_mode: bool = False
    tasks: list[str] = Field(default_factory=lambda: ["morning_brief"])
    last_tick_at: Any | None = None


def _audit_record(audit: Any, actor: str, event_type: str, payload: dict) -> None:
    if audit is None:
        return
    try:
        audit.record(actor, event_type, payload)
    except Exception:
        pass  # auditing must never break ambient work


def _emit(event_sink: Any, event_type: str, properties: dict) -> None:
    if event_sink is None:
        return
    try:
        event_sink(event_type, properties)
    except Exception:
        pass  # events are best-effort; never break the run


class RunJournal:
    """Append-only per-run journal. Entries are never updated or deleted."""

    def __init__(self, store: Any | None = None, event_sink: Any | None = None):
        self._store = store if store is not None else InMemoryKV()
        self._event_sink = event_sink

    def append(
        self,
        run_id: str,
        entry_type: JournalEntryType | str,
        message: str,
        data: dict[str, Any] | None = None,
        execution_id: str | None = None,
    ) -> JournalEntry:
        if isinstance(entry_type, str):
            entry_type = JournalEntryType(entry_type)
        existing = [e for e in self._store.all(_JOURNAL_COLLECTION, JournalEntry) if e.run_id == run_id]
        entry = JournalEntry(
            run_id=run_id,
            seq=len(existing) + 1,
            entry_type=entry_type,
            message=message,
            data=data or {},
            execution_id=execution_id,
        )
        self._store.put(_JOURNAL_COLLECTION, entry.id, entry)
        return entry

    def for_run(self, run_id: str, limit: int = 500) -> list[JournalEntry]:
        entries = [e for e in self._store.all(_JOURNAL_COLLECTION, JournalEntry) if e.run_id == run_id]
        entries.sort(key=lambda e: (e.seq, str(e.created_at)))
        return entries[-max(1, limit):]

    def run_ids(self) -> list[str]:
        """Distinct run ids, most recently active first."""
        latest: dict[str, Any] = {}
        for e in self._store.all(_JOURNAL_COLLECTION, JournalEntry):
            if e.run_id not in latest or str(e.created_at) > str(latest[e.run_id]):
                latest[e.run_id] = str(e.created_at)
        return sorted(latest, key=lambda r: latest[r], reverse=True)


class CheckpointStore:
    """One replaceable checkpoint per run: the restorable resume point."""

    def __init__(self, store: Any | None = None):
        self._store = store if store is not None else InMemoryKV()

    def save(self, checkpoint: RunCheckpoint) -> None:
        checkpoint.updated_at = now()
        self._store.put(_CHECKPOINT_COLLECTION, checkpoint.run_id, checkpoint)

    def load(self, run_id: str) -> RunCheckpoint | None:
        for cp in self._store.all(_CHECKPOINT_COLLECTION, RunCheckpoint):
            if cp.run_id == run_id:
                return cp
        return None

    def all(self) -> list[RunCheckpoint]:
        cps = self._store.all(_CHECKPOINT_COLLECTION, RunCheckpoint)
        return sorted(cps, key=lambda c: str(c.updated_at), reverse=True)


class ClaimRegistry:
    """Deterministic world-state claims. Confirm/refute are explicit calls
    carrying evidence; a decided claim is final."""

    def __init__(self, store: Any | None = None):
        self._store = store if store is not None else InMemoryKV()

    def register(self, statement: str, run_id: str | None = None) -> Claim:
        claim = Claim(statement=statement, run_id=run_id)
        self._store.put(_CLAIM_COLLECTION, claim.id, claim)
        return claim

    def get(self, claim_id: str) -> Claim:
        for c in self._store.all(_CLAIM_COLLECTION, Claim):
            if c.id == claim_id:
                return c
        raise KeyError(f"unknown claim: {claim_id}")

    def _decide(self, claim_id: str, status: ClaimStatus, evidence: str) -> Claim:
        claim = self.get(claim_id)
        if claim.status != ClaimStatus.UNCONFIRMED:
            raise ValueError(f"claim {claim_id} is already {claim.status.value}; decided claims are final")
        updated = claim.model_copy(update={
            "status": status,
            "evidence": [*claim.evidence, evidence],
            "decided_at": now(),
        })
        self._store.put(_CLAIM_COLLECTION, claim.id, updated)
        return updated

    def confirm(self, claim_id: str, evidence: str) -> Claim:
        return self._decide(claim_id, ClaimStatus.CONFIRMED, evidence)

    def refute(self, claim_id: str, evidence: str) -> Claim:
        return self._decide(claim_id, ClaimStatus.REFUTED, evidence)

    def link_execution(self, claim_id: str, execution_id: str) -> Claim:
        claim = self.get(claim_id)
        if execution_id not in claim.execution_ids:
            updated = claim.model_copy(update={"execution_ids": [*claim.execution_ids, execution_id]})
            self._store.put(_CLAIM_COLLECTION, claim.id, updated)
            return updated
        return claim

    def list(self, status: ClaimStatus | str | None = None) -> list[Claim]:
        claims = self._store.all(_CLAIM_COLLECTION, Claim)
        if status is not None:
            status = ClaimStatus(status)
            claims = [c for c in claims if c.status == status]
        return sorted(claims, key=lambda c: str(c.created_at), reverse=True)

    def for_run(self, run_id: str) -> list[Claim]:
        return [c for c in self.list() if c.run_id == run_id]


class GhostRunSession:
    """Execute a multi-step plan with journaling and real checkpoints.

    Each step runs through AgentCore.execute (policy gate, evidence,
    verification verdict). After every step the checkpoint is saved, so an
    interrupted run (process death, operator stop, unexpected error) can be
    resumed by a fresh session without re-executing finished steps.

    Steps are plain dicts: {"tool": str, "description": str, "params": dict,
    "claim": optional str}. A step-level "claim" registers a world-state
    claim that the step's verification verdict then confirms or refutes.
    """

    def __init__(
        self,
        core: AgentCore,
        journal: RunJournal | None = None,
        checkpoints: CheckpointStore | None = None,
        claims: ClaimRegistry | None = None,
        event_sink: Any | None = None,
        audit: Any | None = None,
    ):
        self.core = core
        self.journal = journal if journal is not None else RunJournal()
        self.checkpoints = checkpoints if checkpoints is not None else CheckpointStore()
        self.claims = claims if claims is not None else ClaimRegistry()
        self._event_sink = event_sink
        self._audit = audit

    # -- run lifecycle ----------------------------------------------------
    def start(
        self,
        objective: str,
        steps: list[dict[str, Any]],
        approval_id: str | None = None,
        double_confirmed: bool = False,
        run_id: str | None = None,
        kind: str = "ghost",
    ) -> str:
        run_id = run_id or new_id("run")
        if not steps:
            raise ValueError("a run needs at least one step")
        cp = RunCheckpoint(
            run_id=run_id,
            kind=kind,
            objective=objective,
            steps=[dict(s) for s in steps],
            approval_id=approval_id,
            double_confirmed=double_confirmed,
        )
        self.checkpoints.save(cp)
        self.journal.append(run_id, JournalEntryType.RUN_STARTED,
                            f"run started: {objective} ({len(steps)} steps)",
                            {"kind": kind, "approval_id": approval_id})
        self.journal.append(run_id, JournalEntryType.CHECKPOINT,
                            "checkpoint saved at step 0", {"step_index": 0})
        _emit(self._event_sink, "ghost.run.started",
              {"run_id": run_id, "objective": objective, "steps": len(steps)})
        _audit_record(self._audit, "ghost", "ghost.run.started",
                      {"run_id": run_id, "objective": objective, "steps": len(steps)})
        return run_id

    def _load_running(self, run_id: str) -> RunCheckpoint:
        cp = self.checkpoints.load(run_id)
        if cp is None:
            raise KeyError(f"unknown run: {run_id}")
        return cp

    def run_next(self, run_id: str) -> dict[str, Any] | None:
        """Execute the next pending step. Returns None when the run finished."""
        cp = self._load_running(run_id)
        if cp.status == "completed":
            return None
        if cp.status not in ("running", "interrupted"):
            raise ValueError(f"run {run_id} is {cp.status}; resume it first")
        if cp.step_index >= len(cp.steps):
            return self._finish(run_id, cp, "completed", None)

        step = cp.steps[cp.step_index]
        tool = str(step.get("tool", ""))
        desc = str(step.get("description") or tool)
        params = dict(step.get("params") or {})
        claim_statement = step.get("claim")
        claim_id: str | None = None

        self.journal.append(run_id, JournalEntryType.ATTEMPT,
                            f"step {cp.step_index + 1}/{len(cp.steps)}: {tool}",
                            {"tool": tool, "description": desc})
        if claim_statement:
            claim = self.claims.register(str(claim_statement), run_id=run_id)
            claim_id = claim.id
            self.journal.append(run_id, JournalEntryType.CLAIM,
                                f"claim registered: {claim_statement}", {"claim_id": claim_id})

        try:
            action = AgentAction(tool_name=tool, description=desc, params=params)
            out = self.core.execute(action, approved=True,
                                    double_confirmed=cp.double_confirmed,
                                    approval_id=cp.approval_id)
        except Exception as e:  # unexpected: checkpoint as interrupted, re-raise
            cp.status = "interrupted"
            cp.error = f"{type(e).__name__}: {e}"
            self.checkpoints.save(cp)
            self.journal.append(run_id, JournalEntryType.INTERRUPTED,
                                f"run interrupted by error at step {cp.step_index + 1}: {e}")
            _emit(self._event_sink, "ghost.run.interrupted",
                  {"run_id": run_id, "step_index": cp.step_index, "error": str(e)[:300]})
            _audit_record(self._audit, "ghost", "ghost.run.interrupted",
                          {"run_id": run_id, "step_index": cp.step_index})
            raise

        execution_id = out.get("execution_id")
        verification = out.get("verification", "uncertain")
        step_result = {
            "tool": tool,
            "ok": bool(out.get("ok")),
            "execution_id": execution_id,
            "verification": verification,
            "verification_reason": out.get("verification_reason", ""),
        }
        self.journal.append(
            run_id, JournalEntryType.OBSERVATION,
            f"step {cp.step_index + 1} {verification}: {step_result['verification_reason'][:160]}",
            {"tool": tool, "verification": verification},
            execution_id=execution_id,
        )
        if claim_id and execution_id:
            self.claims.link_execution(claim_id, execution_id)
            if verification == "verified":
                self.claims.confirm(claim_id, f"step verification: {step_result['verification_reason'][:300]}")
                self.journal.append(run_id, JournalEntryType.CLAIM,
                                    "claim confirmed by step evidence", {"claim_id": claim_id})
            elif verification in ("failed", "conflicting"):
                self.claims.refute(claim_id, f"step verification: {step_result['verification_reason'][:300]}")
                self.journal.append(run_id, JournalEntryType.CLAIM,
                                    "claim refuted by step evidence", {"claim_id": claim_id})

        cp.results.append(step_result)
        cp.step_index += 1
        # A step that fails verification does not stop the run; the failure is
        # recorded in the journal and checkpoint, and the run continues. Only
        # an unexpected exception interrupts.
        if cp.step_index >= len(cp.steps):
            return self._finish(run_id, cp, "completed", None)
        self.checkpoints.save(cp)
        self.journal.append(run_id, JournalEntryType.CHECKPOINT,
                            f"checkpoint saved at step {cp.step_index}", {"step_index": cp.step_index})
        _emit(self._event_sink, "ghost.run.step",
              {"run_id": run_id, "step_index": cp.step_index, "tool": tool,
               "verification": verification})
        return {"status": "step_done", "run_id": run_id, "step_result": step_result,
                "remaining": len(cp.steps) - cp.step_index}

    def _finish(self, run_id: str, cp: RunCheckpoint, status: str, error: str | None) -> dict[str, Any]:
        cp.status = status
        cp.error = error
        self.checkpoints.save(cp)
        verdicts: dict[str, int] = {}
        for r in cp.results:
            verdicts[r.get("verification", "uncertain")] = verdicts.get(r.get("verification", "uncertain"), 0) + 1
        self.journal.append(run_id, JournalEntryType.COMPLETED,
                            f"run {status}: {len(cp.results)} steps, verdicts {verdicts}",
                            {"verdicts": verdicts})
        _emit(self._event_sink, "ghost.run.completed",
              {"run_id": run_id, "status": status, "verdicts": verdicts,
               "execution_ids": [r.get("execution_id") for r in cp.results]})
        _audit_record(self._audit, "ghost", "ghost.run.completed",
                      {"run_id": run_id, "status": status, "verdicts": verdicts})
        return {"status": status, "run_id": run_id, "results": cp.results, "verdicts": verdicts}

    def run_all(self, run_id: str, max_steps: int | None = None) -> dict[str, Any]:
        """Run steps until completion. max_steps caps the batch, leaving the
        checkpoint resumable; it models a process dying mid-run."""
        done = 0
        while True:
            out = self.run_next(run_id)
            if out is None:
                cp = self._load_running(run_id)
                return {"status": cp.status, "run_id": run_id, "results": cp.results}
            done += 1
            if out["status"] != "step_done":
                return out
            if max_steps is not None and done >= max_steps:
                cp = self._load_running(run_id)
                return {"status": "paused", "run_id": run_id,
                        "step_index": cp.step_index, "results": cp.results}

    def interrupt(self, run_id: str, reason: str = "operator stop") -> dict[str, Any]:
        cp = self._load_running(run_id)
        if cp.status == "completed":
            raise ValueError(f"run {run_id} already completed")
        cp.status = "interrupted"
        cp.error = reason
        self.checkpoints.save(cp)
        self.journal.append(run_id, JournalEntryType.INTERRUPTED, f"run interrupted: {reason}")
        _emit(self._event_sink, "ghost.run.interrupted",
              {"run_id": run_id, "step_index": cp.step_index, "error": reason[:300]})
        return {"status": "interrupted", "run_id": run_id, "step_index": cp.step_index}

    def resume(self, run_id: str) -> dict[str, Any]:
        """Resume an interrupted (or still-running) run from its checkpoint."""
        cp = self._load_running(run_id)
        if cp.status == "completed":
            return {"status": "already_completed", "run_id": run_id, "results": cp.results}
        if cp.status not in ("running", "interrupted"):
            raise ValueError(f"run {run_id} is {cp.status} and cannot be resumed")
        cp.status = "running"
        cp.error = None
        self.checkpoints.save(cp)
        self.journal.append(run_id, JournalEntryType.NOTE,
                            f"run resumed from checkpoint at step {cp.step_index + 1}/{len(cp.steps)}",
                            {"step_index": cp.step_index})
        _emit(self._event_sink, "ghost.run.resumed",
              {"run_id": run_id, "step_index": cp.step_index})
        _audit_record(self._audit, "ghost", "ghost.run.resumed",
                      {"run_id": run_id, "step_index": cp.step_index})
        return self.run_all(run_id)


class AmbientScheduler:
    """Background scheduler for periodic ambient work.

    The scheduler only ticks when explicitly enabled; the default config is
    disabled. Each tick creates a journaled run and executes the configured
    tasks through the node-supplied task callables. Built-in tasks are
    read-only observers: they never change world state beyond their own
    journal entries and checkpoints.
    """

    def __init__(
        self,
        store: Any | None = None,
        journal: RunJournal | None = None,
        tasks: dict[str, Callable[[dict], dict]] | None = None,
        event_sink: Any | None = None,
        audit: Any | None = None,
        context: dict | None = None,
        checkpoints: "CheckpointStore | None" = None,
    ):
        self._store = store if store is not None else InMemoryKV()
        self.journal = journal if journal is not None else RunJournal(self._store)
        self.tasks: dict[str, Callable[[dict], dict]] = dict(tasks or {})
        self._event_sink = event_sink
        self._audit = audit
        # Node-supplied context handed to every task callable (core objects).
        self._task_context: dict = dict(context or {})
        self.checkpoints = checkpoints if checkpoints is not None else CheckpointStore(self._store)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- config ----------------------------------------------------------
    def get_config(self) -> AmbientConfig:
        configs = self._store.all(_CONFIG_COLLECTION, AmbientConfig)
        return configs[0] if configs else AmbientConfig()

    def _save_config(self, cfg: AmbientConfig) -> None:
        self._store.put(_CONFIG_COLLECTION, _CONFIG_ID, cfg)

    def configure(
        self,
        enabled: bool | None = None,
        interval_seconds: int | None = None,
        stealth_mode: bool | None = None,
        tasks: list[str] | None = None,
    ) -> AmbientConfig:
        cfg = self.get_config()
        if enabled is not None:
            cfg.enabled = bool(enabled)
        if interval_seconds is not None:
            if interval_seconds < MIN_INTERVAL_SECONDS:
                raise ValueError(f"interval must be at least {MIN_INTERVAL_SECONDS} seconds")
            cfg.interval_seconds = int(interval_seconds)
        if stealth_mode is not None:
            cfg.stealth_mode = bool(stealth_mode)
        if tasks is not None:
            cfg.tasks = [str(t) for t in tasks]
        self._save_config(cfg)
        _audit_record(self._audit, "user", "ambient.config.changed",
                      {"enabled": cfg.enabled, "interval_seconds": cfg.interval_seconds,
                       "stealth_mode": cfg.stealth_mode, "tasks": cfg.tasks})
        _emit(self._event_sink, "ambient.config.changed",
              {"enabled": cfg.enabled, "stealth_mode": cfg.stealth_mode,
               "interval_seconds": cfg.interval_seconds})
        return cfg

    # -- ticking ----------------------------------------------------------
    def _due(self, cfg: AmbientConfig, at: float) -> bool:
        if cfg.last_tick_at is None:
            return True
        try:
            last = cfg.last_tick_at.timestamp()
        except AttributeError:
            last = float(cfg.last_tick_at)
        return (at - last) >= cfg.interval_seconds

    def tick(self, at: float | None = None, context: dict | None = None) -> dict[str, Any]:
        """Run one scheduler iteration. Returns what happened; never raises."""
        at = time.time() if at is None else at
        cfg = self.get_config()
        if not cfg.enabled:
            return {"ran": False, "reason": "ambient_disabled"}
        if not self._due(cfg, at):
            return {"ran": False, "reason": "not_due"}
        run_id = new_id("amb")
        self.journal.append(run_id, JournalEntryType.RUN_STARTED,
                            f"ambient tick: tasks={cfg.tasks} stealth={cfg.stealth_mode}",
                            {"kind": "ambient", "tasks": cfg.tasks, "stealth_mode": cfg.stealth_mode})
        results: dict[str, Any] = {}
        ctx = dict(self._task_context)
        ctx.update(context or {})
        ctx.update({"journal": self.journal, "run_id": run_id})
        for name in cfg.tasks:
            fn = self.tasks.get(name)
            if fn is None:
                self.journal.append(run_id, JournalEntryType.NOTE,
                                    f"unknown ambient task skipped: {name}")
                results[name] = {"ok": False, "error": "unknown_task"}
                continue
            self.journal.append(run_id, JournalEntryType.ATTEMPT, f"ambient task: {name}")
            try:
                out = fn(ctx) or {}
                summary = str(out.get("summary", "done"))
                self.journal.append(run_id, JournalEntryType.OBSERVATION,
                                    f"task {name}: {summary[:200]}", {"task": name})
                results[name] = {"ok": True, "summary": summary, "data": out.get("data", {})}
                if not cfg.stealth_mode:
                    _emit(self._event_sink, "ambient.task.completed",
                          {"run_id": run_id, "task": name, "summary": summary[:200]})
            except Exception as e:
                self.journal.append(run_id, JournalEntryType.DECISION,
                                    f"task {name} failed: {e}", {"task": name, "error": str(e)[:300]})
                results[name] = {"ok": False, "error": str(e)[:300]}
        cfg.last_tick_at = now()
        self._save_config(cfg)
        self.journal.append(run_id, JournalEntryType.COMPLETED,
                            f"ambient tick done: {len(results)} tasks", {"results": list(results)})
        self.checkpoints.save(RunCheckpoint(
            run_id=run_id, kind="ambient",
            objective=f"ambient tick: {', '.join(cfg.tasks)}",
            steps=[{"task": t} for t in cfg.tasks],
            results=[{"task": t, **r} for t, r in results.items()],
            step_index=len(results), status="completed",
        ))
        if not cfg.stealth_mode:
            _emit(self._event_sink, "ambient.tick",
                  {"run_id": run_id, "tasks": cfg.tasks,
                   "summaries": {k: v.get("summary", "") for k, v in results.items()}})
        _audit_record(self._audit, "ambient", "ambient.tick",
                      {"run_id": run_id, "tasks": cfg.tasks, "stealth_mode": cfg.stealth_mode})
        return {"ran": True, "run_id": run_id, "stealth_mode": cfg.stealth_mode, "results": results}

    # -- background thread -------------------------------------------------
    def start_background(self, poll_seconds: int = 30) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.wait(poll_seconds):
                try:
                    self.tick()
                except Exception:
                    continue  # the scheduler never takes the node down

        self._thread = threading.Thread(target=_loop, name="ambient-scheduler", daemon=True)
        self._thread.start()

    def stop_background(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5)

    @property
    def background_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
