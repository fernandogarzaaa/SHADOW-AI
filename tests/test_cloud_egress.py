"""Adversarial tests: data-bound cloud egress (audit P0: cloud privacy).

The ask pipeline used to build the cloud-bound context from every memory
hit, so an item with `sensitive=false, do_not_send_to_cloud=true` leaked
to the provider. Worse, the HybridRouter reground retry re-sent the FULL
raw context, bypassing even the AXIOM redaction. These tests pin the fix:

  - per-item authorization: do_not_send_to_cloud is a hard veto that no
    grant, approval, or trusted mode can override;
  - the frontier provider only ever receives the authorized cloud context,
    on both the first send and the reground retry;
  - every cloud egress carries an explicit per-item manifest.
"""

from types import SimpleNamespace

from cryptography.fernet import Fernet

from agent_core import PolicyEngine
from agent_core.models import ConsentGrant
from memory_engine import EncryptedMemoryStore, MemoryEngine
from memory_engine.models import MemoryItem, MemorySource, SearchResult
from shadow_node.hybrid import HybridRouter
from shadow_node.model_providers import LocalMockModel


# -- fixtures ---------------------------------------------------------------

def _item(text, do_not_send_to_cloud=False, sensitive=False, grant_id=None,
          revoked=False):
    from datetime import datetime, timezone
    src = MemorySource(kind="manual", title="test source",
                       consent_grant_id=grant_id)
    return MemoryItem(text=text, source=src, sensitive=sensitive,
                      do_not_send_to_cloud=do_not_send_to_cloud,
                      revoked_at=(datetime.now(timezone.utc) if revoked else None))


def _result(item):
    return SearchResult(item=item, score=1.0, freshness=1.0,
                        attribution="test", explanation="test")


def _grant(grant_id, model_access_level="cloud", revoked=False):
    from datetime import datetime, timezone
    return ConsentGrant(id=grant_id, data_source="manual",
                        scope="memory", purpose="answer_user_question",
                        model_access_level=model_access_level,
                        revoked_at=(datetime.now(timezone.utc) if revoked else None))


def _policy():
    return PolicyEngine()


# -- per-item authorization ----------------------------------------------------

def test_do_not_send_to_cloud_is_hard_veto_even_when_not_sensitive():
    """The audit's core case: sensitive=false, do_not_send_to_cloud=true
    must never appear in a provider payload."""
    policy = _policy()
    grant = _grant("g1")
    results = [_result(_item("my secret diary", do_not_send_to_cloud=True,
                             sensitive=False, grant_id="g1"))]
    manifest = policy.authorize_cloud_context(
        results, provider="anthropic", purpose="answer_user_question",
        grants=[grant])
    assert manifest["policy_decision"] == "deny_all"
    assert manifest["allowed_ids"] == []
    assert manifest["excluded_count"] == 1
    entry = manifest["items"][0]
    assert entry["allowed"] is False
    assert "do_not_send_to_cloud" in entry["reason"]


def test_plain_item_allowed_without_grant_requirement():
    policy = _policy()
    results = [_result(_item("public project notes"))]
    manifest = policy.authorize_cloud_context(
        results, provider="anthropic", purpose="answer_user_question", grants=[])
    assert manifest["policy_decision"] == "allow"
    assert manifest["allowed_count"] == 1 and manifest["excluded_count"] == 0
    assert manifest["items"][0]["allowed"] is True


def test_revoked_item_never_egresses():
    policy = _policy()
    results = [_result(_item("old notes", revoked=True))]
    manifest = policy.authorize_cloud_context(
        results, provider="anthropic", purpose="answer_user_question", grants=[])
    assert manifest["allowed_ids"] == []
    assert "revoked" in manifest["items"][0]["reason"]


def test_grant_bound_items_follow_their_grant():
    policy = _policy()
    grants = [_grant("cloud-ok"), _grant("local-only", model_access_level="local_only"),
              _grant("revoked", revoked=True)]
    results = [
        _result(_item("a", grant_id="cloud-ok")),
        _result(_item("b", grant_id="local-only")),
        _result(_item("c", grant_id="revoked")),
        _result(_item("d", grant_id="missing")),
    ]
    manifest = policy.authorize_cloud_context(
        results, provider="openai", purpose="answer_user_question", grants=grants)
    by_text = {r.item.text: e for r, e in zip(results, manifest["items"])}
    assert by_text["a"]["allowed"] is True
    assert by_text["b"]["allowed"] is False and "local-only" in by_text["b"]["reason"]
    assert by_text["c"]["allowed"] is False and "revoked" in by_text["c"]["reason"]
    assert by_text["d"]["allowed"] is False and "not found" in by_text["d"]["reason"]
    assert manifest["allowed_count"] == 1 and manifest["excluded_count"] == 3


def test_manifest_is_explicit_and_attributable():
    policy = _policy()
    item = _item("notes")
    manifest = policy.authorize_cloud_context(
        [_result(item)], provider="anthropic",
        purpose="answer_user_question", grants=[])
    assert manifest["provider"] == "anthropic"
    assert manifest["purpose"] == "answer_user_question"
    entry = manifest["items"][0]
    assert entry["memory_id"] == item.id
    assert entry["source_id"] == item.source.id
    assert set(entry) == {"memory_id", "source_id", "allowed", "reason"}


# -- memory integration: flagged text never reaches the cloud context --------

def test_flagged_memory_never_enters_cloud_context(tmp_path):
    engine = MemoryEngine(EncryptedMemoryStore(
        path=str(tmp_path / "mem.db"), key=Fernet.generate_key()))
    engine.ingest("aurora project status is green",
                  MemorySource(kind="manual", title="project"))
    engine.ingest("aurora secret diary entry, keep local",
                  MemorySource(kind="manual", title="diary"),
                  sensitive=False, do_not_send_to_cloud=True)

    results = engine.search("aurora", 5, include_sensitive=False)
    assert len(results) == 2  # both retrieved locally: local use is fine

    # exactly what _run_ask_pipeline does with the manifest
    manifest = _policy().authorize_cloud_context(
        results, provider="anthropic", purpose="answer_user_question", grants=[])
    cloud_results = [r for r in results if r.item.id in manifest["allowed_ids"]]
    cloud_context = "\n".join(r.item.text for r in cloud_results)

    assert "secret diary" not in cloud_context
    assert "project status is green" in cloud_context
    assert manifest["excluded_count"] == 1


# -- HybridRouter egress boundary ----------------------------------------------

class _Frontier:
    name = "fake_frontier"
    def __init__(self):
        self.contexts = []
    def complete(self, prompt, context=""):
        self.contexts.append(context)
        return "FRONTIER_ANSWER"


def _router(route="frontier"):
    h = HybridRouter(
        LocalMockModel(),
        axiom=SimpleNamespace(
            package_context=lambda text: {"context": text}),
        router=SimpleNamespace(
            decide=lambda prompt, tokens, frontier_available, threshold:
                   SimpleNamespace(route=route, reason="test", complexity=0.9)),
        verifier=SimpleNamespace(score=lambda answer, context: 1.0),
    )
    return h


def test_frontier_never_sees_unauthorized_context():
    frontier = _Frontier()
    h = _router()
    raw = "PUBLIC NOTES. SECRET_DIARY_ENTRY_DO_NOT_SEND."
    out = h.run("summarize", raw, frontier=frontier,
                cloud_context="PUBLIC NOTES.")
    assert out["route"] == "frontier"
    assert frontier.contexts, "frontier was never called"
    for ctx in frontier.contexts:
        assert "SECRET_DIARY_ENTRY_DO_NOT_SEND" not in ctx
    assert any("PUBLIC NOTES." in ctx for ctx in frontier.contexts)


def test_reground_retry_uses_authorized_context_only():
    """The reground path previously re-sent the full raw context to the
    provider, bypassing authorization. Force a reground with a verifier
    that always scores 0 and prove the retry only saw authorized text."""
    frontier = _Frontier()
    h = HybridRouter(
        LocalMockModel(),
        axiom=SimpleNamespace(
            package_context=lambda text: {"context": text}),
        router=SimpleNamespace(
            decide=lambda prompt, tokens, frontier_available, threshold:
                   SimpleNamespace(route="frontier", reason="test", complexity=0.9)),
        verifier=SimpleNamespace(score=lambda answer, context: 0.0),
    )
    out = h.run("summarize", "PUBLIC. SECRET_DIARY_ENTRY_DO_NOT_SEND.",
                frontier=frontier, cloud_context="PUBLIC.",
                verify=True, grounding_threshold=0.3)
    assert out["regrounded"] is True
    assert len(frontier.contexts) == 2  # first send + reground retry
    for ctx in frontier.contexts:
        assert "SECRET_DIARY_ENTRY_DO_NOT_SEND" not in ctx


def test_cloud_context_defaults_to_raw_for_caller_supplied_context():
    """MCP tools pass caller-supplied context with no memory flags; the
    default keeps their behavior unchanged."""
    frontier = _Frontier()
    h = _router()
    out = h.run("summarize", "caller supplied context", frontier=frontier)
    assert out["route"] == "frontier"
    assert frontier.contexts == ["caller supplied context"]


def test_local_path_unaffected_by_egress_boundary():
    frontier = _Frontier()
    h = _router(route="local")
    out = h.run("summarize", "raw context here", frontier=frontier,
                cloud_context="authorized only")
    assert out["route"] == "local"
    assert frontier.contexts == []


def test_memory_search_endpoint_excludes_sensitive_by_default():
    """Adversarial: /memory/search must not leak sensitive items unless the
    caller explicitly opts in with include_sensitive=true."""
    from fastapi.testclient import TestClient
    import shadow_node.main as main
    main.AUTH_REQUIRED = False
    client = TestClient(main.app)
    client.post('/memory/ingest',
                json={'text': 'sensitive default probe api key',
                      'source_title': 'probe'})
    # no explicit flag: sensitive item must be withheld
    default_hits = client.get('/memory/search',
                              params={'q': 'sensitive default probe'}).json()
    assert default_hits == []
    # explicit opt-in: sensitive item returned
    optin_hits = client.get('/memory/search',
                            params={'q': 'sensitive default probe',
                                    'include_sensitive': 'true'}).json()
    assert len(optin_hits) == 1
    assert 'api key' in optin_hits[0]['item']['text']
