"""Tests for paced plans: staged delivery of multi-step proactive work.

Covers quiet_ends_at, PlanStore validation/storage/cancellation, plan
creation from an act result (plan wins over single-shot notify), the
deliver_due_plans pass (due steps delivered via notify/publish/feed,
quiet-hour deferral that stays visible, delivery after quiet ends),
and cancellation semantics.
"""

from datetime import datetime

import pytest
from agent_core import (
    AgentCore,
    PacedPlan,
    PlanStatus,
    PlanStepStatus,
    PlanStore,
    ShadowAct,
    ShadowActRunner,
    UserProfile,
    quiet_ends_at,
)


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


# -- quiet_ends_at -----------------------------------------------------


def test_quiet_ends_at_none_when_not_quiet():
    at = datetime(2026, 1, 5, 15, 0)  # noqa: DTZ001  # 3pm, outside 22:00-07:00
    assert quiet_ends_at("22:00", "07:00", at) is None


def test_quiet_ends_at_none_when_unconfigured():
    assert quiet_ends_at(None, None) is None
    assert quiet_ends_at("", "") is None


def test_quiet_ends_at_same_day_window():
    at = datetime(2026, 1, 5, 15, 0)  # noqa: DTZ001  # 3pm inside 13:00-17:00
    ends = quiet_ends_at("13:00", "17:00", at)
    assert ends == datetime(2026, 1, 5, 17, 0).timestamp()  # noqa: DTZ001


def test_quiet_ends_at_overnight_before_midnight():
    at = datetime(2026, 1, 5, 23, 30)  # noqa: DTZ001  # inside 22:00-07:00
    ends = quiet_ends_at("22:00", "07:00", at)
    assert ends == datetime(2026, 1, 6, 7, 0).timestamp()  # noqa: DTZ001


def test_quiet_ends_at_overnight_after_midnight():
    at = datetime(2026, 1, 6, 2, 0)  # noqa: DTZ001  # inside 22:00-07:00
    ends = quiet_ends_at("22:00", "07:00", at)
    assert ends == datetime(2026, 1, 6, 7, 0).timestamp()  # noqa: DTZ001  # noqa: DTZ001


# -- PlanStore ----------------------------------------------------------


def test_plan_store_create_sorts_steps_by_deliver_at():
    store = PlanStore()
    plan = store.create(
        "probe",
        [
            {"title": "later", "deliver_at": 2000.0},
            {"title": "sooner", "deliver_at": 1000.0},
        ],
    )
    assert [s.title for s in plan.steps] == ["sooner", "later"]
    assert plan.act_name == "probe"
    assert plan.status == PlanStatus.ACTIVE
    assert all(s.status == PlanStepStatus.PENDING for s in plan.steps)


def test_plan_store_create_rejects_empty():
    with pytest.raises(ValueError):
        PlanStore().create("probe", [])


def test_plan_store_create_rejects_malformed_steps():
    store = PlanStore()
    with pytest.raises(ValueError):
        store.create("probe", [{"body": "no title", "deliver_at": 1000.0}])
    with pytest.raises(ValueError):
        store.create("probe", [{"title": "x", "deliver_at": "soon"}])
    with pytest.raises(ValueError):
        store.create("probe", [{"title": "x", "deliver_at": -5}])
    with pytest.raises(TypeError):
        store.create("probe", ["not a dict"])


def test_plan_store_get_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        PlanStore().get("pln_nope")


def test_plan_store_cancel_marks_pending_steps_cancelled():
    store = PlanStore()
    plan = store.create(
        "probe",
        [
            {"title": "a", "deliver_at": 1000.0},
            {"title": "b", "deliver_at": 2000.0},
        ],
    )
    plan.steps[0].status = PlanStepStatus.DELIVERED
    cancelled = store.cancel(plan.id)
    assert cancelled.status == PlanStatus.CANCELLED
    assert cancelled.steps[0].status == PlanStepStatus.DELIVERED
    assert cancelled.steps[1].status == PlanStepStatus.CANCELLED
    # cancelling twice is idempotent
    assert store.cancel(plan.id).status == PlanStatus.CANCELLED


def test_plan_store_list_active_only():
    store = PlanStore()
    p1 = store.create("probe", [{"title": "a", "deliver_at": 1000.0}])
    p2 = store.create("probe", [{"title": "b", "deliver_at": 1000.0}])
    store.cancel(p2.id)
    assert {p.id for p in store.list()} == {p1.id, p2.id}
    assert [p.id for p in store.list(active_only=True)] == [p1.id]


def test_plan_roundtrip_to_dict():
    store = PlanStore()
    plan = store.create("probe", [{"title": "a", "body": "b", "deliver_at": 1000.0}])
    plan.steps[0].status = PlanStepStatus.DEFERRED
    plan.steps[0].deferred_from = 1000.0
    plan.steps[0].deferred_to = 2000.0
    clone = PacedPlan.from_dict(plan.to_dict())
    assert clone.id == plan.id
    assert clone.act_name == "probe"
    assert clone.steps[0].status == PlanStepStatus.DEFERRED
    assert clone.steps[0].deferred_to == 2000.0


# -- runner: plan creation ----------------------------------------------


def test_act_plan_creates_stored_plan_not_single_notify(profile):
    core = _auto_core("probe")
    notified = []
    runner = ShadowActRunner(core, profile, acts=(_plan_act(),))
    out = runner.run_one("probe", _ctx(notify=lambda t, b, d: notified.append((t, b))))
    assert notified == []
    assert out["data"]["plan_steps"] == 2
    plan_id = out["data"]["plan_id"]
    plan = runner.get_plan(plan_id)
    assert [s.title for s in plan.steps] == ["step one", "step two"]
    assert "paced plan" in out["summary"]


def test_plan_wins_over_notify_when_both_present(profile):
    core = _auto_core("probe")
    notified = []
    act = ShadowAct(
        name="probe",
        description="t",
        effect="local_notify",
        run=lambda ctx: {
            "summary": "s",
            "data": {},
            "notify": ("dump", "everything at once"),
            "plan": [{"title": "paced", "deliver_at": 1000.0}],
        },
    )
    runner = ShadowActRunner(core, profile, acts=(act,))
    out = runner.run_one("probe", _ctx(notify=lambda t, b, d: notified.append(t)))
    assert notified == []
    assert out["data"]["plan_steps"] == 1


# -- runner: deliver_due_plans -------------------------------------------


def _runner_with_plan(profile, now, **ctx_kw):
    core = _auto_core("probe")
    runner = ShadowActRunner(core, profile, acts=(_plan_act(),))
    out = runner.run_one("probe", _ctx())
    plan = runner.get_plan(out["data"]["plan_id"])
    calls = {"notify": [], "publish": [], "feed": []}
    ctx = _ctx(
        notify=lambda t, b, d: calls["notify"].append((t, b, d)),
        publish=lambda e, p: calls["publish"].append((e, p)),
        feed_add=lambda k, t, b: calls["feed"].append((k, t, b)),
        **ctx_kw,
    )
    return runner, plan, calls, ctx


def test_due_steps_delivered_not_due_held(profile):
    runner, plan, calls, ctx = _runner_with_plan(profile, now=1500.0)
    out = runner.deliver_due_plans(ctx, now=1500.0)
    assert out["data"] == {"delivered": 1, "deferred": 0}
    assert [t for t, b, d in calls["notify"]] == ["step one"]
    assert calls["publish"][0][0] == "plan_step.delivered"
    assert calls["feed"][0] == ("plan_step", "step one", "first")
    assert plan.steps[0].status == PlanStepStatus.DELIVERED
    assert plan.steps[0].delivered_at == 1500.0
    assert plan.steps[1].status == PlanStepStatus.PENDING
    assert plan.status == PlanStatus.ACTIVE


def test_plan_completes_when_all_steps_delivered(profile):
    runner, plan, calls, ctx = _runner_with_plan(profile, now=0)
    runner.deliver_due_plans(ctx, now=5000.0)
    assert all(s.status == PlanStepStatus.DELIVERED for s in plan.steps)
    assert plan.status == PlanStatus.COMPLETED
    assert len(calls["notify"]) == 2


def test_quiet_hours_defer_step_to_quiet_end(profile):
    quiet_end = 8000.0
    runner, plan, calls, ctx = _runner_with_plan(
        profile, now=1500.0, is_quiet=lambda: True, quiet_until=lambda: quiet_end
    )
    out = runner.deliver_due_plans(ctx, now=1500.0)
    assert out["data"] == {"delivered": 0, "deferred": 1}
    assert calls["notify"] == []
    step = plan.steps[0]
    assert step.status == PlanStepStatus.DEFERRED
    assert step.deferred_from == 1000.0
    assert step.deferred_to == quiet_end
    assert step.deliver_at == quiet_end  # rescheduled, still visible
    assert plan.status == PlanStatus.ACTIVE


def test_deferred_step_delivers_after_quiet_ends(profile):
    quiet_end = 8000.0
    runner, plan, calls, ctx = _runner_with_plan(
        profile, now=1500.0, is_quiet=lambda: True, quiet_until=lambda: quiet_end
    )
    runner.deliver_due_plans(ctx, now=1500.0)
    assert plan.steps[0].status == PlanStepStatus.DEFERRED
    # quiet over: the deferred step is now due at its deferred time, and
    # step two (due at 2000) is also due: both deliver.
    out = runner.deliver_due_plans(
        _ctx(
            notify=lambda t, b, d: calls["notify"].append((t, b)),
            publish=lambda e, p: None,
            feed_add=lambda k, t, b: None,
            is_quiet=lambda: False,
            quiet_until=lambda: None,
        ),
        now=quiet_end + 1,
    )
    assert out["data"]["delivered"] == 2
    assert plan.steps[0].status == PlanStepStatus.DELIVERED
    assert plan.steps[0].delivered_at == quiet_end + 1


def test_quiet_without_known_end_falls_back_to_next_tick(profile):
    runner, plan, _calls, ctx = _runner_with_plan(
        profile, now=1500.0, is_quiet=lambda: True, quiet_until=lambda: None
    )
    now = 1500.0
    runner.deliver_due_plans(ctx, now=now)
    step = plan.steps[0]
    assert step.status == PlanStepStatus.DEFERRED
    assert step.deferred_to == now + 3600


def test_cancel_plan_cancels_pending_steps(profile):
    runner, plan, _calls, ctx = _runner_with_plan(profile, now=0)
    runner.deliver_due_plans(ctx, now=1500.0)  # first step delivered
    cancelled = runner.cancel_plan(plan.id)
    assert cancelled.status == PlanStatus.CANCELLED
    assert cancelled.steps[0].status == PlanStepStatus.DELIVERED
    assert cancelled.steps[1].status == PlanStepStatus.CANCELLED
    # cancelled plans are not delivered by later ticks
    out = runner.deliver_due_plans(ctx, now=99999.0)
    assert out["data"] == {"delivered": 0, "deferred": 0}


def test_cancel_unknown_plan_raises_keyerror(profile):
    runner = ShadowActRunner(_auto_core("probe"), profile, acts=(_plan_act(),))
    with pytest.raises(KeyError):
        runner.cancel_plan("pln_nope")


def test_delivery_survives_missing_optional_channels(profile):
    # notify/publish/feed_add all absent: delivery marks steps without raising
    runner, plan, _calls, _ctx = _runner_with_plan(profile, now=0)
    bare = {"is_quiet": lambda: False, "quiet_until": lambda: None}
    out = runner.deliver_due_plans(bare, now=5000.0)
    assert out["data"]["delivered"] == 2
    assert plan.status == PlanStatus.COMPLETED


def test_plan_store_kv_persistence_roundtrip():
    from agent_core import InMemoryKV

    kv = InMemoryKV()
    store = PlanStore(kv=kv)
    plan = store.create("probe", [{"title": "a", "deliver_at": 1000.0}])
    store.cancel(plan.id)
    # a fresh store over the same KV rehydrates the plan
    store2 = PlanStore(kv=kv)
    clone = store2.get(plan.id)
    assert clone.status == PlanStatus.CANCELLED
    assert clone.steps[0].status == PlanStepStatus.CANCELLED


def test_validate_step_rejects_zero_deliver_at():
    # boundary: deliver_at == 0 is not positive
    with pytest.raises(ValueError):
        PlanStore().create("probe", [{"title": "x", "deliver_at": 0}])


def test_validate_step_rejects_non_string_body():
    with pytest.raises(ValueError):
        PlanStore().create("probe", [{"title": "x", "deliver_at": 1000.0, "body": 123}])


def test_plan_from_dict_defaults_missing_deliver_at():
    from agent_core import PacedPlan

    plan = PacedPlan.from_dict(
        {"id": "pln_x", "act_name": "probe", "steps": [{"title": "a"}]}
    )
    assert plan.steps[0].deliver_at == 0.0


def test_plan_step_deliver_at_defaults_to_zero():
    from agent_core import PlanStep

    assert PlanStep(id="stp_1", title="t").deliver_at == 0.0


def test_plan_from_dict_preserves_explicit_step_id():
    from agent_core import PacedPlan

    plan = PacedPlan.from_dict(
        {
            "id": "pln_x",
            "act_name": "probe",
            "steps": [{"id": "stp_keep", "title": "a"}],
        }
    )
    assert plan.steps[0].id == "stp_keep"


def test_plan_from_dict_defaults_missing_created_at():
    from agent_core import PacedPlan

    plan = PacedPlan.from_dict({"id": "pln_x", "act_name": "probe", "steps": []})
    assert plan.created_at == 0.0


def test_validate_step_accepts_deliver_at_of_one():
    # boundary: 1 is positive, must not raise
    plan = PlanStore().create("probe", [{"title": "x", "deliver_at": 1}])
    assert plan.steps[0].deliver_at == 1


def test_create_persists_to_kv():
    from agent_core import InMemoryKV

    kv = InMemoryKV()
    store = PlanStore(kv=kv)
    plan = store.create("probe", [{"title": "a", "deliver_at": 1000.0}])
    assert PlanStore(kv=kv).get(plan.id).steps[0].title == "a"


def test_plan_store_survives_kv_failures():
    class BrokenKV:
        def all(self, collection, model):
            raise RuntimeError("kv down")

        def put(self, collection, id, obj):
            raise RuntimeError("kv down")

    store = PlanStore(kv=BrokenKV())  # corrupt load must not break the store
    plan = store.create("probe", [{"title": "a", "deliver_at": 1000.0}])
    assert store.get(plan.id).act_name == "probe"  # persist failure is swallowed


def test_list_plans_inspection(profile):
    runner, _plan, _calls, _ctx = _runner_with_plan(profile, now=0)
    plans = runner.list_plans()
    assert len(plans) == 1
    d = plans[0].to_dict()
    assert d["act_name"] == "probe"
    assert [s["status"] for s in d["steps"]] == ["pending", "pending"]
    assert [s["deliver_at"] for s in d["steps"]] == [1000.0, 2000.0]
