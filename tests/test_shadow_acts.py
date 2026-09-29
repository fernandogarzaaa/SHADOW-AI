"""Tests for Shadow Acts: policy-gated proactive actions.

Covers the full decision table through the real PolicyEngine and
ApprovalWorkflow: ALLOW runs, REQUIRE_APPROVAL files (and dedupes) an
approval request and holds the act, a granted one-time approval is
claimed exactly once, DENY refuses. No bypass is possible: the runner
only executes on ALLOW or a claimed approval.
"""
import time

import pytest

from agent_core import (
    AgentCore,
    AutonomyMode,
    InMemoryKV,
    ShadowAct,
    ShadowActRunner,
    UserProfile,
)
from agent_core.policy import PolicyOutcome


@pytest.fixture()
def core():
    return AgentCore()


@pytest.fixture()
def profile():
    # default profile: SUGGEST_ONLY, so nothing auto-runs without a grant
    return UserProfile()


def _ctx(**kw):
    ctx = {"notify": lambda t, b, d: None, "is_quiet": lambda: False}
    ctx.update(kw)
    return ctx


def test_act_held_for_approval_by_default(core, profile):
    """No tool_tiers grant: the act is held and an approval request is
    filed, not run."""
    ran = []
    act = ShadowAct(name="probe", description="test probe", effect="local_read",
                    run=lambda ctx: ran.append(1) or {"summary": "ran", "data": {}})
    runner = ShadowActRunner(core, profile, acts=(act,))
    out = runner.run_one("probe", _ctx())
    assert out["data"]["outcome"] == "require_approval"
    assert ran == []
    assert out["data"]["approval_id"]
    # second tick: no duplicate approval request
    out2 = runner.run_one("probe", _ctx())
    assert out2["data"]["approval_id"] == out["data"]["approval_id"]
    pending = [r for r in core.approvals.requests.values()
               if r.status.value == "pending"]
    assert len(pending) == 1


def test_granted_one_time_approval_runs_act_exactly_once(core, profile):
    ran = []
    act = ShadowAct(name="probe", description="test probe", effect="local_read",
                    run=lambda ctx: ran.append(1) or {"summary": "ran", "data": {}})
    runner = ShadowActRunner(core, profile, acts=(act,))
    held = runner.run_one("probe", _ctx())
    approval_id = held["data"]["approval_id"]
    core.approvals.decide(approval_id, True)
    out = runner.run_one("probe", _ctx())
    assert out["data"]["outcome"] == "allow"
    assert out["data"]["via"] == "approval_claim"
    assert ran == [1]
    # the one-time approval is consumed: next tick holds again, no free run
    out2 = runner.run_one("probe", _ctx())
    assert out2["data"]["outcome"] == "require_approval"
    assert ran == [1]


def test_tool_tier_grant_enables_autonomous_run():
    core = AgentCore(policy={"tool_tiers": {"shadow_act:probe": "auto_approve"}})
    profile = UserProfile()
    ran = []
    act = ShadowAct(name="probe", description="test probe", effect="local_read",
                    run=lambda ctx: ran.append(1) or {"summary": "ran", "data": {}})
    runner = ShadowActRunner(core, profile, acts=(act,))
    out = runner.run_one("probe", _ctx())
    assert out["data"]["outcome"] == "allow"
    assert out["data"]["via"] == "policy_allow"
    assert ran == [1]


def test_deny_never_runs_even_with_tier():
    # emergency pause is a hard gate: evaluated before tiers in decide()
    core = AgentCore()
    profile = UserProfile(autonomy_mode=AutonomyMode.TRUSTED_WORKFLOW,
                          emergency_paused=True)
    ran = []
    act = ShadowAct(name="probe", description="test probe", effect="local_read",
                    run=lambda ctx: ran.append(1) or {"summary": "ran", "data": {}})
    runner = ShadowActRunner(core, profile, acts=(act,))
    out = runner.run_one("probe", _ctx())
    assert out["data"]["outcome"] == "deny"
    assert ran == []


def test_notify_dedupe_and_quiet_hours(core):
    core = AgentCore(policy={"tool_tiers": {"shadow_act:n": "auto_approve"}})
    profile = UserProfile()
    notified = []
    act = ShadowAct(name="n", description="test notify", effect="local_notify",
                    run=lambda ctx: {"summary": "digest ready",
                                     "data": {},
                                     "notify": ("Title", "Body")})
    runner = ShadowActRunner(core, profile, acts=(act,))
    ctx = _ctx(notify=lambda t, b, d: notified.append((t, b)))
    out1 = runner.run_one("n", ctx)
    assert out1["notified"] is True and len(notified) == 1
    out2 = runner.run_one("n", ctx)
    assert out2["notified"] is False and len(notified) == 1
    assert "unchanged since last notification" in out2["summary"]
    # quiet hours: held, not sent
    runner2 = ShadowActRunner(core, profile, acts=(act,))
    qctx = _ctx(notify=lambda t, b, d: notified.append((t, b)),
                is_quiet=lambda: True)
    out3 = runner2.run_one("n", qctx)
    assert out3["notified"] is False and len(notified) == 1
    assert "quiet hours" in out3["summary"]


def test_run_all_aggregates_and_isolates_errors():
    core = AgentCore(policy={"tool_tiers": {"shadow_act:ok": "auto_approve",
                                            "shadow_act:bad": "auto_approve"}})
    profile = UserProfile()

    def boom(ctx):
        raise RuntimeError("kaput")
    acts = (
        ShadowAct(name="ok", description="fine", effect="local_read",
                  run=lambda ctx: {"summary": "ok", "data": {}}),
        ShadowAct(name="bad", description="broken", effect="local_read", run=boom),
    )
    runner = ShadowActRunner(core, profile, acts=acts)
    out = runner.run_all(_ctx())
    assert out["data"]["acts"]["ok"]["data"]["outcome"] == "allow"
    assert "error" in out["data"]["acts"]["bad"]["data"]
    assert "shadow_acts:" in out["summary"]


def test_unknown_act_fails_loud(core, profile):
    runner = ShadowActRunner(core, profile)
    with pytest.raises(KeyError):
        runner.run_one("nope", _ctx())


def test_evaluate_is_dry_run(core, profile):
    runner = ShadowActRunner(core, profile)
    d = runner.evaluate("upcoming_events_brief")
    assert d.outcome == PolicyOutcome.REQUIRE_APPROVAL
    assert len(core.approvals.requests) == 0  # nothing filed


def test_builtin_acts_run_with_grants_and_real_calendar_shape():
    from datetime import datetime, timezone

    from agent_core import GoogleCalendarWakeTrigger
    import json

    now = time.time()
    events = [{"summary": "Rust Developer Interview: Fernando",
               "calendar": "Work",
               "start": datetime.fromtimestamp(now + 3600, tz=timezone.utc).isoformat(),
               "end": ""}]

    class FakeProc:
        returncode = 0
        stdout = json.dumps({"events": events})
        stderr = ""

    trig = GoogleCalendarWakeTrigger(runner=lambda argv: FakeProc())
    trig.bind(lambda src, reason, payload: None)
    trig.poll(now)

    notified = []
    ctx = _ctx(calendar=trig,
               notify=lambda t, b, d: notified.append((t, b)))
    core = AgentCore(policy={"tool_tiers": {
        "shadow_act:upcoming_events_brief": "auto_approve",
        "shadow_act:ambient_health": "auto_approve"}})
    runner = ShadowActRunner(core, UserProfile())
    out = runner.run_all(ctx)
    brief = out["data"]["acts"]["upcoming_events_brief"]
    assert brief["notified"] is True
    assert brief["data"]["count"] == 1
    assert "Rust Developer Interview" in notified[0][1]
    health = out["data"]["acts"]["ambient_health"]
    assert health["data"]["outcome"] == "allow"
    assert health["data"]["compression_backend"] == "unknown"
    assert "loop=" in health["summary"]
