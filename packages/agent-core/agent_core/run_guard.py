"""Live permission re-check with abort on drift.

Adapted from OpenDots' ``DotAgent`` (``src/server/dot-agent.ts``, MIT (c)
Atai Barkai): a ``check()`` closure re-reads settings and the Dot row on
every tool execution and on a 100 ms interval, with a 90 s backstop; any
drift (paused, research/memory toggled, space grants changed, dot deleted)
calls ``abortRun()``.

SHADOW mapping: the "Dot row + settings" becomes agent-core's permission
triple: the profile's emergency pause, the persona capability envelope
(backlog #5), and the policy document. OpenDots' booleans map to SHADOW
risk classes like this:

- ``emergency_paused``: aborts everything, all risk classes.
- ``persona.research_allowed``: gates research tools (``web.search``,
  ``http.get``); drift aborts runs that may use them.
- ``persona.memory_allowed``: gates memory tools (notes, reminders,
  artifacts); drift aborts runs that may use them.
- ``persona.allowed_tools`` / ``denied_tools``: the explicit grant table;
  any change aborts.
- ``policy.fingerprint``: the policy document (blocked / destructive /
  sensitive lists, approval tiers); any change aborts.

A :class:`RunGuard` snapshots this triple when a run starts (the baseline
is plain data, so it can ride along in a persisted checkpoint across
process restarts). :meth:`RunGuard.check` re-reads live state and raises
:class:`PermissionDriftError` naming every drifted permission. Call it
before every step of a multi-step run; SHADOW's per-action policy gate
already re-evaluates each action, this guard catches changes *between*
actions.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

#: Human-readable risk impact per permission key, used in drift errors.
RISK_IMPACT = {
    "emergency_paused": "all risk classes (emergency pause)",
    "persona.research_allowed": "research tools (web.search, http.get)",
    "persona.memory_allowed": "memory tools (notes, reminders, artifacts)",
    "persona.allowed_tools": "explicit tool grant table",
    "persona.denied_tools": "explicit tool deny table",
    "policy.fingerprint": "policy document (blocked/destructive/sensitive lists, tiers)",
}


class PermissionDriftError(RuntimeError):
    """Permissions changed mid-run. The run must abort, not continue."""

    def __init__(self, drifted: list[str]):
        self.drifted = drifted
        impacts = "; ".join(
            f"{k} affects {RISK_IMPACT.get(k, 'unknown')}" for k in drifted
        )
        super().__init__(f"permission drift detected, aborting run: {impacts}")


def _policy_fingerprint(document: Any) -> str:
    blob = json.dumps(document, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


class RunGuard:
    """Snapshot-and-recheck guard for one run's permission triple."""

    def __init__(self, core: Any, baseline: dict[str, Any] | None = None):
        self._core = core
        self.baseline = baseline if baseline is not None else self.snapshot(core)

    @staticmethod
    def snapshot(core: Any) -> dict[str, Any]:
        """Read the live permission triple from an AgentCore."""
        persona = core.persona
        return {
            "emergency_paused": bool(core.profile.emergency_paused),
            "persona.research_allowed": bool(persona.research_allowed),
            "persona.memory_allowed": bool(persona.memory_allowed),
            "persona.allowed_tools": sorted(persona.allowed_tools),
            "persona.denied_tools": sorted(persona.denied_tools),
            "policy.fingerprint": _policy_fingerprint(core.policy.document),
        }

    def check(self) -> None:
        """Re-read live permissions; raise PermissionDriftError on any drift."""
        current = self.snapshot(self._core)
        drifted = [k for k in current if current[k] != self.baseline.get(k)]
        if drifted:
            raise PermissionDriftError(drifted)
