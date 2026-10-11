"""Paced plans: staged delivery for proactive multi-step work.

A paced plan is created when a Shadow Act's run() returns a "plan": a
list of steps, each with its own deliver_at time. Instead of dumping
everything in one notification, the ShadowActRunner delivers each step
at its relevant moment through the existing notify/publish/feed path.

Quiet hours are respected per step: a step whose deliver_at falls
inside quiet hours is deferred to the end of quiet hours. The deferral
is recorded on the step (deferred_from/deferred_to) so it is visible in
the plan state; steps are never dropped silently.

Plans are inspectable (steps, scheduled times, delivery status) and
cancellable: cancelling a plan cancels its pending steps. Delivered
steps are never un-delivered.

No new external dependencies. Delivery reuses the node's existing
notify/publish/feed callables from the scheduler context.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import new_id


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


class PlanStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class PlanStep:
    """One timed touchpoint. deliver_at is epoch seconds, node-local time."""

    id: str = field(default_factory=lambda: new_id("stp"))
    title: str = ""
    body: str = ""
    deliver_at: float = 0.0
    status: PlanStepStatus = PlanStepStatus.PENDING
    delivered_at: float | None = None
    deferred_from: float | None = None
    deferred_to: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "deliver_at": self.deliver_at,
            "status": self.status.value,
            "delivered_at": self.delivered_at,
            "deferred_from": self.deferred_from,
            "deferred_to": self.deferred_to,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlanStep:
        return cls(
            id=str(d.get("id") or new_id("stp")),
            title=str(d.get("title", "")),
            body=str(d.get("body", "")),
            deliver_at=float(d.get("deliver_at", 0.0)),
            status=PlanStepStatus(str(d.get("status", "pending"))),
            delivered_at=d.get("delivered_at"),
            deferred_from=d.get("deferred_from"),
            deferred_to=d.get("deferred_to"),
        )


@dataclass
class PacedPlan:
    """A stored multi-step delivery plan owned by one shadow act."""

    id: str = field(default_factory=lambda: new_id("pln"))
    act_name: str = ""
    created_at: float = field(default_factory=time.time)
    steps: list[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.ACTIVE

    def pending_steps(self) -> list[PlanStep]:
        return [
            s
            for s in self.steps
            if s.status in (PlanStepStatus.PENDING, PlanStepStatus.DEFERRED)
        ]

    def is_complete(self) -> bool:
        return all(
            s.status in (PlanStepStatus.DELIVERED, PlanStepStatus.CANCELLED)
            for s in self.steps
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "act_name": self.act_name,
            "created_at": self.created_at,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PacedPlan:
        return cls(
            id=str(d.get("id") or new_id("pln")),
            act_name=str(d.get("act_name", "")),
            created_at=float(d.get("created_at", 0.0)),
            status=PlanStatus(str(d.get("status", "active"))),
            steps=[PlanStep.from_dict(s) for s in d.get("steps", [])],
        )


def _validate_step(raw: Any, index: int) -> PlanStep:
    """Validate one raw step dict from an act's plan. Fail loud: a
    malformed plan is a programming error in the act, not user input."""
    if not isinstance(raw, dict):
        raise TypeError(f"plan step {index}: must be a dict, got {type(raw).__name__}")
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"plan step {index}: 'title' must be a non-empty string")
    try:
        deliver_at = float(raw.get("deliver_at"))
    except (TypeError, ValueError):
        raise ValueError(
            f"plan step {index}: 'deliver_at' must be epoch seconds"
        ) from None
    if deliver_at <= 0:
        raise ValueError(
            f"plan step {index}: 'deliver_at' must be positive epoch seconds"
        )
    body = raw.get("body", "")
    if body is not None and not isinstance(body, str):
        raise ValueError(f"plan step {index}: 'body' must be a string")
    return PlanStep(title=title.strip(), body=body or "", deliver_at=deliver_at)


class PlanStore:
    """Stores paced plans. In-memory by default; pass a KV store
    (put(collection, id, obj) / all(collection, model)) for durability
    across restarts, e.g. the ambient scheduler's runtime store."""

    COLLECTION = "paced_plans"

    def __init__(self, kv: Any | None = None) -> None:
        self._kv = kv
        self._plans: dict[str, PacedPlan] = {}
        if kv is not None:
            try:
                rows = kv.all(self.COLLECTION, dict)
            except Exception:  # noqa: BLE001
                # Collection unreadable: start empty, memory is source of truth.
                rows = []
            for raw in rows:
                try:
                    plan = (
                        raw if isinstance(raw, PacedPlan) else PacedPlan.from_dict(raw)
                    )
                except Exception:  # noqa: BLE001, S112
                    # One corrupt row must not drop the rest of the collection.
                    continue
                self._plans[plan.id] = plan

    def _persist(self, plan: PacedPlan) -> None:
        if self._kv is None:
            return
        try:
            self._kv.put(self.COLLECTION, plan.id, plan.to_dict())
        except Exception:  # noqa: BLE001, S110
            # Persistence is best-effort; memory is the source of truth.
            pass

    def create(
        self, act_name: str, raw_steps: list[Any], now: float | None = None
    ) -> PacedPlan:
        if not raw_steps:
            raise ValueError("cannot create a plan with no steps")
        steps = [_validate_step(raw, i) for i, raw in enumerate(raw_steps)]
        steps.sort(key=lambda s: s.deliver_at)
        plan = PacedPlan(act_name=act_name, created_at=now or time.time(), steps=steps)
        self._plans[plan.id] = plan
        self._persist(plan)
        return plan

    def get(self, plan_id: str) -> PacedPlan:
        return self._plans[plan_id]  # KeyError for unknown ids: fail loud

    def list(self, active_only: bool = False) -> list[PacedPlan]:
        plans = sorted(self._plans.values(), key=lambda p: p.created_at)
        if active_only:
            plans = [p for p in plans if p.status == PlanStatus.ACTIVE]
        return plans

    def save(self, plan: PacedPlan) -> None:
        self._plans[plan.id] = plan
        self._persist(plan)

    def cancel(self, plan_id: str) -> PacedPlan:
        """Cancel a plan: pending and deferred steps become cancelled.
        Delivered steps stay delivered. Returns the plan."""
        plan = self.get(plan_id)
        if plan.status == PlanStatus.CANCELLED:
            return plan
        for step in plan.pending_steps():
            step.status = PlanStepStatus.CANCELLED
        plan.status = PlanStatus.CANCELLED
        self._persist(plan)
        return plan
