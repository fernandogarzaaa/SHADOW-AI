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
from .capabilities import (
    AgentPersona,
    MEMORY_TOOLS,
    RESEARCH_TOOLS,
    persona_from_dict,
)

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
    # Irreversible action classes (Sentinel gate). Maps tool name -> class.
    # Every irreversible action ALWAYS requires an explicit recorded
    # approval: no tier, autonomy mode, or persona can waive it. Classes
    # in DOUBLE_CONFIRM_CLASSES additionally require double confirmation.
    # Operators extend this via policy.yaml for new publish/financial tools.
    "irreversible_tools": {
        "delete_file": "destructive",
        "overwrite_file": "destructive",
        "shell_rm": "destructive",
        "send_email": "external_send",
        "send_message": "external_send",
    },
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


#: Irreversible action classes (Sentinel gate). The single source of truth
#: for "this action cannot be taken back": destructive (delete/overwrite),
#: external_send (a message leaves the node), publish (content goes public),
#: financial (money moves or an obligation is created).
IRREVERSIBLE_CLASSES = ("destructive", "external_send", "publish", "financial")

#: Irreversible classes that require two explicit confirmations, not one.
#: Destructive tools keep their historical double-confirmation; external
#: sends and financial actions join them per the Sentinel spec.
DOUBLE_CONFIRM_CLASSES = ("destructive", "external_send", "financial")

#: Consequence text per irreversible class. Shown on the approval card so
#: the confirmation names the concrete consequence, never a bare
#: "Are you sure?". {destination} is filled from the action.
IRREVERSIBLE_CONSEQUENCES = {
    "destructive": "This will permanently delete or overwrite data. It cannot be undone.",
    "external_send": (
        "This will send content to {destination}. The recipient can read it "
        "immediately, and it cannot be recalled."
    ),
    "publish": (
        "This will publish content where others can see it. "
        "It may be impossible to fully retract."
    ),
    "financial": (
        "This will move real money or create a financial obligation. "
        "It cannot be reversed automatically."
    ),
}


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


def _parse_irreversible_tools(raw: dict | None) -> dict[str, str]:
    """Validate the `irreversible_tools` mapping. Unknown class names are a
    hard error: silently running a misclassified irreversible tool would
    hide an operator mistake behind a weaker gate."""
    mapping: dict[str, str] = {}
    for tool, cls in (raw or {}).items():
        name = str(cls).lower()
        if name not in IRREVERSIBLE_CLASSES:
            raise ValueError(
                f"unknown irreversible class {cls!r} for tool {tool!r}; "
                f"expected one of {list(IRREVERSIBLE_CLASSES)}"
            )
        mapping[str(tool).lower()] = name
    return mapping


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
        self.irreversible_tools = _parse_irreversible_tools(
            self.document.get("irreversible_tools", {})
        )
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
    def is_destructive(self, action: AgentAction) -> bool:
        """Server-side destructiveness. The client-supplied flag can only
        widen the classification, never narrow it: a tool listed in the
        policy's destructive_tools is destructive regardless of what the
        client claims (audit P0-4)."""
        return bool(action.destructive) or action.tool_name.lower() in self.destructive_tools

    # -- Sentinel irreversible-action gate -----------------------------------
    def irreversible_class(self, action: AgentAction) -> str | None:
        """The single source of truth for irreversibility. Returns the
        irreversible class ("destructive", "external_send", "publish",
        "financial") or None. A tool listed as destructive is always
        irreversible even if the operator mapping omits it."""
        cls = self.irreversible_tools.get(action.tool_name.lower())
        if cls is not None:
            return cls
        if self.is_destructive(action):
            return "destructive"
        return None

    def is_irreversible(self, action: AgentAction) -> bool:
        """True when the action cannot be taken back. Such actions ALWAYS
        require an explicit recorded approval: no tier, autonomy mode, or
        persona can waive the gate (enforced in decide())."""
        return self.irreversible_class(action) is not None

    def requires_double_confirmation(self, action: AgentAction) -> bool:
        """Two explicit confirmations instead of one. Destructive tools
        keep their historical requirement; external sends and financial
        actions require it per the Sentinel spec."""
        return self.irreversible_class(action) in DOUBLE_CONFIRM_CLASSES

    def consequence_for(self, action: AgentAction) -> str | None:
        """Human-readable consequence for the approval card. Names the
        concrete consequence so the confirmation is never a bare
        "Are you sure?". None for reversible actions."""
        cls = self.irreversible_class(action)
        if cls is None:
            return None
        destination = action.destination or "the recipient"
        return IRREVERSIBLE_CONSEQUENCES[cls].format(destination=destination)

    def classify_action(self, action: AgentAction) -> RiskClass:
        n = action.tool_name.lower()
        d = action.description.lower()
        if n in self.blocked_tools or any(x in d for x in self.blocked_patterns):
            return RiskClass.BLOCKED
        if self.is_destructive(action):
            return RiskClass.HIGH
        if self.irreversible_class(action) is not None:
            # Any irreversible tool (including future publish/financial
            # tools an operator adds) is HIGH risk by default.
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
        if self.is_irreversible(action):
            # Sentinel gate: irreversibility always needs a recorded
            # approval, even in TRUSTED_WORKFLOW mode. (decide() enforces
            # this again ahead of the tiers so no tier can waive it.)
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
        persona: AgentPersona | dict | None = None,
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
        if self.is_destructive(action) and not double_confirmed:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="Destructive action requires double confirmation.",
                rule_id="destructive_needs_double_confirm",
                risk=risk,
            )
        # Sentinel gate, part 1: external sends and financial actions need
        # two explicit confirmations, mirroring the destructive pattern.
        # Runs before persona/tiers so nothing can waive it.
        irrev = self.irreversible_class(action)
        if irrev in ("external_send", "financial") and not double_confirmed:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason=(
                    f"Irreversible {irrev.replace('_', ' ')} action requires "
                    "double confirmation."
                ),
                rule_id="irreversible_needs_double_confirm",
                risk=risk,
            )
        # Sentinel gate, part 2: no irreversible action is ever ALLOWed
        # without a recorded explicit approval. Runs before persona/tiers
        # so no tier or autonomy mode can waive the gate. The reason names
        # the concrete consequence for the approval card.
        if irrev is not None and not approved:
            return PolicyDecision(
                outcome=PolicyOutcome.REQUIRE_APPROVAL,
                reason=(
                    f"Irreversible action ({irrev.replace('_', ' ')}): "
                    f"{self.consequence_for(action)} "
                    "Nothing runs until you approve."
                ),
                rule_id="irreversible_needs_approval",
                risk=risk,
            )
        # Persona capability envelope. Runs after the hard gates above, so a
        # persona can never override emergency pause, blocked tools, or the
        # destructive double-confirmation. It runs before the approval tiers:
        # a denied capability is denied outright, never waived by a tier or
        # an approval. (Adapted from OpenDots' per-run permission check,
        # src/server/dot-agent.ts, which aborts the run on permission drift.)
        persona_decision = self._check_persona(action, persona, risk)
        if persona_decision is not None:
            return persona_decision
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
                and not self.is_destructive(action)
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
            and not self.is_destructive(action)
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

    def _check_persona(
        self,
        action: AgentAction,
        persona: AgentPersona | dict | None,
        risk: RiskClass,
    ) -> PolicyDecision | None:
        """Enforce the persona capability envelope. Returns a DENY decision or None."""
        if persona is None:
            return None
        p = persona_from_dict(persona)
        tool = action.tool_name.lower()
        if tool in p.denied_tools:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason=f"Tool '{action.tool_name}' is denied by the active persona.",
                rule_id="persona_denied_tool",
                risk=risk,
            )
        if p.allowed_tools and tool not in p.allowed_tools:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason=f"Tool '{action.tool_name}' is not granted by the active persona.",
                rule_id="persona_not_granted",
                risk=risk,
            )
        if tool in RESEARCH_TOOLS and not p.research_allowed:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason=f"Tool '{action.tool_name}' needs research capability; the active persona has research disabled.",
                rule_id="persona_research_disabled",
                risk=risk,
            )
        if tool in MEMORY_TOOLS and not p.memory_allowed:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason=f"Tool '{action.tool_name}' needs memory capability; the active persona has memory disabled.",
                rule_id="persona_memory_disabled",
                risk=risk,
            )
        return None

    # -- compatibility wrappers ----------------------------------------------
    def can_execute(
        self,
        action: AgentAction,
        profile: UserProfile,
        approved: bool = False,
        double_confirmed: bool = False,
        persona: AgentPersona | dict | None = None,
    ) -> tuple[bool, str]:
        decision = self.decide(action, profile, approved, double_confirmed, persona)
        return decision.outcome == PolicyOutcome.ALLOW, decision.reason

    def cloud_allowed(self, grants: list[ConsentGrant], explicit_approval: bool, trusted_mode: bool = False) -> bool:
        """Cloud escalation gate with the explicit fallback policy.

        local_only: never. cloud_allowed: explicit approval or trusted mode.
        ask_each_time: explicit approval only; trusted mode cannot waive it.
        """
        for g in grants:
            if g.revoked_at is not None:
                continue
            if g.model_access_level == ModelAccessLevel.LOCAL_ONLY:
                continue
            if g.model_access_level == ModelAccessLevel.ASK_EACH_TIME:
                if explicit_approval:
                    return True
            elif explicit_approval or trusted_mode:
                return True
        return False

    # -- data-bound cloud egress authorization -------------------------------
    def authorize_cloud_context(
        self,
        results: list,
        *,
        provider: str,
        purpose: str,
        grants: list[ConsentGrant],
    ) -> dict:
        """Per-item cloud egress authorization (audit P0: cloud privacy).

        The coarse cloud_allowed() gate answers "may this request escalate
        to cloud at all". This answers the harder question for every
        candidate memory item: "is THIS item authorized for THIS provider,
        purpose, and destination?" An item is allowed into a cloud-bound
        payload only when all of these hold:

          - it is not revoked, and
          - it is NOT flagged do_not_send_to_cloud. This flag is a hard
            privacy veto, independent of `sensitive`: no consent grant,
            approval, or trusted mode can override it, and
          - when its source names a consent grant, that grant exists, is
            active (not revoked), and is cloud-capable
            (model_access_level != "local_only").

        `results` are memory SearchResults (each carries `.item`). Returns
        an explicit manifest: provider, purpose, one decision per item
        (memory_id, source_id, allowed, reason), allowed/excluded counts,
        and the overall policy decision. Callers MUST build the cloud-bound
        context only from allowed items; the manifest is recorded in the
        audit trail so every egress is attributable.
        """
        grant_by_id = {g.id: g for g in grants}
        items = []
        allowed_ids = []
        for r in results:
            item = r.item
            memory_id = item.id
            source_id = item.source.id
            if item.revoked_at is not None:
                decision = (False, "memory item is revoked")
            elif item.do_not_send_to_cloud:
                decision = (False, "do_not_send_to_cloud flag set: never leaves the node")
            else:
                gid = item.source.consent_grant_id
                if gid is None:
                    decision = (True, "no consent grant required for this source")
                else:
                    g = grant_by_id.get(gid)
                    if g is None:
                        decision = (False, f"consent grant {gid} not found")
                    elif g.revoked_at is not None:
                        decision = (False, f"consent grant {gid} is revoked")
                    elif g.model_access_level == ModelAccessLevel.LOCAL_ONLY:
                        decision = (False, f"consent grant {gid} is local-only")
                    else:
                        decision = (
                            True,
                            f"active cloud-capable consent grant {gid} "
                            f"(purpose={g.purpose}, scope={g.scope})",
                        )
            allowed, reason = decision
            if allowed:
                allowed_ids.append(memory_id)
            items.append(
                {
                    "memory_id": memory_id,
                    "source_id": source_id,
                    "allowed": allowed,
                    "reason": reason,
                }
            )
        return {
            "provider": provider,
            "purpose": purpose,
            "policy_decision": "allow" if allowed_ids else "deny_all",
            "items": items,
            "allowed_ids": allowed_ids,
            "allowed_count": len(allowed_ids),
            "excluded_count": len(items) - len(allowed_ids),
        }

    def describe(self) -> dict:
        """Operator-readable summary of the loaded policy (no secrets)."""
        return {
            "version": self.document.get("version"),
            "blocked_tools": sorted(self.blocked_tools),
            "destructive_tools": sorted(self.destructive_tools),
            "irreversible_tools": dict(sorted(self.irreversible_tools.items())),
            "sensitive_tools": sorted(self.sensitive_tools),
            "approval_required_risks": sorted(self.approval_required_risks),
            "tool_tiers": dict(sorted(self.tool_tiers.items())),
        }
