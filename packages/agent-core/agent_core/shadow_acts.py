"""Shadow Acts (v0.3): narrowly scoped proactive actions for the ambient loop.

A Shadow Act is a named, auditable unit of proactive behavior that runs
inside the ambient loop's scheduler tick. Every act goes through the
SAME policy path as every other agent action: ``core.policy.decide()``.

- ALLOW -> the act runs; the run is audit-recorded.
- REQUIRE_APPROVAL -> the runner files an approval request (deduped: one
  pending request per act) and holds the act. If the operator later
  grants it, the runner claims the one-time approval on a later tick and
  runs the act exactly once. The runner can never manufacture approval.
- DENY -> the act is skipped and the denial is audit-recorded.

Standing autonomy for an act is granted the same way as for any tool:
an explicit ``tool_tiers`` entry in the policy document, e.g.
``{"shadow_act:upcoming_events_brief": "auto_approve"}``. With no tier
configured (the default), the default SUGGEST_ONLY profile makes
decide() require approval, so acts are held, never silently auto-run.
Removing the tier revokes autonomy. Tiers can only waive the approval
requirement; the hard gates (emergency pause, blocked tools,
destructive double-confirmation) are evaluated first in decide() and
cannot be waived.

Act surface is deliberately narrow and local-only:

- upcoming_events_brief (local_notify): digest of calendar events
  starting in the next 24h, delivered through the node's own notify
  path. Notifies at most once per digest content (hash dedupe); held
  during quiet hours.
- due_reminders_digest (local_notify): reminders due in the next 24h,
  same notify-once and quiet-hours behavior.
- ambient_health (local_read): read-only report of trigger health,
  loop state, open sessions, and the active compression backend. Never
  notifies, never writes.

No paid services, no network calls, no credential access. Anything
beyond this surface goes through the normal approval-gated agent path.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from .models import AgentAction, ApprovalStatus
from .policy import PolicyDecision, PolicyOutcome

DAY = 24 * 3600


@dataclass
class ShadowAct:
    """One proactive behavior. run(ctx) returns a result dict with
    "summary" (str), "data" (dict), and optionally "notify" ((title,
    body) tuple) when effect == "local_notify"."""
    name: str
    description: str
    effect: str  # "local_notify" | "local_read"
    run: Callable[[dict], dict]


def _fmt_start(start_ts: float) -> str:
    dt = datetime.fromtimestamp(start_ts).astimezone()
    return dt.strftime("%a %-I:%M%p").replace("AM", "am").replace("PM", "pm")


def upcoming_events_brief(ctx: dict) -> dict:
    cal = ctx.get("calendar")
    if cal is None:
        return {"summary": "upcoming_events_brief: no calendar source in context",
                "data": {}, "notify": None}
    events = cal.upcoming_within(DAY)
    if not events:
        return {"summary": "upcoming_events_brief: no events in the next 24h",
                "data": {"count": 0}, "notify": None}
    lines = []
    for e in events:
        cal_name = f" ({e['calendar']})" if e.get("calendar") else ""
        loc = f" @ {e['location']}" if e.get("location") else ""
        lines.append(f"- {_fmt_start(e['start_ts'])}: {e['summary']}{cal_name}{loc}")
    body = "\n".join(lines)
    data_events = [{"summary": e["summary"], "start": e["start"],
                    "calendar": e.get("calendar", "")} for e in events]
    return {"summary": f"upcoming_events_brief: {len(events)} event(s) in the next 24h",
            "data": {"count": len(events), "events": data_events},
            "notify": (f"{len(events)} upcoming event(s)", body)}


def due_reminders_digest(ctx: dict) -> dict:
    store = ctx.get("reminders")
    if store is None:
        return {"summary": "due_reminders_digest: no reminder store in context",
                "data": {}, "notify": None}
    now = time.time()
    due = []
    for r in store.reminders.values():
        if getattr(r, "status", "") != "pending":
            continue
        try:
            due_ts = float(getattr(r, "due_at", 0) or 0)
        except (TypeError, ValueError):
            continue
        if due_ts <= now + DAY:
            due.append({"title": getattr(r, "title", ""), "due_at": due_ts})
    due.sort(key=lambda d: d["due_at"])
    if not due:
        return {"summary": "due_reminders_digest: no reminders due in the next 24h",
                "data": {"count": 0}, "notify": None}
    lines = [f"- {_fmt_start(d['due_at'])}: {d['title']}" for d in due]
    body = "\n".join(lines)
    return {"summary": f"due_reminders_digest: {len(due)} reminder(s) due in the next 24h",
            "data": {"count": len(due),
                     "reminders": [{"title": d["title"]} for d in due]},
            "notify": (f"{len(due)} reminder(s) due soon", body)}


def ambient_health(ctx: dict) -> dict:
    loop = ctx.get("ambient_loop")
    triggers = loop.trigger_statuses() if loop is not None else []
    errors = [t for t in triggers if t.get("last_error")]
    backend = ctx.get("compression_backend")
    agent_sessions = ctx.get("agent_sessions")
    try:
        open_sessions = len(agent_sessions.list()) if agent_sessions else 0
    except Exception:
        open_sessions = -1
    data = {
        "loop_state": loop.state.value if loop is not None else "unknown",
        "wake_count": loop.wake_count if loop is not None else 0,
        "triggers": triggers,
        "trigger_errors": len(errors),
        "open_sessions": open_sessions,
        "compression_backend": backend.name if backend is not None else "unknown",
    }
    summary = (f"ambient_health: loop={data['loop_state']} wakes={data['wake_count']} "
               f"sessions={open_sessions} backend={data['compression_backend']} "
               f"triggers_ok={len(triggers) - len(errors)}/{len(triggers)}")
    return {"summary": summary, "data": data, "notify": None}


SHADOW_ACTS: tuple[ShadowAct, ...] = (
    ShadowAct(
        name="upcoming_events_brief",
        description="Summarize locally cached Google Calendar events starting "
                    "in the next 24h into a digest delivered through the "
                    "node's own notification path.",
        effect="local_notify",
        run=upcoming_events_brief,
    ),
    ShadowAct(
        name="due_reminders_digest",
        description="Summarize node-local reminders due in the next 24h into "
                    "a digest delivered through the node's own notification path.",
        effect="local_notify",
        run=due_reminders_digest,
    ),
    ShadowAct(
        name="ambient_health",
        description="Report ambient loop health: trigger status, loop state, "
                    "open sessions, active compression backend. Read-only.",
        effect="local_read",
        run=ambient_health,
    ),
)


class ShadowActRunner:
    """Runs Shadow Acts through the policy gate. Constructed once by the
    node; driven by the ambient scheduler task and the manual
    POST /ambient/acts/run endpoint."""

    def __init__(self, core: Any, profile: Any,
                 acts: tuple[ShadowAct, ...] | None = None,
                 audit: Any | None = None) -> None:
        self.core = core
        self.profile = profile
        self.acts: dict[str, ShadowAct] = {a.name: a for a in (acts or SHADOW_ACTS)}
        self._audit = audit
        self._last_notify_hash: dict[str, str] = {}

    def _record(self, event_type: str, payload: dict) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record("shadow_acts", event_type, payload)
        except Exception:
            pass

    def _action_for(self, act: ShadowAct) -> AgentAction:
        return AgentAction(tool_name=f"shadow_act:{act.name}",
                           description=act.description, params={})

    def evaluate(self, name: str) -> PolicyDecision:
        """Dry-run policy evaluation for status reporting. Pure: never
        creates approvals or runs anything."""
        return self.core.policy.decide(self._action_for(self.acts[name]),
                                       self.profile)

    def _pending_approval_for(self, tool_name: str) -> Any | None:
        for req in self.core.approvals.requests.values():
            if (req.status == ApprovalStatus.PENDING
                    and req.action.tool_name == tool_name):
                return req
        return None

    def _granted_approval_for(self, tool_name: str) -> Any | None:
        for req in self.core.approvals.requests.values():
            if (req.status == ApprovalStatus.APPROVED
                    and req.action.tool_name == tool_name):
                return req
        return None

    def run_one(self, name: str, ctx: dict) -> dict:
        act = self.acts[name]  # KeyError for unknown acts: fail loud
        action = self._action_for(act)

        # One-time approval granted earlier? Claim it and run exactly once.
        granted = self._granted_approval_for(action.tool_name)
        if granted is not None:
            try:
                claimed = self.core.approvals.claim(granted.id, action)
                return self._execute(act, ctx, via="approval_claim",
                                     approval_id=claimed.id)
            except (KeyError, ValueError):
                pass  # fell through: re-evaluate below

        decision = self.core.policy.decide(action, self.profile)
        action.risk = decision.risk
        base = {"act": name, "outcome": decision.outcome.value,
                "rule_id": decision.rule_id, "risk": decision.risk.value}
        self._record(f"act.{name}.decision", base)

        if decision.outcome == PolicyOutcome.DENY:
            return {"summary": f"{name}: denied by policy ({decision.rule_id}: "
                               f"{decision.reason})",
                    "data": base, "notified": False}
        if decision.outcome == PolicyOutcome.REQUIRE_APPROVAL:
            pending = self._pending_approval_for(action.tool_name)
            if pending is None:
                pending = self.core.approvals.create(
                    action, f"Shadow act '{name}' wants to run: {decision.reason}")
            self._record(f"act.{name}.held_for_approval",
                         {**base, "approval_id": pending.id})
            return {"summary": f"{name}: held for approval ({pending.id})",
                    "data": {**base, "approval_id": pending.id},
                    "notified": False}
        return self._execute(act, ctx, via="policy_allow")

    def _execute(self, act: ShadowAct, ctx: dict, via: str,
                 approval_id: str | None = None) -> dict:
        result = act.run(ctx)
        data = dict(result.get("data", {}))
        data.update({"act": act.name, "outcome": "allow", "via": via})
        if approval_id:
            data["approval_id"] = approval_id
        notified = False
        notify = result.get("notify")
        summary = result.get("summary", "")
        if notify and act.effect == "local_notify":
            title, body = notify
            digest = hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()
            is_quiet = ctx.get("is_quiet", lambda: False)
            notify_fn = ctx.get("notify", lambda t, b, d: None)
            if is_quiet():
                summary += " (quiet hours: notification held)"
            elif self._last_notify_hash.get(act.name) == digest:
                summary += " (unchanged since last notification)"
            else:
                notify_fn(title, body, {"act": act.name})
                self._last_notify_hash[act.name] = digest
                notified = True
                summary += " (notified)"
        self._record(f"act.{act.name}.ran",
                     {"act": act.name, "via": via, "notified": notified,
                      "summary": summary})
        return {"summary": summary, "data": data, "notified": notified}

    def run_all(self, ctx: dict) -> dict:
        outcomes: dict[str, dict] = {}
        for name in self.acts:
            try:
                outcomes[name] = self.run_one(name, ctx)
            except Exception as e:  # noqa: BLE001 - one bad act holds no others
                self._record(f"act.{name}.error", {"error": str(e)})
                outcomes[name] = {"summary": f"{name}: error: {e}",
                                  "data": {"act": name, "error": str(e)},
                                  "notified": False}
        ran = sum(1 for o in outcomes.values()
                  if o["data"].get("outcome") == "allow")
        held = sum(1 for o in outcomes.values()
                   if o["data"].get("outcome") == "require_approval")
        denied = sum(1 for o in outcomes.values()
                     if o["data"].get("outcome") == "deny")
        return {"summary": f"shadow_acts: {ran} ran, {held} held for approval, "
                           f"{denied} denied",
                "data": {"acts": outcomes}}
