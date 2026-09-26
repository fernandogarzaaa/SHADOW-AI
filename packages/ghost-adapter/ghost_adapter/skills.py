"""Skill registry: an extensible capability layer over the action executor.

Adapted from GHOST-Chimera's ``ghostchimera.skill_layer``.

A skill is a named capability that declares the actions it handles, a human
readable description, and its requirements (environment variables, binaries).
The registry is the discovery surface: new capabilities register as skills
without changing the executor. Execution itself stays on
:class:`LocalActionExecutor`, which owns the approval gate and consent
logic, so behavior is unchanged.

Each executor tool is registered as a skill here, which makes the full tool
set discoverable (name, description, consent requirement, readiness) and
gives future skills a pattern to follow.
"""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import Any


class Skill(ABC):
    """A named capability that handles one or more actions."""

    name: str = "base"
    description: str = "Base skill"
    actions: Iterable[str] = ()
    version: str = "0.0.0"
    requires_env: list[str] = []
    requires_bins: list[str] = []
    primary_env: str = ""

    @abstractmethod
    def run(self, action: str, params: dict[str, Any]) -> Any:
        """Perform the action and return a result."""

    def check_requirements(self) -> list[str]:
        """Return human-readable descriptions of unmet requirements."""

        problems: list[str] = []
        for var in self.requires_env:
            if not os.environ.get(var):
                problems.append(
                    f"Environment variable '{var}' is not set (required by skill '{self.name}')"
                )
        for binary in self.requires_bins:
            if shutil.which(binary) is None:
                problems.append(f"Binary '{binary}' not found on PATH (required by skill '{self.name}')")
        return problems

    @property
    def ready(self) -> bool:
        """True when every declared requirement is satisfied."""

        return not self.check_requirements()


class ExecutorToolSkill(Skill):
    """A skill that delegates to one LocalActionExecutor tool.

    Note: this bypasses the executor's per-tool consent gate. Consent
    enforcement lives in ``LocalActionExecutor.run``; always execute
    through the executor in production paths.
    """

    def __init__(
        self,
        name: str,
        description: str,
        action: str,
        handler: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        needs_explicit_consent: bool = False,
        requires_env: list[str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.actions = (action,)
        self.version = "1.0.0"
        self.requires_env = requires_env or []
        self._handler = handler
        self.needs_explicit_consent = needs_explicit_consent

    def run(self, action: str, params: dict[str, Any]) -> Any:
        if action not in self.actions:
            raise KeyError(f"skill '{self.name}' cannot handle action '{action}'")
        return self._handler(params)


class SkillRegistry:
    """Discover and expose skills by name and by action."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"skill '{skill.name}' is already registered")
        self._skills[skill.name] = skill

    def get_skill(self, name: str) -> Skill:
        try:
            return self._skills[name]
        except KeyError:
            raise KeyError(f"unknown skill: {name}") from None

    def list_skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    def skill_for_action(self, action: str) -> Skill:
        for skill in self._skills.values():
            if action in skill.actions:
                return skill
        raise KeyError(f"no skill handles action: {action}")

    def describe(self) -> list[dict[str, Any]]:
        """Metadata for every skill, including readiness and consent."""

        return [
            {
                "name": s.name,
                "description": s.description,
                "actions": sorted(s.actions),
                "version": s.version,
                "ready": s.ready,
                "unmet_requirements": s.check_requirements(),
                "needs_explicit_consent": bool(getattr(s, "needs_explicit_consent", False)),
            }
            for s in sorted(self._skills.values(), key=lambda s: s.name)
        ]


def build_default_registry(executor: Any) -> SkillRegistry:
    """Register every executor tool as a skill. Additive; executor untouched."""

    registry = SkillRegistry()
    consent_required: set[str] = getattr(executor, "CONSENT_REQUIRED", set())
    handlers: dict[str, Callable] = getattr(executor, "handlers", {})

    def describe_tool(action: str) -> str:
        doc = getattr(handlers[action], "__doc__", "") or ""
        first_line = doc.strip().split("\n")[0] if doc.strip() else ""
        return first_line or f"Perform {action}."

    for action in sorted(handlers):
        handler = handlers[action]

        def _run(params: dict[str, Any], _h: Callable = handler) -> dict[str, Any]:
            return _h(params or {})

        skill_name = action.replace(".", "_")
        # web.search has a working default (localhost SearXNG); the env var
        # only overrides it, so it is not a hard requirement.
        registry.register(
            ExecutorToolSkill(
                name=skill_name,
                description=describe_tool(action),
                action=action,
                handler=_run,
                needs_explicit_consent=action in consent_required,
            )
        )
    return registry


__all__ = [
    "ExecutorToolSkill",
    "Skill",
    "SkillRegistry",
    "build_default_registry",
]
