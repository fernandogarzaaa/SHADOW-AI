"""One-shot approval consumption: a granted ONE_TIME approval authorizes
exactly one execution.

Regression coverage for the re-audit P0 "Approval is still reusable":
_resolve_server_approval() used to only CHECK (exists, APPROVED, unexpired,
tool/params/description match) and return True, so the same approval could
execute N times until expiry. Approvals are now atomically CLAIMED:
check-and-consume under a lock, transitioning ONE_TIME approvals to
CONSUMED. A second claim fails closed.

Also covers the hardened binding: the claim verifies the full
authorization envelope hash (tool, params, destination, data/model scope,
risk, destructive, requires_approval, envelope version), so a
security-relevant divergence (e.g. different destination) fails even when
tool/params/description match.
"""

import threading

import pytest

from agent_core.core import AgentAction, AgentCore
from agent_core.models import ApprovalStatus
from agent_core.security import envelope_hash


def _action(**kw):
    base = dict(tool_name="note.create", description="create note X",
                params={"title": "X"}, destination=None)
    base.update(kw)
    return AgentAction(**base)


def test_claim_consumes_one_time_approval():
    core = AgentCore()
    req = core.approvals.create(_action(), reason="test")
    core.approvals.decide(req.id, True)
    claimed = core.approvals.claim(req.id, _action())
    assert claimed.status == ApprovalStatus.CONSUMED
    assert claimed.consumed_at is not None
    with pytest.raises(ValueError, match="already been consumed"):
        core.approvals.claim(req.id, _action())


def test_replay_after_execute_is_blocked():
    """Simulates two /agent/execute calls racing on the same approval id:
    only one may win."""
    core = AgentCore()
    req = core.approvals.create(_action(), reason="test")
    core.approvals.decide(req.id, True)
    results, errors = [], []

    def attempt():
        try:
            core.approvals.claim(req.id, _action())
            results.append(True)
        except ValueError as e:
            errors.append(str(e))

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 1, f"expected exactly one winning claim, got {len(results)}"
    assert len(errors) == 7
    assert all("consumed" in e for e in errors)


def test_destination_divergence_fails_claim():
    core = AgentCore()
    granted = _action(tool_name="email.draft", destination="alice@example.com",
                      params={"to": "alice@example.com"})
    req = core.approvals.create(granted, reason="test")
    core.approvals.decide(req.id, True)
    tampered = _action(tool_name="email.draft", destination="bob@example.com",
                       params={"to": "alice@example.com"})
    with pytest.raises(ValueError, match="does not match"):
        core.approvals.claim(req.id, tampered)
    # Untouched approval is still claimable with the exact granted action.
    claimed = core.approvals.claim(req.id, granted)
    assert claimed.status == ApprovalStatus.CONSUMED


def test_risk_and_destructive_divergence_fails_claim():
    core = AgentCore()
    granted = _action()
    req = core.approvals.create(granted, reason="test")
    core.approvals.decide(req.id, True)
    escalated = _action(risk="high", destructive=True)
    with pytest.raises(ValueError, match="does not match"):
        core.approvals.claim(req.id, escalated)


def test_legacy_approval_without_binding_hash_still_verifies():
    """Approvals persisted before binding_hash existed verify by recomputing
    the envelope hash of the stored action."""
    core = AgentCore()
    req = core.approvals.create(_action(), reason="test")
    req.binding_hash = None  # simulate a pre-hardening persisted record
    core.approvals.requests[req.id] = req
    core.approvals.decide(req.id, True)
    claimed = core.approvals.claim(req.id, _action())
    assert claimed.status == ApprovalStatus.CONSUMED


def test_create_stores_binding_hash():
    core = AgentCore()
    action = _action()
    req = core.approvals.create(action, reason="test")
    assert req.binding_hash == envelope_hash(action)


def test_claim_rejects_non_approved_states():
    core = AgentCore()
    pending = core.approvals.create(_action(), reason="pending")
    with pytest.raises(ValueError, match="not granted"):
        core.approvals.claim(pending.id, _action())
    denied = core.approvals.create(_action(), reason="denied")
    core.approvals.decide(denied.id, False)
    with pytest.raises(ValueError, match="not granted"):
        core.approvals.claim(denied.id, _action())
    with pytest.raises(KeyError):
        core.approvals.claim("apr_does_not_exist", _action())


def test_policy_blocked_execute_does_not_consume():
    """A policy-blocked attempt (missing double confirmation) must not burn
    the approval; retrying with double_confirmed succeeds on the same id,
    and a further replay is then blocked."""
    core = AgentCore(mock_tools=True)
    action = _action(tool_name="delete_file", description="delete",
                     destructive=True, risk="high")
    req = core.approvals.create(action, reason="test")
    core.approvals.decide(req.id, True)
    blocked = core.execute(action, approved=True, double_confirmed=False,
                           approval_id=req.id)
    assert blocked["ok"] is False
    assert core.approvals.requests[req.id].status == ApprovalStatus.APPROVED
    ok = core.execute(action, approved=True, double_confirmed=True,
                      approval_id=req.id)
    assert ok["ok"] is True
    assert core.approvals.requests[req.id].status == ApprovalStatus.CONSUMED
    replay = core.execute(action, approved=True, double_confirmed=True,
                          approval_id=req.id)
    assert replay["ok"] is False
    assert "consumed" in replay["reason"]


def test_unknown_tool_fails_closed_by_default():
    """Unknown tools must not report success. Default (non-mock) cores
    refuse with status unknown_tool and a FAILED verification."""
    core = AgentCore()
    action = _action(tool_name="no.such.tool", description="imaginary",
                     destructive=False, risk="low")
    req = core.approvals.create(action, reason="test")
    core.approvals.decide(req.id, True)
    r = core.execute(action, approved=True, double_confirmed=True,
                     approval_id=req.id)
    assert r["ok"] is False
    assert r["result"]["status"] == "unknown_tool"
    assert r["verification"] == "failed"


def test_unknown_tool_mock_mode_is_explicit():
    """mock_executed is only reachable with explicit mock_tools=True."""
    core = AgentCore(mock_tools=True)
    action = _action(tool_name="no.such.tool", description="imaginary",
                     destructive=False, risk="low")
    req = core.approvals.create(action, reason="test")
    core.approvals.decide(req.id, True)
    r = core.execute(action, approved=True, double_confirmed=True,
                     approval_id=req.id)
    assert r["ok"] is True
    assert r["result"]["status"] == "mock_executed"
    assert r["verification"] == "uncertain"
