"""Strengthening tests for paced plans: audit-trail assertions, run_all
outcome counts, deliver_at boundary, persistence across store
instances, and active_only filtering. These target the surviving
mutants from the first testteeth pass.
"""

import pytest
from agent_core import (
    AgentCore,
    PlanStatus,
    PlanStepStatus,
    PlanStore,
    ShadowAct,
    ShadowActRunner,
    UserProfile,
)


class RecordingAudit:
    """Test double for the audit chain: records every event."""

    def __init__(self):
        self.events = []

    def record(self, actor, event_type, payload):
        self.events.append((actor, event_type, payload))

    def event_types(self):
        return [e[1] for e in self.events]


@pytest.fixture()
def profile():
    return UserProfile()


def _auto_core(act_name: str) -> AgentCore:
    return AgentCore(policy={"tool_tiers": {f"shadow_act:{act_name}": "auto_approve"}})


def _ctx(**kw):
    ctx = {
        "notify": lambda t, b, d: None,
        "publish": lambda e, p: None,
        "is_quiet": lambda: False,
        "quiet_until": lambda: None,
    }
    ctx.update(kw)
    return ctx


def _plan_act(name="probe", steps=None):
    return ShadowAct(
        name=name,
        description="test probe",
        effect="local_notify",
        run=lambda ctx: {
            "summary": "probe ran",
            "data": {},
            "plan": steps
            if steps is not None
            else [
                {"title": "step one", "body": "first", "deliver_at": 1000.0},
                {"title": "step two", "body": "second", "deliver_at": 2000.0},
            ],
        },
    )


def test_plan_creation_is_audit_recorded(profile):
    audit = RecordingAudit()
    core = _auto_core("probe")
    runner = ShadowActRunner(core, profile, acts=(_plan_act(),), audit=audit)
    out = runner.run_one("probe", _ctx())
    plan_id = out["data"]["plan_id"]
    assert "act.probe.plan_created" in audit.event_types()
    evt = next(e for e in audit.events if e[1] == "act.probe.plan_created")
    assert evt[2]["plan_id"] == plan_id
    assert evt[2]["steps"] == 2


def test_step_delivery_and_deferral_are_audit_recorded(profile):
    audit = RecordingAudit()
    core = _auto_core("probe")
    runner = ShadowActRunner(core, profile, acts=(_plan_act(),), audit=audit)
    out = runner.run_one("probe", _ctx())
    plan_id = out["data"]["plan_id"]
    # deliver first step (due), defer nothing: not quiet
    runner.deliver_due_plans(_ctx(), now=1500.0)
    delivered = [e for e in audit.events if e[1] == "plan.step_delivered"]
    assert len(delivered) == 1
    assert delivered[0][2]["plan_id"] == plan_id
    # now quiet: the second step defers
    runner.deliver_due_plans(
        _ctx(is_quiet=lambda: True, quiet_until=lambda: 9000.0), now=2500.0
    )
    deferred = [e for e in audit.events if e[1] == "plan.step_deferred"]
    assert len(deferred) == 1
    assert deferred[0][2]["deferred_to"] == 9000.0


def test_plan_cancellation_is_audit_recorded(profile):
    audit = RecordingAudit()
    core = _auto_core("probe")
    runner = ShadowActRunner(core, profile, acts=(_plan_act(),), audit=audit)
    out = runner.run_one("probe", _ctx())
    runner.cancel_plan(out["data"]["plan_id"])
    assert "plan.cancelled" in audit.event_types()


def test_run_all_counts_outcomes(profile):
    fast = _plan_act("fast")
    slow = ShadowAct(
        name="slow",
        description="held act",
        effect="local_read",
        run=lambda ctx: {"summary": "slow ran", "data": {}},
    )
    core = AgentCore(policy={"tool_tiers": {"shadow_act:fast": "auto_approve"}})
    runner = ShadowActRunner(core, profile, acts=(fast, slow))
    out = runner.run_all(_ctx())
    assert "1 ran, 1 held for approval, 0 denied" in out["summary"]
    assert out["data"]["acts"]["fast"]["data"]["outcome"] == "allow"
    assert out["data"]["acts"]["slow"]["data"]["outcome"] == "require_approval"


def test_step_due_exactly_now_is_delivered(profile):
    # boundary: deliver_at == now must deliver (not skip)
    core = _auto_core("probe")
    runner = ShadowActRunner(core, profile, acts=(_plan_act(),))
    out = runner.run_one("probe", _ctx())
    plan = runner.get_plan(out["data"]["plan_id"])
    result = runner.deliver_due_plans(_ctx(), now=1000.0)
    assert result["data"]["delivered"] == 1
    assert plan.steps[0].status == PlanStepStatus.DELIVERED


def test_delivery_persists_step_status_across_store_instances(profile):
    from agent_core import InMemoryKV

    kv = InMemoryKV()
    core = _auto_core("probe")
    runner = ShadowActRunner(
        core, profile, acts=(_plan_act(),), plan_store=PlanStore(kv=kv)
    )
    out = runner.run_one("probe", _ctx())
    plan_id = out["data"]["plan_id"]
    runner.deliver_due_plans(_ctx(), now=1500.0)
    # a fresh store over the same KV sees the delivered step
    fresh = PlanStore(kv=kv)
    assert fresh.get(plan_id).steps[0].status == PlanStepStatus.DELIVERED
    assert fresh.get(plan_id).steps[1].status == PlanStepStatus.PENDING


def test_list_plans_active_only_filters_completed(profile):
    core = _auto_core("probe")
    runner = ShadowActRunner(core, profile, acts=(_plan_act(),))
    out = runner.run_one("probe", _ctx())
    plan_id = out["data"]["plan_id"]
    assert len(runner.list_plans(active_only=True)) == 1
    runner.deliver_due_plans(_ctx(), now=5000.0)
    assert runner.get_plan(plan_id).status == PlanStatus.COMPLETED
    assert runner.list_plans(active_only=True) == []
    assert len(runner.list_plans()) == 1


def test_explicit_now_is_used_not_wall_time(profile):
    # passing now=1500 must not deliver the step due at 2000, even
    # though wall-clock time is far later
    core = _auto_core("probe")
    runner = ShadowActRunner(core, profile, acts=(_plan_act(),))
    runner.run_one("probe", _ctx())
    out = runner.deliver_due_plans(_ctx(), now=1500.0)
    assert out["data"]["delivered"] == 1
