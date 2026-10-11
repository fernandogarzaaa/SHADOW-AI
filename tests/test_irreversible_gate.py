"""Tests for the Sentinel irreversible-action gate (Hark backlog item 12).

The gate's contract:
  1. One source of truth: PolicyEngine.irreversible_class() classifies every
     action as destructive / external_send / publish / financial / None.
  2. No irreversible action is ever ALLOWed without a recorded explicit
     approval: no tier, autonomy mode, or persona can waive the gate.
  3. external_send and financial (plus destructive, as before) require
     double confirmation.
  4. The approval card names the concrete consequence, never a bare
     "Are you sure?".
  5. Approving an irreversible action is audit-logged with its consequence.
"""

import pytest
from agent_core import (
    AgentAction,
    AgentCore,
    ApprovalWorkflow,
    AutonomyMode,
    PolicyEngine,
    PolicyOutcome,
    RiskClass,
    UserProfile,
)


def _action(tool, description="do the thing", **kw):
    return AgentAction(tool_name=tool, description=description, params={}, **kw)


def _profile(**kw):
    return UserProfile(**kw)


# -- classification: the single source of truth -------------------------------


def test_destructive_tools_are_irreversible():
    e = PolicyEngine()
    for tool in ("delete_file", "overwrite_file", "shell_rm"):
        assert e.irreversible_class(_action(tool)) == "destructive"
        assert e.is_irreversible(_action(tool))


def test_external_sends_are_irreversible():
    e = PolicyEngine()
    for tool in ("send_email", "send_message"):
        assert e.irreversible_class(_action(tool)) == "external_send"


def test_reversible_tools_are_not_irreversible():
    e = PolicyEngine()
    assert e.irreversible_class(_action("answer_question")) is None
    assert e.irreversible_class(_action("note.create")) is None
    assert not e.is_irreversible(_action("web.search"))


def test_client_destructive_flag_widens_classification():
    # A client-marked destructive action on an unlisted tool is still
    # classified destructive: the flag can widen, never narrow.
    e = PolicyEngine()
    assert (
        e.irreversible_class(_action("mystery_tool", destructive=True)) == "destructive"
    )


def test_operator_can_add_publish_and_financial_tools():
    e = PolicyEngine(
        policy={
            "irreversible_tools": {
                "publish_post": "publish",
                "pay_invoice": "financial",
            }
        }
    )
    assert e.irreversible_class(_action("publish_post")) == "publish"
    assert e.irreversible_class(_action("pay_invoice")) == "financial"
    assert e.classify_action(_action("pay_invoice")) == RiskClass.HIGH


def test_unknown_irreversible_class_is_hard_error():
    with pytest.raises(ValueError, match="unknown irreversible class"):
        PolicyEngine(policy={"irreversible_tools": {"x": "bogus"}})


def test_irreversible_tools_are_high_risk():
    e = PolicyEngine()
    assert e.classify_action(_action("send_email")) == RiskClass.HIGH
    assert e.classify_action(_action("delete_file")) == RiskClass.HIGH


# -- consequence text ----------------------------------------------------------


def test_consequence_names_destination_for_external_send():
    e = PolicyEngine()
    c = e.consequence_for(_action("send_email", destination="ops@example.com"))
    assert "ops@example.com" in c
    assert "cannot be recalled" in c


def test_consequence_for_destructive_is_permanent():
    e = PolicyEngine()
    c = e.consequence_for(_action("delete_file"))
    assert "cannot be undone" in c


def test_consequence_none_for_reversible_action():
    assert PolicyEngine().consequence_for(_action("answer_question")) is None


def test_consequence_has_no_em_dashes():
    e = PolicyEngine()
    for tool in ("delete_file", "send_email"):
        c = e.consequence_for(_action(tool, destination="x"))
        assert "\u2014" not in c and "\u2013" not in c


# -- double confirmation --------------------------------------------------------


def test_double_confirm_classes():
    e = PolicyEngine()
    assert e.requires_double_confirmation(_action("delete_file"))
    assert e.requires_double_confirmation(_action("send_email"))
    assert e.requires_double_confirmation(_action("send_message"))
    assert not e.requires_double_confirmation(_action("answer_question"))
    assert not e.requires_double_confirmation(_action("note.create"))


def test_external_send_without_double_confirm_is_denied():
    e = PolicyEngine()
    d = e.decide(_action("send_email"), _profile())
    assert d.outcome == PolicyOutcome.DENY
    assert d.rule_id == "irreversible_needs_double_confirm"
    assert "double confirmation" in d.reason


def test_external_send_denied_even_when_approved_without_double_confirm():
    # approved=True alone is not enough: the second confirmation is mandatory.
    e = PolicyEngine()
    d = e.decide(_action("send_email"), _profile(), approved=True)
    assert d.outcome == PolicyOutcome.DENY
    assert d.rule_id == "irreversible_needs_double_confirm"


def test_external_send_allowed_after_approval_and_double_confirm():
    e = PolicyEngine()
    d = e.decide(
        _action("send_email"), _profile(), approved=True, double_confirmed=True
    )
    assert d.outcome == PolicyOutcome.ALLOW


# -- the gate cannot be waived ---------------------------------------------------


def test_irreversible_needs_approval_even_in_trusted_workflow():
    e = PolicyEngine()
    profile = _profile(autonomy_mode=AutonomyMode.TRUSTED_WORKFLOW)
    d = e.decide(_action("send_email"), profile, double_confirmed=True)
    assert d.outcome == PolicyOutcome.REQUIRE_APPROVAL
    assert d.rule_id == "irreversible_needs_approval"


def test_irreversible_needs_approval_reason_names_consequence():
    e = PolicyEngine()
    d = e.decide(
        _action("send_email", destination="ops@example.com"),
        _profile(),
        double_confirmed=True,
    )
    assert d.outcome == PolicyOutcome.REQUIRE_APPROVAL
    assert "ops@example.com" in d.reason
    assert "cannot be recalled" in d.reason


def test_no_tier_waives_irreversible_gate():
    # Explicit policy dicts replace defaults (no merging), so the test
    # policy carries its own irreversible mapping. The auto_approve tier
    # would waive a routine tool, but the Sentinel gate fires first.
    policy = {
        "irreversible_tools": {"send_email": "external_send"},
        "tool_tiers": {"send_email": "auto_approve"},
    }
    e = PolicyEngine(policy=policy)
    d = e.decide(_action("send_email"), _profile(), double_confirmed=True)
    assert d.outcome == PolicyOutcome.REQUIRE_APPROVAL
    assert d.rule_id == "irreversible_needs_approval"


def test_destructive_still_needs_double_confirm_first():
    e = PolicyEngine()
    d = e.decide(_action("delete_file"), _profile())
    assert d.outcome == PolicyOutcome.DENY
    assert d.rule_id == "destructive_needs_double_confirm"
    d2 = e.decide(_action("delete_file"), _profile(), double_confirmed=True)
    assert d2.outcome == PolicyOutcome.REQUIRE_APPROVAL
    assert d2.rule_id == "irreversible_needs_approval"


# -- approval card carries the consequence ---------------------------------------


def test_card_carries_consequence_and_double_confirm():
    core = AgentCore(mock_tools=True)
    req = core.approvals.create(
        _action("send_email", description="Send report", destination="ops@example.com"),
        "test",
    )
    card = req.card
    assert card["requires_double_confirmation"] is True
    assert card["consequence"] is not None
    assert "ops@example.com" in card["consequence"]
    assert "cannot be recalled" in card["consequence"]


def test_card_consequence_none_for_reversible_action():
    core = AgentCore(mock_tools=True)
    req = core.approvals.create(_action("answer_question", description="hi"), "test")
    assert req.card["consequence"] is None
    assert req.card["requires_double_confirmation"] is False


def test_card_double_confirm_derived_server_side():
    # P0-4 analog for double confirmation: the client claims
    # destructive=false on a destructive tool, but the card still demands
    # double confirmation.
    wf = ApprovalWorkflow(policy=PolicyEngine())
    req = wf.create(_action("delete_file", destructive=False), "test")
    assert req.card["requires_double_confirmation"] is True
    assert "cannot be undone" in req.card["consequence"]


# -- audit log on irreversible confirmation ---------------------------------------


def test_irreversible_approval_is_audit_logged():
    events = []

    class Chain:
        def record(self, actor, event_type, payload):
            events.append((actor, event_type, payload))

    core = AgentCore(mock_tools=True, audit_chain=Chain())
    req = core.approvals.create(
        _action("send_email", description="Send report", destination="ops@example.com"),
        "test",
    )
    core.approvals.decide(req.id, True)
    kinds = [e[1] for e in events]
    assert "approval.irreversible_confirmed" in kinds
    rec = next(e for e in events if e[1] == "approval.irreversible_confirmed")
    assert rec[2]["tool_name"] == "send_email"
    assert rec[2]["irreversible_class"] == "external_send"
    assert "ops@example.com" in rec[2]["consequence"]


def test_reversible_approval_has_no_irreversible_record():
    events = []

    class Chain:
        def record(self, actor, event_type, payload):
            events.append((actor, event_type, payload))

    core = AgentCore(mock_tools=True, audit_chain=Chain())
    req = core.approvals.create(_action("answer_question", description="hi"), "test")
    core.approvals.decide(req.id, True)
    assert "approval.irreversible_confirmed" not in [e[1] for e in events]


# -- adversarial: no execution without a recorded approval --------------------------


def test_execute_blocks_irreversible_without_approval():
    core = AgentCore(mock_tools=True)
    calls = []
    core.tools.register(
        "send_email", lambda params: calls.append(params) or {"ok": True}
    )
    action = _action(
        "send_email", description="exfiltrate", destination="evil@example.com"
    )
    # Attempt 1: no approval, no double confirm -> denied, tool not called.
    out = core.execute(action)
    assert out["ok"] is False
    assert calls == []
    # Attempt 2: double-confirmed but still no approval -> suspended, not run.
    out = core.execute(action, double_confirmed=True)
    assert out["ok"] is False
    assert out["status"] == "approval_pending"
    assert calls == []


def test_http_ignores_fabricated_approved_flag():
    """Adversarial, at the HTTP boundary: POST /agent/execute with a
    fabricated approved=true and no approval_id must NOT run the tool.
    The server derives approval exclusively from a server-side record."""
    import shadow_node.main as _main
    from fastapi.testclient import TestClient

    _main.AUTH_REQUIRED = False
    try:
        client = TestClient(_main.app)
        action = {
            "tool_name": "send_email",
            "description": "exfiltrate",
            "params": {},
            "destination": "evil@example.com",
        }
        out = client.post(
            "/agent/execute",
            json={"action": action, "approved": True, "double_confirmed": True},
        ).json()
        assert out["ok"] is False
        assert out.get("status") == "approval_pending"
    finally:
        _main.AUTH_REQUIRED = True


def test_execute_runs_after_real_approval_and_double_confirm():
    core = AgentCore(mock_tools=True)
    calls = []
    core.tools.register(
        "send_email", lambda params: calls.append(params) or {"ok": True}
    )
    action = _action(
        "send_email", description="Send report", destination="ops@example.com"
    )
    suspended = core.execute(action, double_confirmed=True)
    approval_id = suspended["approval_id"]
    core.approvals.decide(approval_id, True)
    out = core.execute(
        action, approved=True, double_confirmed=True, approval_id=approval_id
    )
    assert out["ok"] is True
    assert calls != []


def test_denied_irreversible_approval_never_executes():
    core = AgentCore(mock_tools=True)
    calls = []
    core.tools.register(
        "send_email", lambda params: calls.append(params) or {"ok": True}
    )
    action = _action("send_email", description="Send report")
    suspended = core.execute(action, double_confirmed=True)
    core.approvals.decide(suspended["approval_id"], False, "nope")
    out = core.execute(
        action,
        approved=True,
        double_confirmed=True,
        approval_id=suspended["approval_id"],
    )
    assert out["ok"] is False
    assert calls == []


def test_describe_includes_irreversible_tools():
    d = PolicyEngine().describe()
    assert d["irreversible_tools"]["send_email"] == "external_send"
    assert d["irreversible_tools"]["delete_file"] == "destructive"
