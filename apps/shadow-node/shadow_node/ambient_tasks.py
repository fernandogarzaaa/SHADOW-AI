"""Built-in ambient tasks for the SHADOW node scheduler.

Contract: every task is a read-only observer. A task receives a context dict
with the node's core objects and returns {"summary": str, "data": dict}.
Tasks never change world state beyond their own journal entries; they write
no files, send no network requests, and touch no credentials. Anything that
should act on the world goes through the normal approval-gated agent path.

Available tasks:
- morning_brief: deterministic digest of pending approvals, recent execution
  verdicts, open claims, and paired devices.
- memory_digest: inventory of the local memory store by category and type,
  items nearing expiry, revoked counts. Ingest already dedupes by content
  hash, so this reports rather than merges; true consolidation is future work.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

BUILTIN_TASKS = ("morning_brief", "memory_digest")


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
    return {"morning_brief": morning_brief, "memory_digest": memory_digest}
