"""Agent persona capability envelope.

Adapted from OpenDots' specialist-Dot permission envelope
(CopilotKit/OpenDots, MIT (c) Atai Barkai: ``src/shared/types.ts`` ``Dot``,
``src/server/workspace-routes.ts`` ``dotSchema``, ``src/server/dot-agent.ts``
per-run tool assembly).

A persona is the agent's validated configuration: an identity (name,
instructions) plus capability flags and an explicit per-tool grant table.
It is validated strictly on write (pydantic ``extra="forbid"``, the analog
of zod ``.strict()``), and the :class:`PolicyEngine
<agent_core.policy.PolicyEngine>` enforces it in ``decide()`` after the hard
safety gates and before the approval tiers: a denied capability can never
be overridden by a tier, an approval, or the model.

Capability-to-tool mapping (grounded in the tools actually registered on a
Shadow Node):
- ``research_allowed`` gates :data:`RESEARCH_TOOLS` (the OpenDots analog of
  ``researchAllowed`` gating ``search_web`` / ``read_public_page``).
- ``memory_allowed`` gates :data:`MEMORY_TOOLS`, the agent's persistent-state
  surface (notes, reminders, versioned artifacts).
- ``denied_tools`` is an explicit deny list and always wins.
- ``allowed_tools``, when non-empty, makes the envelope closed-world: only
  listed tools may run.
"""
from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_NAME_LEN = 40
MAX_INSTRUCTIONS_LEN = 2000
MAX_TOOL_NAME_LEN = 64

#: Agent tools that reach the outside world for research. Gated by
#: ``research_allowed``.
RESEARCH_TOOLS = frozenset({"web.search", "http.get"})

#: Agent tools that persist state across runs (the agent's working memory).
#: Gated by ``memory_allowed``.
MEMORY_TOOLS = frozenset({
    "note.create",
    "note.append",
    "note.list",
    "reminder.create",
    "artifact_create",
    "artifact_read",
    "artifact_update",
})


class AgentPersona(BaseModel):
    """Validated capability envelope for the agent."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"persona_{uuid4().hex}")
    name: str = Field(min_length=1, max_length=MAX_NAME_LEN)
    instructions: str = Field(min_length=3, max_length=MAX_INSTRUCTIONS_LEN)
    research_allowed: bool = True
    memory_allowed: bool = True
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)

    @field_validator("name", "instructions")
    @classmethod
    def _stripped(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("allowed_tools", "denied_tools")
    @classmethod
    def _tool_names(cls, v: list[str]) -> list[str]:
        names = []
        for raw in v:
            name = str(raw).strip().lower()
            if not name or len(name) > MAX_TOOL_NAME_LEN:
                raise ValueError(f"invalid tool name: {raw!r}")
            if name not in names:
                names.append(name)
        return names

    @model_validator(mode="after")
    def _no_allow_deny_overlap(self) -> "AgentPersona":
        overlap = set(self.allowed_tools) & set(self.denied_tools)
        if overlap:
            raise ValueError(
                f"tool(s) cannot be both allowed and denied: {sorted(overlap)}"
            )
        return self


def default_persona() -> AgentPersona:
    """The permissive default: every capability on, no tool restrictions.

    With the default persona the policy engine behaves exactly as before,
    so existing deployments are unaffected until an operator configures one.
    """
    return AgentPersona(
        id="persona_default",
        name="Shadow",
        instructions="Default Shadow agent persona: all capabilities enabled.",
    )


def persona_from_dict(data: dict | AgentPersona | None) -> AgentPersona:
    """Validate raw config into an :class:`AgentPersona`.

    Raises pydantic ``ValidationError`` on any schema violation, including
    unknown fields (strict mode).
    """
    if data is None:
        return default_persona()
    if isinstance(data, AgentPersona):
        return data
    return AgentPersona.model_validate(data)
