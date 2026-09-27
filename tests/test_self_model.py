"""Self-awareness surface: 'what are you', 'where are you', 'what can you do'.

The answers are derived from live node state, not hardcoded copy, and the
ask pipeline answers these intents deterministically.
"""
from fastapi.testclient import TestClient
import pytest
from agent_core import *
from memory_engine import *
from axiom_adapter import AxiomAdapter, RedactionLayer
from ghost_adapter import GhostAdapter, GhostTaskIR
from shadow_node.main import app
from shadow_node.self_model import classify_self_intent
import shadow_node.main as main

@pytest.fixture()
def client():
    main.AUTH_REQUIRED=False
    return TestClient(app)

def test_classify_self_intent():
    assert classify_self_intent("what are you?")=="identity"
    assert classify_self_intent("Who are you")=="identity"
    assert classify_self_intent("where are you?")=="location"
    assert classify_self_intent("what can you do?")=="capabilities"
    assert classify_self_intent("what can you do for me")=="capabilities"
    assert classify_self_intent("list your capabilities.")=="capabilities"
    # Longer questions that merely contain the phrase fall through.
    assert classify_self_intent("where are you going with this plan?") is None
    assert classify_self_intent("what are your thoughts on agents?") is None
    assert classify_self_intent("remind me to buy milk") is None

def test_agent_self_endpoint(client):
    m=client.get("/agent/self").json()
    assert m["identity"]["name"]=="SHADOW"
    assert m["identity"]["version"]
    assert m["runtime"]["local_first"] is True
    assert m["runtime"]["platform"]
    assert m["capabilities"]["tool_count"]==len(m["capabilities"]["tools"])>0
    assert m["capabilities"]["memory"]["encrypted"] is True
    # No invented connectors: tools come from the live registry.
    assert "ghost_handoff" in m["capabilities"]["tools"]

def test_ask_identity(client):
    r=client.post("/agent/ask",json={"prompt":"what are you?"}).json()
    assert r["model_used"]=="self_model"
    assert "SHADOW" in r["answer"] and "local-first" in r["answer"]

def test_ask_location(client):
    r=client.post("/agent/ask",json={"prompt":"where are you?"}).json()
    assert r["model_used"]=="self_model"
    assert "Shadow Node" in r["answer"]
    assert "cloud" in r["answer"].lower()

def test_ask_capabilities(client):
    r=client.post("/agent/ask",json={"prompt":"what can you do?"}).json()
    assert r["model_used"]=="self_model"
    assert "approvals" in r["answer"].lower()

def test_ask_non_self_question_uses_normal_pipeline(client):
    r=client.post("/agent/ask",json={"prompt":"where are you going with this plan?"}).json()
    assert r["model_used"]!="self_model"

def test_self_ask_is_audited(client):
    before=len(client.get("/audit").json())
    client.post("/agent/ask",json={"prompt":"what are you?"})
    events=client.get("/audit").json()[before:]
    assert any(e["event_type"]=="agent_ask" and e.get("model_used")=="self_model" for e in events)
