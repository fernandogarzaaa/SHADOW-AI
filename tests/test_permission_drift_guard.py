"""Backlog #4: live permission re-check with abort on drift.

OpenDots source: src/server/dot-agent.ts (check() closure re-reading
settings + Dot row on every tool execution and setInterval 100ms, 90s
backstop, abortRun()). MIT (c) Atai Barkai. Mapped to SHADOW risk classes:
the permission triple (emergency pause, persona capability envelope,
policy document) is snapshotted at run start and re-checked before every
step of a multi-step run.
"""
import pytest

from agent_core import (
    AgentCore,
    AutonomyMode,
    GhostRunSession,
    UserProfile,
    persona_from_dict,
)
from agent_core.run_guard import PermissionDriftError, RunGuard


def trusted_core():
    core = AgentCore(profile=UserProfile(autonomy_mode=AutonomyMode.TRUSTED_WORKFLOW),
                     mock_tools=True)
    core.tools.register("probe", lambda params: {"ok": True, "n": params.get("n")})
    return core


def steps(n=2):
    return [{"tool": "probe", "description": f"step {i}", "params": {"n": i}} for i in range(n)]


# --- RunGuard unit tests -----------------------------------------------------

def test_check_passes_without_drift():
    core = trusted_core()
    guard = RunGuard(core)
    guard.check()  # no error


def test_emergency_pause_drift_aborts():
    core = trusted_core()
    guard = RunGuard(core)
    core.profile.emergency_paused = True
    with pytest.raises(PermissionDriftError) as e:
        guard.check()
    assert "emergency_paused" in e.value.drifted
    assert "all risk classes" in str(e.value)


def test_persona_research_toggle_drift_aborts():
    core = trusted_core()
    guard = RunGuard(core)
    core.persona = persona_from_dict({"name": "NoResearch", "instructions": "no research",
                                      "research_allowed": False})
    with pytest.raises(PermissionDriftError) as e:
        guard.check()
    assert "persona.research_allowed" in e.value.drifted
    assert "web.search" in str(e.value)


def test_persona_memory_toggle_drift_aborts():
    core = trusted_core()
    guard = RunGuard(core)
    core.persona = persona_from_dict({"name": "NoMem", "instructions": "no memory",
                                      "memory_allowed": False})
    with pytest.raises(PermissionDriftError) as e:
        guard.check()
    assert "persona.memory_allowed" in e.value.drifted


def test_grant_table_change_drift_aborts():
    core = trusted_core()
    guard = RunGuard(core)
    core.persona = persona_from_dict({"name": "Deny", "instructions": "deny probe",
                                      "denied_tools": ["probe"]})
    with pytest.raises(PermissionDriftError) as e:
        guard.check()
    assert "persona.denied_tools" in e.value.drifted


def test_policy_document_change_drift_aborts():
    core = trusted_core()
    guard = RunGuard(core)
    core.policy.document["blocked_tools"] = core.policy.document["blocked_tools"] + ["probe"]
    core.policy.blocked_tools.add("probe")
    with pytest.raises(PermissionDriftError) as e:
        guard.check()
    assert "policy.fingerprint" in e.value.drifted


def test_baseline_survives_round_trip():
    core = trusted_core()
    baseline = RunGuard.snapshot(core)
    guard = RunGuard(core, baseline)
    guard.check()  # baseline from persisted checkpoint works


# --- GhostRunSession integration --------------------------------------------

def test_ghost_run_aborts_on_mid_run_drift():
    core = trusted_core()
    session = GhostRunSession(core)
    run_id = session.start("drift test", steps(3))
    session.run_next(run_id)  # step 0 fine
    core.profile.emergency_paused = True  # operator hits the pause mid-run
    with pytest.raises(PermissionDriftError):
        session.run_next(run_id)
    cp = session.checkpoints.load(run_id)
    assert cp.status == "aborted"
    assert "emergency_paused" in (cp.error or "")


def test_ghost_run_completes_without_drift():
    core = trusted_core()
    session = GhostRunSession(core)
    run_id = session.start("clean test", steps(2))
    session.run_next(run_id)
    out = session.run_next(run_id)
    assert out is not None
    cp = session.checkpoints.load(run_id)
    assert cp.status == "completed"
