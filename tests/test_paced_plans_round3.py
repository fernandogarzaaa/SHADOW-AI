"""Final strengthening round for paced plans: audit events for the
decision/held/ran/error paths, notified-flag assertions, the
notify/effect gate, run_all count asymmetries, and the
active_only=True delivery filter.
"""

import pytest
from agent_core import (
    AgentCore,
    AutonomyMode,
    PlanStatus,
    PlanStepStatus,
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


def _notify_act(name="probe"):
    return ShadowAct(
        name=name,
        description="test probe",
        effect="local_notify",
        run=lambda ctx: {
            "summary": "probe ran",
            "data": {},
            "notify": ("hello", "world"),
        },
    )


def test_decision_and_ran_audit_events_recorded(profile):
    audit = RecordingAudit()
    runner = ShadowActRunner(
        _auto_core("probe"), profile, acts=(_notify_act(),), audit=audit
    )
    runner.run_one("probe", _ctx())
    assert "act.probe.decision" in audit.event_types()
    assert "act.probe.ran" in audit.event_types()


def test_held_for_approval_audit_event_recorded(profile):
    audit = RecordingAudit()
    runner = ShadowActRunner(AgentCore(), profile, acts=(_notify_act(),), audit=audit)
    out = runner.run_one("probe", _ctx())
    assert out["data"]["outcome"] == "require_approval"
    assert "act.probe.held_for_approval" in audit.event_types()


def test_run_all_error_audit_event_recorded(profile):
    audit = RecordingAudit()

    def boom(ctx):
        raise RuntimeError("act exploded")

    bad = ShadowAct(name="bad", description="t", effect="local_read", run=boom)
    runner = ShadowActRunner(_auto_core("bad"), profile, acts=(bad,), audit=audit)
    out = runner.run_all(_ctx())
    assert "error" in out["data"]["acts"]["bad"]["summary"]
    assert "act.bad.error" in audit.event_types()
    assert out["data"]["acts"]["bad"]["notified"] is False


def test_denied_act_reports_notified_false(profile):
    paused = UserProfile(
        autonomy_mode=AutonomyMode.TRUSTED_WORKFLOW, emergency_paused=True
    )
    runner = ShadowActRunner(AgentCore(), paused, acts=(_notify_act(),))
    out = runner.run_one("probe", _ctx())
    assert out["data"]["outcome"] == "deny"
    assert out["notified"] is False


def test_held_act_reports_notified_false(profile):
    runner = ShadowActRunner(AgentCore(), profile, acts=(_notify_act(),))
    out = runner.run_one("probe", _ctx())
    assert out["data"]["outcome"] == "require_approval"
    assert out["notified"] is False


def test_notified_flag_true_when_notification_sent(profile):
    notified = []
    runner = ShadowActRunner(_auto_core("probe"), profile, acts=(_notify_act(),))
    out = runner.run_one("probe", _ctx(notify=lambda t, b, d: notified.append((t, b))))
    assert notified == [("hello", "world")]
    assert out["notified"] is True


def test_execute_defaults_to_not_quiet_without_is_quiet_key(profile):
    # single-notify path: ctx without "is_quiet" must not hold the
    # notification as quiet
    notified = []
    runner = ShadowActRunner(_auto_core("probe"), profile, acts=(_notify_act(),))
    out = runner.run_one("probe", {"notify": lambda t, b, d: notified.append(t)})
    assert notified == ["hello"]
    assert out["notified"] is True
    assert "(notified)" in out["summary"]


def test_notify_ignored_when_effect_is_not_local_notify(profile):
    notified = []
    read_act = ShadowAct(
        name="probe",
        description="t",
        effect="local_read",
        run=lambda ctx: {"summary": "s", "data": {}, "notify": ("x", "y")},
    )
    runner = ShadowActRunner(_auto_core("probe"), profile, acts=(read_act,))
    out = runner.run_one("probe", _ctx(notify=lambda t, b, d: notified.append((t, b))))
    assert notified == []
    assert out["notified"] is False


def test_run_all_counts_asymmetric_outcomes(profile):
    # 2 allow + 1 held: asymmetric so != mutants change the counts
    acts = (
        _notify_act("fast1"),
        _notify_act("fast2"),
        ShadowAct(
            name="slow",
            description="t",
            effect="local_read",
            run=lambda ctx: {"summary": "s", "data": {}},
        ),
    )
    core = AgentCore(
        policy={
            "tool_tiers": {
                "shadow_act:fast1": "auto_approve",
                "shadow_act:fast2": "auto_approve",
            }
        }
    )
    runner = ShadowActRunner(core, profile, acts=acts)
    out = runner.run_all(_ctx())
    assert "2 ran, 1 held for approval, 0 denied" in out["summary"]


def test_run_all_counts_all_denied(profile):
    paused = UserProfile(
        autonomy_mode=AutonomyMode.TRUSTED_WORKFLOW, emergency_paused=True
    )
    acts = (_notify_act("a"), _notify_act("b"), _notify_act("c"))
    runner = ShadowActRunner(AgentCore(), paused, acts=acts)
    out = runner.run_all(_ctx())
    assert "0 ran, 0 held for approval, 3 denied" in out["summary"]


def test_delivery_defaults_to_not_quiet_without_is_quiet_key(profile):
    # ctx without "is_quiet": the default lambda must be False
    core = _auto_core("probe")
    plan_act = ShadowAct(
        name="probe",
        description="t",
        effect="local_notify",
        run=lambda ctx: {
            "summary": "s",
            "data": {},
            "plan": [{"title": "s1", "deliver_at": 1000.0}],
        },
    )
    runner = ShadowActRunner(core, profile, acts=(plan_act,))
    notified = []
    out = runner.run_one("probe", {"notify": lambda t, b, d: notified.append(t)})
    plan_id = out["data"]["plan_id"]
    result = runner.deliver_due_plans(
        {"notify": lambda t, b, d: notified.append(t)}, now=1500.0
    )
    assert result["data"] == {"delivered": 1, "deferred": 0}
    assert runner.get_plan(plan_id).steps[0].status == PlanStepStatus.DELIVERED


def test_cancelled_plan_keeps_cancelled_status_on_later_ticks(profile):
    # deliver_due_plans must only iterate active plans: a cancelled
    # plan must not be flipped to completed by the is_complete check
    core = _auto_core("probe")
    plan_act = ShadowAct(
        name="probe",
        description="t",
        effect="local_notify",
        run=lambda ctx: {
            "summary": "s",
            "data": {},
            "plan": [{"title": "s1", "deliver_at": 1000.0}],
        },
    )
    runner = ShadowActRunner(core, profile, acts=(plan_act,))
    out = runner.run_one("probe", _ctx())
    plan_id = out["data"]["plan_id"]
    runner.cancel_plan(plan_id)
    runner.deliver_due_plans(_ctx(), now=99999.0)
    assert runner.get_plan(plan_id).status == PlanStatus.CANCELLED
