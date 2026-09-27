"""Built-in ambient tasks for the SHADOW node scheduler.

Contract: every task is a read-only observer. A task receives a context dict
with the node's core objects and returns {"summary": str, "data": dict}.
Tasks never change world state beyond their own journal entries; they write
no files, send no network requests, and touch no credentials. Anything that
should act on the world goes through the normal approval-gated agent path.

The exceptions are feed_digest (appends rendered units to the node's own
feed journal) and reminder_check (fires due reminders: marks them, advances
recurrence, sends pushes). Both touch only the node's own stores and its
notification path; neither reads credentials nor reaches the network beyond
the configured push service.

Available tasks:
- morning_brief: deterministic digest of pending approvals, recent execution
  verdicts, open claims, and paired devices.
- memory_digest: inventory of the local memory store by category and type,
  items nearing expiry, revoked counts. Ingest already dedupes by content
  hash, so this reports rather than merges; true consolidation is future work.
- feed_digest: renders editorial feed units (morning brief, goals briefing,
  memory digest) into the feed store, at most one unit per kind per ~20h.
- reminder_check: fires due reminders through the node's notify/publish/feed
  path. During quiet hours nothing fires; due reminders wait for the next
  check after quiet hours end.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

BUILTIN_TASKS = ("morning_brief", "memory_digest", "feed_digest", "reminder_check")


def _as_dict(item):
    return item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)


def morning_brief(ctx: dict) -> dict:
    core = ctx.get("core")
    claims = ctx.get("claims")
    sessions = ctx.get("sessions")

    pending = []
    if core is not None:
        for req in core.approvals.requests.values():
            if req.status.value == "pending":
                pending.append({
                    "id": req.id,
                    "preview": req.action_preview or req.action.description,
                    "risk": req.risk_label.value,
                })
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        verdicts: dict[str, int] = {}
        recent = 0
        for rec in core.executions.values():
            started = rec.started_at
            if isinstance(started, str):
                try:
                    started = datetime.fromisoformat(started)
                except ValueError:
                    continue
            if started and started >= cutoff:
                recent += 1
                verdicts[rec.verification.value] = verdicts.get(rec.verification.value, 0) + 1
    else:
        verdicts, recent = {}, 0

    open_claims = []
    if claims is not None:
        for c in claims.list(status="unconfirmed"):
            open_claims.append({"id": c.id, "statement": c.statement})

    devices = 0
    if sessions is not None:
        devices = len([d for d in sessions.devices.values() if not d.revoked])

    data = {
        "pending_approvals": pending,
        "pending_approval_count": len(pending),
        "recent_executions_24h": recent,
        "verdicts_24h": verdicts,
        "unconfirmed_claims": open_claims,
        "paired_devices": devices,
    }
    summary = (
        f"{len(pending)} approvals pending, {recent} executions in 24h "
        f"({verdicts}), {len(open_claims)} unconfirmed claims, {devices} devices"
    )
    return {"summary": summary, "data": data}


def memory_digest(ctx: dict) -> dict:
    memory = ctx.get("memory")
    items = []
    if memory is not None:
        try:
            items = [_as_dict(i) for i in memory.export(include_sensitive=False)]
        except Exception:
            items = []

    by_category: dict[str, int] = {}
    by_type: dict[str, int] = {}
    expiring_soon = 0
    now = datetime.now(timezone.utc)
    for it in items:
        by_category[str(it.get("category", "?"))] = by_category.get(str(it.get("category", "?")), 0) + 1
        by_type[str(it.get("type", "?"))] = by_type.get(str(it.get("type", "?")), 0) + 1
        exp = it.get("expires_at")
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp) if isinstance(exp, str) else exp
                if now < exp_dt < now + timedelta(days=7):
                    expiring_soon += 1
            except (ValueError, TypeError):
                pass

    data = {
        "total_items": len(items),
        "by_category": by_category,
        "by_type": by_type,
        "expiring_within_7_days": expiring_soon,
        "notes": "ingest dedupes by content hash; nothing to merge",
    }
    summary = f"{len(items)} memory items across {len(by_category)} categories, {expiring_soon} expiring soon"
    return {"summary": summary, "data": data}


def build_task_map() -> dict:
    return {"morning_brief": morning_brief, "memory_digest": memory_digest,
            "feed_digest": feed_digest, "reminder_check": reminder_check}


def feed_digest(ctx: dict) -> dict:
    """Render editorial feed units into the node's feed journal.

    The feed store arrives via the scheduler context ("feed_store"); the
    goals store via "goals". This is the documented exception to the
    read-only task contract: the only world-state change is an append to the
    node's own feed journal.
    """
    from .feed import FEED_KINDS, DIGEST_KINDS, generate_units, render_goals_briefing, render_memory_digest, render_morning_brief

    feed_store = ctx.get("feed_store")
    if feed_store is None:
        return {"summary": "feed_digest: no feed store in context", "data": {}}
    goal_store = ctx.get("goals")

    renderers = {
        "morning_brief": lambda: render_morning_brief(morning_brief(ctx)["data"]),
        "goals_briefing": (
            lambda: render_goals_briefing(goal_store.briefing())
            if goal_store is not None else ("Goals briefing", "No goals tracked yet.")
        ),
        "memory_digest": lambda: render_memory_digest(memory_digest(ctx)["data"]),
    }
    units = generate_units(feed_store, list(DIGEST_KINDS), renderers)
    kinds = [u.kind for u in units]
    return {
        "summary": f"feed_digest: generated {len(units)} units ({', '.join(kinds) or 'none due'})",
        "data": {"units": [{"id": u.id, "kind": u.kind, "title": u.title} for u in units]},
    }



def reminder_check(ctx: dict) -> dict:
    """Fire due reminders through the node's notify/publish/feed path.

    The reminder store, quiet-hours gate, notifier, event publisher, and feed
    store arrive via the scheduler context. This is the documented exception
    to the read-only task contract: firing is the proactive behavior.
    """
    import time as _time

    from .reminders import fire_due

    store = ctx.get("reminders")
    feed_store = ctx.get("feed_store")
    if store is None or feed_store is None:
        return {"summary": "reminder_check: missing reminders or feed store in context", "data": {}}
    is_quiet = ctx.get("is_quiet", lambda: False)
    notify = ctx.get("notify", lambda title, body, data: None)
    publish = ctx.get("publish", lambda event_type, payload: None)
    now = _time.time()
    if is_quiet():
        due = store.due(now)
        return {"summary": f"reminder_check: quiet hours, {len(due)} due reminders held",
                "data": {"held": len(due)}}
    fired = fire_due(store, now, is_quiet, notify, publish, feed_store)
    return {
        "summary": f"reminder_check: fired {len(fired)} reminders",
        "data": {"fired": [{"id": r.id, "title": r.title} for r in fired]},
    }
