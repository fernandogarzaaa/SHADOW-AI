"""Sentinel-lite policy engine: one deterministic policy path for all agent actions.

Rules are data, not code. The engine loads a policy document (YAML) describing
blocked / destructive / sensitive tools and evaluates every action against it
in a fixed order, returning exactly one of ALLOW, DENY, or REQUIRE_APPROVAL
(the spec's ASK) with a human-readable reason and the rule id that fired.

No LLM acts as judge. Evaluation is a pure function of (action, profile,
approvals state); the same inputs always produce the same decision.
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from .models import *

# Built-in default policy. Mirrors the historical hard-coded rule sets so a
# node without an explicit policy file behaves exactly as before. The operator
# policy file (apps/shadow-node/shadow_node/policy.yaml) starts from this and
# is the readable, editable source of truth on a real node.
DEFAULT_POLICY: dict = {
    "version": 1,
    "blocked_tools": [
        "keylogger",
        "covert_monitor",
        "bypass_ios_sandbox",
        "silent_microphone",
        "silent_camera",
        "leak_secret",
    ],
    "blocked_description_patterns": [
        "keylog",
        "covert",
        "bypass ios",
        "silently record",
        "reveal secret",
    ],
    "destructive_tools": ["delete_file", "overwrite_file", "shell_rm"],
    "sensitive_tools": [
        "send_email",
        "send_message",
        "write_file",
        "device_control",
        "cloud_model",
        "ghost_handoff",
        "calendar.create",
        "email.draft",
    ],
    # Risk classes that always require explicit user approval.
    "approval_required_risks": ["medium", "high", "blocked"],
    # Per-tool approval tiers. Empty by default: with no tiers configured the
    # engine behaves exactly as before. Tiers are operator opt-in and can
    # only relax the *approval* requirement; they never override the hard
    # gates above (emergency pause, blocked tools, destructive double
    # confirmation), which are evaluated first in decide().
    "tool_tiers": {},
}


class PolicyOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"  # the spec's ASK


#: Valid per-tool approval tiers. `always_ask` forces an approval prompt;
#: `auto_approve` waives approval for routine (low/medium risk, non-sensitive,
#: non-destructive) uses of the tool; `always_allow` acts as standing
#: pre-approval for routine *low-risk, non-sensitive, non-destructive* uses
#: only. Sensitive, medium/high-risk, or destructive uses still require
#: approval even when tiered `always_allow`, and tiering a sensitive tool
#: `always_allow` is a configuration error. All three still lose to the hard
#: gates (emergency pause, blocked tools, destructive double confirmation).
TOOL_TIERS = ("always_ask", "auto_approve", "always_allow")


class PolicyDecision(BaseModel):
    outcome: PolicyOutcome
    reason: str
    rule_id: str
    risk: RiskClass = RiskClass.LOW


def _load_policy_document(policy: dict | None, policy_file: str | Path | None) -> dict:
    """Resolve the effective policy document.

    Precedence: explicit dict > explicit file > SHADOW_POLICY_FILE env >
    built-in defaults. An explicitly configured file that cannot be read is a
    hard error: silently running on defaults would hide operator mistakes.
    """
    if policy is not None:
        return policy
    path = policy_file or os.getenv("SHADOW_POLICY_FILE")
    if path is None:
        return DEFAULT_POLICY
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"policy file not found: {p}")
    try:
        import yaml
    except ImportError as e:  # pragma: no cover
        raise ValueError("PyYAML is required to load a policy file") from e
    try:
        doc = yaml.safe_load(p.read_text())
    except Exception as e:
        raise ValueError(f"policy file {p} is not valid YAML: {e}") from e
    if not isinstance(doc, dict):
        raise ValueError(f"policy file {p} must contain a YAML mapping")
    merged = dict(DEFAULT_POLICY)
    merged.update(doc)
    return merged


def _parse_tool_tiers(raw: dict | None) -> dict[str, str]:
    """Validate the `tool_tiers` mapping. Unknown tier names are a hard error:
    silently running a misconfigured tier would hide operator mistakes."""
    tiers: dict[str, str] = {}
    for tool, tier in (raw or {}).items():
        name = str(tier).lower()
        if name not in TOOL_TIERS:
            raise ValueError(
                f"unknown tool_tier {tier!r} for tool {tool!r}; "
                f"expected one of {list(TOOL_TIERS)}"
            )
        tiers[str(tool).lower()] = name
    return tiers


class PolicyEngine:
    """Single policy authority. Every agent action flows through decide()."""

    def __init__(self, policy: dict | None = None, policy_file: str | Path | None = None):
        self.document = _load_policy_document(policy, policy_file)
        self.blocked_tools = {t.lower() for t in self.document.get("blocked_tools", [])}
        self.blocked_patterns = [p.lower() for p in self.document.get("blocked_description_patterns", [])]
        self.destructive_tools = {t.lower() for t in self.document.get("destructive_tools", [])}
        self.sensitive_tools = {t.lower() for t in self.document.get("sensitive_tools", [])}
        self.approval_required_risks = set(self.document.get("approval_required_risks", []))
        self.tool_tiers = _parse_tool_tiers(self.document.get("tool_tiers", {}))
        # Fail loud: `always_allow` on a sensitive tool would silently waive
        # approval for outbound messages, writes, and other sensitive
        # actions. That is never a valid configuration.
        for tool, tier in self.tool_tiers.items():
            if tier == "always_allow" and tool in self.sensitive_tools:
                raise ValueError(
                    f"tool_tier 'always_allow' is not allowed for sensitive tool "
                    f"{tool!r}: sensitive tools always require approval; "
                    f"use 'always_ask' or 'auto_approve' instead"
                )

    # -- risk classification -------------------------------------------------
    def classify_action(self, action: AgentAction) -> RiskClass:
        n = action.tool_name.lower()
        d = action.description.lower()
        if n in self.blocked_tools or any(x in d for x in self.blocked_patterns):
            return RiskClass.BLOCKED
        if n in self.destructive_tools or action.destructive:
            return RiskClass.HIGH
        if n in {"send_email", "send_message"}:
            return RiskClass.HIGH
        if n in self.sensitive_tools or "cloud" in d:
            return RiskClass.HIGH
        if any(w in d for w in ["calendar", "email", "contact", "personal", "file"]):
            return RiskClass.MEDIUM
        return RiskClass.LOW

    def requires_approval(self, action: AgentAction, profile: UserProfile) -> bool:
        risk = self.classify_action(action)
        if profile.emergency_paused or profile.autonomy_mode in [
            AutonomyMode.OFF,
            AutonomyMode.SUGGEST_ONLY,
            AutonomyMode.DRAFT_ONLY,
        ]:
            return True
        if action.tool_name.lower() in self.sensitive_tools:
            return True
        if risk.value in self.approval_required_risks:
            return True
        return profile.autonomy_mode != AutonomyMode.TRUSTED_WORKFLOW

    # -- the single decision path --------------------------------------------
    def decide(
        self,
        action: AgentAction,
        profile: UserProfile,
        approved: bool = False,
        double_confirmed: bool = False,
    ) -> PolicyDecision:
        """Evaluate one action. Fixed rule order; first match wins."""
        risk = self.classify_action(action)
        if profile.emergency_paused:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="Emergency pause is enabled.",
                rule_id="emergency_pause",
                risk=risk,
            )
        if risk == RiskClass.BLOCKED:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="Action is blocked by hard safety policy.",
                rule_id="blocked_tool",
                risk=risk,
            )
        if action.destructive and not double_confirmed:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="Destructive action requires double confirmation.",
                rule_id="destructive_needs_double_confirm",
                risk=risk,
            )
        # Per-tool approval tiers. These run after the hard gates above, so a
        # tier can only relax the approval requirement, never override a
        # denial. An empty tool_tiers map (the default) falls straight
        # through to the standard requires_approval() path.
        tier = self.tool_tiers.get(action.tool_name.lower())
        if tier == "always_ask" and not approved:
            return PolicyDecision(
                outcome=PolicyOutcome.REQUIRE_APPROVAL,
                reason=f"Tool '{action.tool_name}' is tiered 'always_ask': explicit approval required.",
                rule_id="tool_tier_always_ask",
                risk=risk,
            )
        if tier == "always_allow":
            # Standing pre-approval covers routine low-risk reads only.
            # Sensitive, risky, or destructive uses fall through to the
            # normal approval path: the tier can waive approval, never the
            # safety requirement.
            if (
                risk == RiskClass.LOW
                and action.tool_name.lower() not in self.sensitive_tools
                and not action.destructive
            ):
                return PolicyDecision(
                    outcome=PolicyOutcome.ALLOW,
                    reason=f"Tool '{action.tool_name}' is tiered 'always_allow': routine low-risk use.",
                    rule_id="tool_tier_always_allow",
                    risk=risk,
                )
        if (
            tier == "auto_approve"
            and risk in (RiskClass.LOW, RiskClass.MEDIUM)
            and action.tool_name.lower() not in self.sensitive_tools
            and not action.destructive
        ):
            return PolicyDecision(
                outcome=PolicyOutcome.ALLOW,
                reason=f"Tool '{action.tool_name}' is tiered 'auto_approve': routine use waived approval.",
                rule_id="tool_tier_auto_approve",
                risk=risk,
            )
        if self.requires_approval(action, profile) and not approved:
            return PolicyDecision(
                outcome=PolicyOutcome.REQUIRE_APPROVAL,
                reason="Approval required before execution.",
                rule_id="approval_required",
                risk=risk,
            )
        return PolicyDecision(
            outcome=PolicyOutcome.ALLOW, reason="Allowed.", rule_id="allow", risk=risk
        )

    # -- compatibility wrappers ----------------------------------------------
    def can_execute(
        self,
        action: AgentAction,
        profile: UserProfile,
        approved: bool = False,
        double_confirmed: bool = False,
    ) -> tuple[bool, str]:
        decision = self.decide(action, profile, approved, double_confirmed)
        return decision.outcome == PolicyOutcome.ALLOW, decision.reason

    def cloud_allowed(self, grants: list[ConsentGrant], explicit_approval: bool, trusted_mode: bool = False) -> bool:
        return (explicit_approval or trusted_mode) and any(
            g.model_access_level != "local_only" and g.revoked_at is None for g in grants
        )

    def describe(self) -> dict:
        """Operator-readable summary of the loaded policy (no secrets)."""
        return {
            "version": self.document.get("version"),
            "blocked_tools": sorted(self.blocked_tools),
            "destructive_tools": sorted(self.destructive_tools),
            "sensitive_tools": sorted(self.sensitive_tools),
            "approval_required_risks": sorted(self.approval_required_risks),
            "tool_tiers": dict(sorted(self.tool_tiers.items())),
        }
