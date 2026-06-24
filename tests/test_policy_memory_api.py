from fastapi.testclient import TestClient
from agent_core import *
from memory_engine import *
from axiom_adapter import RedactionLayer
from shadow_node.main import app
import tempfile

def test_policy_blocks_spyware():
    p=PolicyEngine(); a=AgentAction(tool_name="keylogger", description="hidden keylog")
    assert p.classify_action(a)==RiskClass.BLOCKED
    assert p.can_execute(a, UserProfile(), approved=True)[0] is False

def test_cloud_escalation_requires_grant_and_approval():
    p=PolicyEngine(); assert not p.cloud_allowed([], True)
    assert p.cloud_allowed([ConsentGrant(data_source="docs",scope="selected",purpose="answer",model_access_level="cloud_redacted")], True)

def test_memory_ingest_search_revoke():
    store=EncryptedMemoryStore(path=tempfile.NamedTemporaryFile().name); engine=MemoryEngine(store)
    items=engine.ingest("Shadow Agent remembers approved calendar preferences", MemorySource(kind="manual",title="note"))
    assert engine.search("calendar")
    store.revoke(items[0].id); assert store.get(items[0].id) is None

def test_redaction():
    assert "[EMAIL]" in RedactionLayer().redact("me@example.com")

def test_api_flow():
    c=TestClient(app); assert c.get("/health").json()["status"]=="ok"
    assert c.post("/memory/ingest",json={"text":"Project Alpha deadline is Friday"}).status_code==401
    assert c.get("/memory/search",params={"q":"Alpha"}).status_code==401
