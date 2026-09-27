"""Adversarial tests: ghost runs must never manufacture approval.

Regression coverage for the audit P0 "Ghost runs can bypass the approval
contract": GhostRunSession.run_next() used to call
core.execute(action, approved=True), letting /ghost/runs execute arbitrary
client-supplied steps without any server-side approval. Every step must now
resolve its approval reference through the injected server-side binding,
the same contract /agent/execute enforces:

    NO VALID APPROVAL -> NO EXECUTION
"""

import pytest

from agent_core.ambient import (
    CheckpointStore,
    ClaimRegistry,
    GhostRunSession,
    RunJournal,
)
from agent_core.core import AgentAction, AgentCore
from agent_core.models import ApprovalStatus


def _make_core():
    core = AgentCore()
    calls = []

    def spy(params):
        calls.append(dict(params))
        return {"ok": True}

    core.tools.register("send_email", spy)  # sensitive tool: approval-gated
    core.tools.register("probe", spy)  # low-risk tool: policy allows
    return core, calls


def _session(core, **kw):
    return GhostRunSession(
        core,
        journal=RunJournal(),
        checkpoints=CheckpointStore(),
        claims=ClaimRegistry(),
        **kw,
    )


def _binding_resolver(core):
    """Test double with the exact semantics of the node's
    _resolve_server_approval: returns True only for an APPROVED, unexpired,
    action-matching record; raises otherwise."""

    def resolve(approval_id, action):
        req = core.approvals.requests.get(approval_id)
        if req is None:
            raise LookupError("unknown approval")
        if req.status != ApprovalStatus.APPROVED:
            raise PermissionError(f"approval is {req.status.value}, not granted")
        granted = req.action
        if (granted.tool_name, granted.params, granted.description) != (
            action.tool_name,
            action.params,
            action.description,
        ):
            raise PermissionError("approval does not match the requested action")
        return True

    return resolve


def _grant(core, tool, params, description):
    action = AgentAction(tool_name=tool, description=description, params=params)
    req = core.approvals.create(action, "test approval")
    core.approvals.decide(req.id, True)
    return req.id


def _email_step(**kw):
    step = {
        "tool": "send_email",
        "description": "send email to ops",
        "params": {"to": "ops@example.com"},
    }
    step.update(kw)
    return step


# -- the core invariant ------------------------------------------------------


def test_ghost_run_cannot_self_approve_sensitive_step():
    """Ghost run + sensitive action + no approval = blocked, tool not called."""
    core, calls = _make_core()
    sess = _session(core, approval_resolver=_binding_resolver(core))
    run_id = sess.start("notify ops", [_email_step()])
    out = sess.run_all(run_id)
    assert out["status"] == "completed"
    assert calls == [], "sensitive tool executed without any approval"
    assert out["results"][0]["ok"] is False


def test_ghost_run_with_valid_approval_executes():
    core, calls = _make_core()
    sess = _session(core, approval_resolver=_binding_resolver(core))
    approval_id = _grant(core, "send_email", {"to": "ops@example.com"}, "send email to ops")
    run_id = sess.start("notify ops", [_email_step(approval_id=approval_id)])
    out = sess.run_all(run_id)
    assert out["status"] == "completed"
    assert calls == [{"to": "ops@example.com"}]
    assert out["results"][0]["ok"] is True


def test_ghost_run_unknown_approval_raises_before_execution():
    core, calls = _make_core()
    sess = _session(core, approval_resolver=_binding_resolver(core))
    run_id = sess.start("notify ops", [_email_step(approval_id="appr_nope")])
    with pytest.raises(LookupError):
        sess.run_next(run_id)
    assert calls == []
    # checkpoint untouched: the step never executed, run is resumable
    assert sess.checkpoints.load(run_id).step_index == 0


def test_ghost_run_mismatched_approval_raises_before_execution():
    core, calls = _make_core()
    sess = _session(core, approval_resolver=_binding_resolver(core))
    # approval granted for a DIFFERENT action than the step performs
    approval_id = _grant(core, "send_email", {"to": "someone-else@example.com"}, "send email to ops")
    run_id = sess.start("notify ops", [_email_step(approval_id=approval_id)])
    with pytest.raises(PermissionError):
        sess.run_next(run_id)
    assert calls == []


def test_ghost_run_denied_approval_raises_before_execution():
    core, calls = _make_core()
    sess = _session(core, approval_resolver=_binding_resolver(core))
    action = AgentAction(tool_name="send_email", description="send email to ops",
                         params={"to": "ops@example.com"})
    req = core.approvals.create(action, "test approval")
    core.approvals.decide(req.id, False)
    run_id = sess.start("notify ops", [_email_step(approval_id=req.id)])
    with pytest.raises(PermissionError):
        sess.run_next(run_id)
    assert calls == []


def test_ghost_run_level_approval_still_binds_per_step():
    """Run-level approval_id falls back per step but still binds to the
    step's action: it authorizes a matching single-step run."""
    core, calls = _make_core()
    sess = _session(core, approval_resolver=_binding_resolver(core))
    approval_id = _grant(core, "send_email", {"to": "ops@example.com"}, "send email to ops")
    run_id = sess.start("notify ops", [_email_step()], approval_id=approval_id)
    out = sess.run_all(run_id)
    assert out["status"] == "completed"
    assert calls == [{"to": "ops@example.com"}]


def test_ghost_run_one_approval_does_not_bless_other_steps():
    """A run-level approval bound to step 1's action must not authorize
    step 2's different action: the binding check fails the run before
    step 2 executes."""
    core, calls = _make_core()
    sess = _session(core, approval_resolver=_binding_resolver(core))
    approval_id = _grant(core, "send_email", {"to": "ops@example.com"}, "send email to ops")
    steps = [
        {"tool": "send_email", "description": "send email to ops",
         "params": {"to": "ops@example.com"}},
        {"tool": "send_email", "description": "send email to attacker",
         "params": {"to": "attacker@example.com"}},
    ]
    run_id = sess.start("two notifications", steps, approval_id=approval_id)
    with pytest.raises(PermissionError):
        sess.run_all(run_id)
    assert calls == [{"to": "ops@example.com"}]


def test_ghost_run_step_approval_without_resolver_fails_closed():
    core, calls = _make_core()
    sess = _session(core)  # no resolver wired
    run_id = sess.start("notify ops", [_email_step(approval_id="appr_anything")])
    with pytest.raises(RuntimeError):
        sess.run_next(run_id)
    assert calls == []


def test_ghost_run_unapproved_step_follows_profile_policy():
    """No approval reference means the step runs under the normal policy
    gate, exactly like /agent/execute without an approval: blocked under
    the default SUGGEST_ONLY profile, allowed for low-risk tools under
    TRUSTED_WORKFLOW."""
    from agent_core import AutonomyMode, UserProfile

    core, calls = _make_core()
    sess = _session(core, approval_resolver=_binding_resolver(core))
    run_id = sess.start("probe", [{"tool": "probe", "description": "harmless check",
                                   "params": {"n": 1}}])
    out = sess.run_all(run_id)
    assert out["status"] == "completed"
    assert calls == [], "default SUGGEST_ONLY profile must block unapproved steps"
    assert out["results"][0]["ok"] is False

    trusted = AgentCore(profile=UserProfile(autonomy_mode=AutonomyMode.TRUSTED_WORKFLOW))
    trusted_calls = []
    trusted.tools.register("probe", lambda params: trusted_calls.append(params) or {"ok": True})
    sess2 = _session(trusted, approval_resolver=_binding_resolver(trusted))
    run_id2 = sess2.start("probe", [{"tool": "probe", "description": "harmless check",
                                     "params": {"n": 2}}])
    out2 = sess2.run_all(run_id2)
    assert out2["status"] == "completed"
    assert trusted_calls == [{"n": 2}]
    assert out2["results"][0]["ok"] is True
