"""Tests for Sentinel-lite: unified policy, credential vault, audit chain.

Covers the policy decision matrix (allow/deny/require_approval), policy file
loading, surrogate credential resolution (expiry, scope, rotation, revoke),
audit chain integrity (including tamper detection), and the execution-path
integration: surrogates are injected just-in-time and never leak into stored
evidence.
"""
import os

import pytest

from agent_core import (
    AgentAction,
    AgentCore,
    AuditChain,
    AutonomyMode,
    CredentialVault,
    PolicyDecision,
    PolicyEngine,
    PolicyOutcome,
    RiskClass,
    UserProfile,
)


def _action(tool, params=None, description="do the thing", destructive=False):
    return AgentAction(tool_name=tool, description=description, params=params or {},
                       destructive=destructive)


def _profile(**kw):
    return UserProfile(autonomy_mode=AutonomyMode.EXECUTE_WITH_APPROVAL, **kw)


# --- policy decision matrix ---

def test_blocked_tool_is_denied_even_when_approved():
    engine = PolicyEngine()
    d = engine.decide(_action("keylogger", description="log keys"), _profile(), approved=True)
    assert d.outcome == PolicyOutcome.DENY
    assert d.rule_id == "blocked_tool"
    assert d.risk == RiskClass.BLOCKED


def test_blocked_description_pattern_is_denied():
    engine = PolicyEngine()
    d = engine.decide(_action("answer_question", description="silently record audio"), _profile())
    assert d.outcome == PolicyOutcome.DENY
    assert d.rule_id == "blocked_tool"


def test_destructive_without_double_confirm_is_denied():
    engine = PolicyEngine()
    d = engine.decide(_action("delete_file", destructive=True), _profile(), approved=True)
    assert d.outcome == PolicyOutcome.DENY
    assert d.rule_id == "destructive_needs_double_confirm"


def test_sensitive_tool_requires_approval():
    engine = PolicyEngine()
    d = engine.decide(_action("send_email", description="send the report"), _profile())
    assert d.outcome == PolicyOutcome.REQUIRE_APPROVAL
    assert d.rule_id == "approval_required"
    assert "Approval required" in d.reason


def test_sensitive_tool_allowed_after_approval_and_double_confirm():
    engine = PolicyEngine()
    d = engine.decide(_action("send_email", description="send the report"),
                      _profile(), approved=True, double_confirmed=True)
    assert d.outcome == PolicyOutcome.ALLOW
    assert d.rule_id == "allow"


def test_emergency_pause_denies_everything():
    engine = PolicyEngine()
    d = engine.decide(_action("answer_question", description="hello"),
                      _profile(emergency_paused=True))
    assert d.outcome == PolicyOutcome.DENY
    assert d.rule_id == "emergency_pause"


def test_trusted_workflow_allows_low_risk_without_approval():
    engine = PolicyEngine()
    profile = UserProfile(autonomy_mode=AutonomyMode.TRUSTED_WORKFLOW)
    d = engine.decide(_action("answer_question", description="summarize this"), profile)
    assert d.outcome == PolicyOutcome.ALLOW


def test_suggest_only_requires_approval_for_low_risk():
    engine = PolicyEngine()
    profile = UserProfile(autonomy_mode=AutonomyMode.SUGGEST_ONLY)
    d = engine.decide(_action("answer_question", description="summarize this"), profile)
    assert d.outcome == PolicyOutcome.REQUIRE_APPROVAL


def test_can_execute_compatibility():
    engine = PolicyEngine()
    ok, reason = engine.can_execute(_action("send_email"), _profile())
    assert ok is False and "Approval required" in reason
    ok, reason = engine.can_execute(_action("send_email"), _profile(), approved=True)
    assert ok is True and reason == "Allowed."
    ok, reason = engine.can_execute(_action("keylogger"), _profile(), approved=True)
    assert ok is False


def test_decisions_are_deterministic():
    engine = PolicyEngine()
    a = _action("send_email", description="send it")
    p = _profile()
    d1 = engine.decide(a, p)
    d2 = engine.decide(a, p)
    assert d1 == d2


# --- policy file loading ---

def test_policy_file_overrides_defaults(tmp_path):
    f = tmp_path / "policy.yaml"
    f.write_text(
        "version: 1\n"
        "sensitive_tools:\n"
        "  - send_email\n"
        "blocked_tools: []\n"
        "blocked_description_patterns: []\n"
        "destructive_tools: []\n"
        "approval_required_risks: []\n"
    )
    engine = PolicyEngine(policy_file=str(f))
    # keylogger no longer blocked by this custom policy
    d = engine.decide(_action("keylogger", description="log keys"),
                      UserProfile(autonomy_mode=AutonomyMode.TRUSTED_WORKFLOW))
    assert d.outcome == PolicyOutcome.ALLOW
    # send_email still sensitive
    assert "send_email" in engine.sensitive_tools


def test_missing_explicit_policy_file_is_hard_error(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        PolicyEngine(policy_file=str(tmp_path / "nope.yaml"))


def test_policy_file_env_var(tmp_path, monkeypatch):
    f = tmp_path / "policy.yaml"
    f.write_text("version: 1\nblocked_tools: []\nblocked_description_patterns: []\n"
                 "destructive_tools: []\nsensitive_tools: []\napproval_required_risks: []\n")
    monkeypatch.setenv("SHADOW_POLICY_FILE", str(f))
    engine = PolicyEngine()
    assert engine.blocked_tools == set()


def test_policy_describe_has_no_secrets():
    desc = PolicyEngine().describe()
    assert "blocked_tools" in desc and "keylogger" in desc["blocked_tools"]


# --- credential vault ---

def test_vault_store_mint_resolve():
    vault = CredentialVault()
    vault.set_credential("openai", "sk-live-secret-value-123", scopes=["llm"])
    token = vault.mint_surrogate("openai", scopes=["llm"])
    assert token.startswith("shv_")
    assert vault.resolve_surrogate(token, required_scope="llm") == "sk-live-secret-value-123"


def test_vault_unknown_surrogate_returns_none():
    vault = CredentialVault()
    assert vault.resolve_surrogate("shv_deadbeef") is None


def test_vault_mint_unknown_credential_raises():
    vault = CredentialVault()
    with pytest.raises(KeyError):
        vault.mint_surrogate("nope")


def test_vault_expired_surrogate_denied(monkeypatch):
    import agent_core.vault as vault_mod
    vault = CredentialVault()
    vault.set_credential("k", "secret-value-xyz")
    token = vault.mint_surrogate("k", ttl_seconds=60)
    real_now = vault_mod.now
    monkeypatch.setattr(vault_mod, "now", lambda: real_now() + __import__("datetime").timedelta(seconds=61))
    assert vault.resolve_surrogate(token) is None


def test_vault_scope_mismatch_denied():
    vault = CredentialVault()
    vault.set_credential("k", "secret-value-xyz", scopes=["llm"])
    token = vault.mint_surrogate("k", scopes=["llm"])
    assert vault.resolve_surrogate(token, required_scope="email") is None
    assert vault.resolve_surrogate(token, required_scope="llm") == "secret-value-xyz"


def test_vault_rotation_revokes_surrogates():
    vault = CredentialVault()
    vault.set_credential("k", "old-secret-value")
    token = vault.mint_surrogate("k")
    vault.rotate_credential("k", "new-secret-value")
    assert vault.resolve_surrogate(token) is None
    token2 = vault.mint_surrogate("k")
    assert vault.resolve_surrogate(token2) == "new-secret-value"


def test_vault_revoke_credential():
    vault = CredentialVault()
    vault.set_credential("k", "secret-value-xyz")
    token = vault.mint_surrogate("k")
    vault.revoke_credential("k")
    assert vault.resolve_surrogate(token) is None
    assert vault.credential_names() == []
    with pytest.raises(KeyError):
        vault.mint_surrogate("k")


def test_vault_inject_replaces_surrogates_in_copy_only():
    vault = CredentialVault()
    vault.set_credential("k", "super-secret-value-1")
    token = vault.mint_surrogate("k")
    params = {"api_key": token, "other": "plain"}
    injected, resolved = vault.inject(params)
    assert injected["api_key"] == "super-secret-value-1"
    assert injected["other"] == "plain"
    assert params["api_key"] == token  # original untouched
    assert resolved == ["k"]


def test_vault_scrub_redacts_tokens_and_values():
    vault = CredentialVault()
    vault.set_credential("k", "super-secret-value-1")
    token = vault.mint_surrogate("k")
    text = f"called with {token} and super-secret-value-1 ok"
    scrubbed = vault.scrub(text)
    assert token not in scrubbed
    assert "super-secret-value-1" not in scrubbed
    assert "[redacted]" in scrubbed


def test_vault_scrub_ignores_short_values():
    vault = CredentialVault()
    vault.set_credential("k", "abc")
    assert vault.scrub("abc is fine here") == "abc is fine here"


def test_vault_validations():
    vault = CredentialVault()
    with pytest.raises(ValueError):
        vault.set_credential("", "x")
    with pytest.raises(ValueError):
        vault.set_credential("k", "")
    vault.set_credential("k", "secret-value-xyz")
    with pytest.raises(ValueError):
        vault.mint_surrogate("k", ttl_seconds=0)


# --- audit chain ---

def test_audit_chain_records_and_verifies():
    chain = AuditChain()
    chain.record("sentinel_policy", "policy.decision", {"outcome": "allow"})
    chain.record("sentinel_policy", "execution.verdict", {"verification": "verified"})
    ok, problems = chain.verify()
    assert ok and problems == []
    assert len(chain) == 2
    assert [e.seq for e in chain.entries()] == [0, 1]
    assert chain.entries()[1].prev_hash == chain.entries()[0].hash


def test_audit_chain_detects_tampering():
    chain = AuditChain()
    chain.record("a", "policy.decision", {"outcome": "allow"})
    chain.record("a", "policy.decision", {"outcome": "deny"})
    chain._entries[0].payload["outcome"] = "deny"  # tamper with history
    ok, problems = chain.verify()
    assert not ok
    assert any("tampered" in p or "mismatch" in p for p in problems)


def test_audit_chain_detects_reordering():
    chain = AuditChain()
    chain.record("a", "one", {})
    chain.record("a", "two", {})
    chain._entries[0], chain._entries[1] = chain._entries[1], chain._entries[0]
    ok, _ = chain.verify()
    assert not ok


def test_audit_chain_empty_verifies():
    ok, problems = AuditChain().verify()
    assert ok and problems == []


# --- execution-path integration ---


def test_execute_injects_surrogate_and_scrubs_evidence():
    chain = AuditChain()
    vault = CredentialVault(audit=chain)
    core = AgentCore(audit_chain=chain, vault=vault)
    seen = []

    def capturing_tool(params):
        seen.append(dict(params))
        return {"ok": True, "echo": params}

    core.tools.register("call_api", capturing_tool)
    vault.set_credential("api", "live-secret-abcdef")
    token = vault.mint_surrogate("api")
    action = AgentAction(tool_name="call_api", description="call the api",
                         params={"api_key": token})
    core.profile.autonomy_mode = AutonomyMode.TRUSTED_WORKFLOW
    out = core.execute(action, approved=True)
    assert out["ok"] is True
    assert seen[0]["api_key"] == "live-secret-abcdef"  # live tool call saw the secret
    assert out["result"]["echo"]["api_key"] == "[redacted]"  # API response is scrubbed
    rec = core.executions[out["execution_id"]]
    assert rec.action.params["api_key"] == token  # stored record keeps the surrogate
    blob = rec.model_dump_json()
    assert "live-secret-abcdef" not in blob  # raw secret never persisted
    # The surrogate token itself is intentionally retained in action.params:
    # it is opaque, expiring, revocable, and reveals nothing without the vault.
    assert token in blob
    kinds = [e.kind for e in rec.evidence]
    assert "policy_decision" in kinds


def test_execute_records_chain_events():
    chain = AuditChain()
    core = AgentCore(audit_chain=chain)
    core.profile.autonomy_mode = AutonomyMode.TRUSTED_WORKFLOW
    action = AgentAction(tool_name="keylogger", description="log keys")
    out = core.execute(action)
    assert out["ok"] is False
    types = [e.event_type for e in chain.entries()]
    assert "policy.decision" in types
    assert "execution.verdict" in types
    denied = [e for e in chain.entries() if e.event_type == "policy.decision"][0]
    assert denied.payload["outcome"] == "deny"
    assert denied.payload["rule_id"] == "blocked_tool"


def test_approvals_record_chain_events():
    chain = AuditChain()
    core = AgentCore(audit_chain=chain)
    action = AgentAction(tool_name="send_email", description="send the report")
    req = core.approvals.create(action, "needs a human")
    core.approvals.decide(req.id, True)
    types = [e.event_type for e in chain.entries()]
    assert "approval.created" in types
    assert "approval.decided" in types
    decided = [e for e in chain.entries() if e.event_type == "approval.decided"][0]
    assert decided.payload["decision"] == "approved"


def test_device_auth_failure_hits_chain():
    from agent_core import DeviceSessionStore
    chain = AuditChain()
    sessions = DeviceSessionStore()
    sessions.event_sink = lambda actor, event_type, payload: chain.record(actor, event_type, payload)
    ok, reason = sessions.verify(None, None, None, None, "GET", "/approvals")
    assert ok is False
    types = [e.event_type for e in chain.entries()]
    assert "auth.decision" in types


def test_drain_audit_returns_new_events_once():
    core = AgentCore()
    core.propose("reveal the api key now")
    first = core.drain_audit()
    assert len(first) == 1
    assert core.drain_audit() == []
