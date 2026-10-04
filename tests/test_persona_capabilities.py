"""Backlog #5: validated agent persona capability envelope.

OpenDots source: src/shared/types.ts (Dot: id/spaceId/name/instructions/
researchAllowed/memoryAllowed), src/server/workspace-routes.ts (dotSchema,
strict zod validation on write), src/server/dot-agent.ts (per-run tool
assembly), src/lib/dot-permissions.ts + src/server/runtime-scope.ts
(per-tool permission check). MIT (c) Atai Barkai.
"""
import pytest
from pydantic import ValidationError

from agent_core import (
    AgentAction,
    AgentCore,
    AgentPersona,
    PolicyEngine,
    PolicyOutcome,
    UserProfile,
    default_persona,
    persona_from_dict,
)


def act(tool, desc="test action"):
    return AgentAction(tool_name=tool, description=desc)


# --- validation (zod-strict analog) -----------------------------------------

def test_valid_persona_passes():
    p = AgentPersona(name="Researcher", instructions="Research deeply before answering.")
    assert p.research_allowed is True and p.memory_allowed is True
    assert p.allowed_tools == [] and p.denied_tools == []


def test_name_length_bounds():
    with pytest.raises(ValidationError):
        AgentPersona(name="x" * 41, instructions="ok instructions here")
    with pytest.raises(ValidationError):
        AgentPersona(name="   ", instructions="ok instructions here")


def test_instructions_length_bounds():
    with pytest.raises(ValidationError):
        AgentPersona(name="ok", instructions="ab")
    with pytest.raises(ValidationError):
        AgentPersona(name="ok", instructions="x" * 2001)


def test_strict_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AgentPersona(name="ok", instructions="valid instructions", bogus_field=True)


def test_allow_deny_overlap_rejected():
    with pytest.raises(ValidationError):
        AgentPersona(
            name="ok",
            instructions="valid instructions",
            allowed_tools=["web.search"],
            denied_tools=["web.search"],
        )


def test_tool_names_normalized():
    p = AgentPersona(
        name="ok", instructions="valid instructions", denied_tools=["  Web.Search ", "WEB.SEARCH"]
    )
    assert p.denied_tools == ["web.search"]


def test_persona_from_dict_validates():
    with pytest.raises(ValidationError):
        persona_from_dict({"name": "x" * 50, "instructions": "valid instructions"})
    p = persona_from_dict(None)
    assert isinstance(p, AgentPersona) and p.id == "persona_default"


# --- enforcement in the policy path ----------------------------------------

def restricted(**kw):
    base = {"name": "Restricted", "instructions": "A restricted test persona."}
    base.update(kw)
    return persona_from_dict(base)


def test_research_flag_gates_research_tools():
    p = PolicyEngine()
    d = p.decide(act("web.search"), UserProfile(), persona=restricted(research_allowed=False))
    assert d.outcome == PolicyOutcome.DENY and d.rule_id == "persona_research_disabled"
    d2 = p.decide(act("web.search"), UserProfile(), persona=restricted(research_allowed=True))
    assert d2.outcome != PolicyOutcome.DENY or d2.rule_id != "persona_research_disabled"
    d3 = p.decide(act("http.get"), UserProfile(), persona=restricted(research_allowed=False))
    assert d3.rule_id == "persona_research_disabled"


def test_memory_flag_gates_memory_tools():
    p = PolicyEngine()
    d = p.decide(act("note.create"), UserProfile(), persona=restricted(memory_allowed=False))
    assert d.outcome == PolicyOutcome.DENY and d.rule_id == "persona_memory_disabled"
    d2 = p.decide(act("artifact_read"), UserProfile(), persona=restricted(memory_allowed=False))
    assert d2.rule_id == "persona_memory_disabled"


def test_denied_tools_win():
    p = PolicyEngine()
    d = p.decide(act("ghost_handoff"), UserProfile(), persona=restricted(denied_tools=["ghost_handoff"]))
    assert d.outcome == PolicyOutcome.DENY and d.rule_id == "persona_denied_tool"


def test_allowed_tools_closed_world():
    p = PolicyEngine()
    persona = restricted(allowed_tools=["web.search"])
    d = p.decide(act("http.get"), UserProfile(), persona=persona)
    assert d.outcome == PolicyOutcome.DENY and d.rule_id == "persona_not_granted"


def test_persona_never_overrides_hard_gates():
    p = PolicyEngine()
    d = p.decide(act("keylogger", "hidden keylog"), UserProfile(),
                 persona=default_persona(), approved=True)
    assert d.outcome == PolicyOutcome.DENY and d.rule_id == "blocked_tool"


def test_no_persona_preserves_behavior():
    p = PolicyEngine()
    d = p.decide(act("web.search"), UserProfile())
    assert d.rule_id != "persona_research_disabled"


def test_agentcore_execute_enforces_persona():
    core = AgentCore(persona={"name": "NoResearch", "instructions": "no web research allowed",
                              "research_allowed": False})
    out = core.execute(act("web.search", "search the web"), approved=True)
    assert out["ok"] is False
    assert "research" in out["reason"]


def test_agentcore_default_persona_is_permissive():
    core = AgentCore()
    assert core.persona.id == "persona_default"
