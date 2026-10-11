"""Tests for the CodeRabbit review fixes: per-row load isolation,
plan deduplication, delivery serialization, and best-effort feed.
"""

import threading

import pytest
from agent_core import (
    AgentCore,
    PlanStepStatus,
    PlanStore,
    ShadowAct,
    ShadowActRunner,
    UserProfile,
)


class RecordingAudit:
    def __init__(self):
        self.events = []

    def record(self, actor, event_type, payload):
        self.events.append((actor, event_type, payload))

    def event_types(self):
        return [e[1] for e in self.events]


@pytest.fixture()
def profile():
    return UserProfile()


def _auto_core(*act_names: str) -> AgentCore:
    return AgentCore(
        policy={"tool_tiers": {f"shadow_act:{n}": "auto_approve" for n in act_names}}
    )


def _ctx(**kw):
    ctx = {
        "notify": lambda t, b, d: None,
        "publish": lambda e, p: None,
        "is_quiet": lambda: False,
        "quiet_until": lambda: None,
    }
    ctx.update(kw)
    return ctx


def _plan_act(name="probe"):
    return ShadowAct(
        name=name,
        description="test probe",
        effect="local_notify",
        run=lambda ctx: {
            "summary": "probe ran",
            "data": {},
            "plan": [
                {"title": "step one", "body": "first", "deliver_at": 1000.0},
                {"title": "step two", "body": "second", "deliver_at": 2000.0},
            ],
        },
    )


def test_corrupt_row_does_not_drop_later_plans():
    from agent_core import InMemoryKV

    kv = InMemoryKV()
    # seed: one valid plan, one corrupt row, one more valid plan
    kv.put(
        PlanStore.COLLECTION,
        "pln_good1",
        {
            "id": "pln_good1",
            "act_name": "probe",
            "status": "active",
            "steps": [{"id": "s1", "title": "a", "deliver_at": 1000.0}],
        },
    )
    kv.put(
        PlanStore.COLLECTION,
        "pln_bad",
        {
            "id": "pln_bad",
            "act_name": "probe",
            "status": "bogus-status",
            "steps": "not-a-list",
        },
    )
    kv.put(
        PlanStore.COLLECTION,
        "pln_good2",
        {
            "id": "pln_good2",
            "act_name": "probe",
            "status": "active",
            "steps": [{"id": "s2", "title": "b", "deliver_at": 2000.0}],
        },
    )
    store = PlanStore(kv=kv)
    assert store.get("pln_good1").steps[0].title == "a"
    assert store.get("pln_good2").steps[0].title == "b"
    assert "pln_bad" not in [p.id for p in store.list()]


def test_identical_repeated_plan_is_deduplicated(profile):
    runner = ShadowActRunner(_auto_core("probe"), profile, acts=(_plan_act(),))
    out1 = runner.run_one("probe", _ctx())
    out2 = runner.run_one("probe", _ctx())
    assert out1["data"]["plan_id"] == out2["data"]["plan_id"]
    assert len(runner.list_plans(active_only=True)) == 1


def test_different_plan_for_same_act_creates_new_plan(profile):
    runner = ShadowActRunner(_auto_core("probe"), profile, acts=(_plan_act(),))
    out1 = runner.run_one("probe", _ctx())
    # second run with different steps -> new plan
    other = ShadowAct(
        name="probe",
        description="t",
        effect="local_notify",
        run=lambda ctx: {
            "summary": "s",
            "data": {},
            "plan": [{"title": "different", "deliver_at": 3000.0}],
        },
    )
    runner2 = ShadowActRunner(
        _auto_core("probe"),
        profile,
        acts=(other,),
        plan_store=runner._plans,
    )
    out2 = runner2.run_one("probe", _ctx())
    assert out1["data"]["plan_id"] != out2["data"]["plan_id"]
    assert len(runner2.list_plans(active_only=True)) == 2


def test_delivery_is_serialized_with_lock(profile):
    runner = ShadowActRunner(_auto_core("probe"), profile, acts=(_plan_act(),))
    assert isinstance(runner._delivery_lock, type(threading.Lock()))


def test_feed_failure_does_not_block_delivery(profile):
    audit = RecordingAudit()

    def bad_feed(kind, title, body):
        raise RuntimeError("feed store down")

    runner = ShadowActRunner(
        _auto_core("probe"), profile, acts=(_plan_act(),), audit=audit
    )
    out = runner.run_one("probe", _ctx())
    plan_id = out["data"]["plan_id"]
    result = runner.deliver_due_plans(_ctx(feed_add=bad_feed), now=1500.0)
    # step still delivered, failure recorded, no duplicate on next tick
    assert result["data"] == {"delivered": 1, "deferred": 0}
    assert "plan.feed_failed" in audit.event_types()
    plan = runner.get_plan(plan_id)
    assert plan.steps[0].status == PlanStepStatus.DELIVERED
    result2 = runner.deliver_due_plans(_ctx(feed_add=bad_feed), now=1500.0)
    assert result2["data"] == {"delivered": 0, "deferred": 0}
