"""User approval rules (Allow / Ask first / Block) and the outgoing-data
filter. Rules may tighten operator policy but never loosen a safety gate;
credentials never leave the node; card/ID numbers need a named approval."""
import pytest
from fastapi.testclient import TestClient

from agent_core import AgentAction, AutonomyMode, PolicyEngine, UserProfile
from agent_core.egress_scan import scan
from agent_core.policy import PolicyOutcome


def act(tool, **params):
    return AgentAction(tool_name=tool, description=f"test {tool}", params=params)


def profile(mode=AutonomyMode.SUGGEST_ONLY):
    return UserProfile(autonomy_mode=mode)


# --- scanner ----------------------------------------------------------------------------

@pytest.mark.parametrize("text,kind", [
    ("key sk-ant-api03-" + "a" * 30, "Anthropic or OpenAI API key"),
    ("AKIAABCDEFGHIJKLMNOP", "AWS access key"),
    ("ghp_" + "x" * 36, "GitHub token"),
    ("-----BEGIN RSA PRIVATE KEY-----", "private key"),
    ("https://user:hunter22@example.com/x", "password in a URL"),
    ("password: correct-horse", "password"),
])
def test_scanner_blocks_credentials(text, kind):
    found = {f.kind: f.severity for f in scan(text)}
    assert found.get(kind) == "block"


def test_scanner_confirms_cards_and_ssn():
    found = {f.kind: f.severity for f in scan({"body": "card 4242 4242 4242 4242, ssn 123-45-6789"})}
    assert found == {"payment card number": "confirm", "Social Security number": "confirm"}


@pytest.mark.parametrize("text", [
    "order 1234567890123 shipped",       # fails Luhn
    "call 555-123-4567 tomorrow",        # phone, not SSN
    "the meeting is at 10:30",
    "0000 0000 0000 0000",               # one repeated digit
])
def test_scanner_ignores_ordinary_text(text):
    assert scan(text) == []


# --- policy -------------------------------------------------------------------------------

def test_outbound_secret_is_denied_even_when_approved():
    e = PolicyEngine()
    d = e.decide(act("http.get", url="https://x.test/?k=sk-proj-" + "b" * 30), profile(), approved=True, double_confirmed=True)
    assert d.outcome == PolicyOutcome.DENY and d.rule_id == "outbound_secret_blocked"
    assert "API key" in d.reason


def test_outbound_card_needs_named_approval_and_beats_rules():
    e = PolicyEngine(policy={"tool_tiers": {"web.search": "auto_approve"}})
    a = act("web.search", query="is 4242424242424242 valid")
    d = e.decide(a, profile(AutonomyMode.TRUSTED_WORKFLOW))
    assert d.outcome == PolicyOutcome.REQUIRE_APPROVAL and d.rule_id == "outbound_sensitive_data"
    assert "payment card" in d.reason
    assert e.decide(a, profile(AutonomyMode.TRUSTED_WORKFLOW), approved=True).outcome != PolicyOutcome.DENY


def test_non_outbound_tool_not_scanned():
    e = PolicyEngine()
    d = e.decide(act("note.create", body="card 4242 4242 4242 4242"), profile(AutonomyMode.TRUSTED_WORKFLOW))
    assert d.rule_id != "outbound_sensitive_data"


def test_user_block_and_ask_win():
    e = PolicyEngine(policy={"tool_tiers": {"note.create": "auto_approve"}})
    e.set_user_rule("note.create", "block")
    d = e.decide(act("note.create"), profile(AutonomyMode.TRUSTED_WORKFLOW), approved=True)
    assert d.outcome == PolicyOutcome.DENY and d.rule_id == "user_rule_block"
    e.set_user_rule("note.create", "ask")
    d = e.decide(act("note.create"), profile(AutonomyMode.TRUSTED_WORKFLOW))
    assert d.outcome == PolicyOutcome.REQUIRE_APPROVAL and d.rule_id == "user_rule_ask"


def test_user_allow_waives_routine_approval():
    e = PolicyEngine()
    assert e.decide(act("note.create"), profile()).outcome == PolicyOutcome.REQUIRE_APPROVAL
    e.set_user_rule("note.create", "allow")
    d = e.decide(act("note.create"), profile())
    assert d.outcome == PolicyOutcome.ALLOW and d.rule_id == "user_rule_allow"


@pytest.mark.parametrize("tool", ["email.draft", "calendar.create", "send_email", "delete_file",
                                  "http.get", "keylogger"])
def test_allow_refused_for_gated_tools(tool):
    e = PolicyEngine()
    with pytest.raises(ValueError):
        e.set_user_rule(tool, "allow")


def test_allow_refused_when_operator_requires_approval():
    e = PolicyEngine(policy={"tool_tiers": {"note.create": "always_ask"}})
    ok, why = e.allow_eligible("note.create")
    assert not ok and "operator" in why


def test_allow_never_beats_hard_gates():
    e = PolicyEngine()
    e.set_user_rule("note.create", "allow")
    paused = UserProfile(autonomy_mode=AutonomyMode.SUGGEST_ONLY, emergency_paused=True)
    assert e.decide(act("note.create"), paused).outcome == PolicyOutcome.DENY


# --- node API -----------------------------------------------------------------------------

@pytest.fixture
def node(monkeypatch, tmp_path):
    import shadow_node.main as m
    from cryptography.fernet import Fernet
    from shadow_node.provider_auth import CredentialStore
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    monkeypatch.setattr(m, "credentials", CredentialStore(path=str(tmp_path / "c.enc"), key=Fernet.generate_key()))
    saved = dict(m.core.policy.user_rules)
    m.core.policy.user_rules.clear()
    yield TestClient(m.app), m
    m.core.policy.user_rules.clear()
    m.core.policy.user_rules.update(saved)


def test_rules_api_round_trip_and_persistence(node):
    c, m = node
    rows = {r["tool"]: r for r in c.get("/policy/rules").json()["items"]}
    assert rows["note.create"]["allow_eligible"] is True
    assert rows["email.draft"]["allow_eligible"] is False and rows["email.draft"]["allow_blocked_reason"]
    assert c.put("/policy/rules/note.create", json={"rule": "allow"}).status_code == 200
    assert c.put("/policy/rules/email.draft", json={"rule": "allow"}).status_code == 422
    assert c.put("/policy/rules/email.draft", json={"rule": "block"}).status_code == 200
    # persisted, and reloaded into a fresh engine
    m.core.policy.user_rules.clear()
    m._load_user_rules()
    assert m.core.policy.user_rules == {"note.create": "allow", "email.draft": "block"}
    c.delete("/policy/rules/email.draft")
    assert "email.draft" not in m.core.policy.user_rules


def test_always_allow_from_approval(node):
    c, m = node
    a = {"tool_name": "note.create", "description": "n", "params": {"title": "t", "body": "b"}}
    rid = c.post("/approvals", json={"action": a}).json()["id"]
    assert c.post(f"/approvals/{rid}/approve", json={"remember": True}).status_code == 200
    assert m.core.policy.user_rules.get("note.create") == "allow"
    # ineligible tools can't be remembered
    a2 = {"tool_name": "email.draft", "description": "e", "params": {"to": "a@b.c"}}
    rid2 = c.post("/approvals", json={"action": a2}).json()["id"]
    assert c.post(f"/approvals/{rid2}/approve", json={"remember": True}).status_code == 409
    assert m.core.approvals.requests[rid2].status.value == "pending"  # untouched


def test_approve_without_body_still_works(node):
    c, m = node
    a = {"tool_name": "note.create", "description": "n", "params": {"title": "t"}}
    rid = c.post("/approvals", json={"action": a}).json()["id"]
    assert c.post(f"/approvals/{rid}/approve").status_code == 200
