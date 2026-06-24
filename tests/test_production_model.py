"""RC tests for the real-model provider seam and persistent encrypted memory."""
import importlib, os, tempfile, uuid
import pytest
from fastapi.testclient import TestClient

from shadow_node.model_providers import ModelProviderConfig, AnthropicProvider, LocalMockModel
from shadow_node.crypto_config import load_fernet_key
from memory_engine import EncryptedMemoryStore, MemoryEngine, MemorySource


def _client():
    import shadow_node.main as m
    importlib.reload(m)
    return TestClient(m.app), m


def test_default_provider_is_local_mock(monkeypatch):
    for k in ["SHADOW_CLOUD_ENABLED", "SHADOW_MODEL_PROVIDER", "ANTHROPIC_API_KEY"]:
        monkeypatch.delenv(k, raising=False)
    cfg = ModelProviderConfig()
    assert cfg.provider == "local_mock"
    assert cfg.cloud_model_ready() is False
    assert cfg.cloud_model() is None


def test_cloud_model_requires_enabled_provider_and_key(monkeypatch):
    monkeypatch.setenv("SHADOW_CLOUD_ENABLED", "true")
    monkeypatch.setenv("SHADOW_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("SHADOW_MODEL_API_KEY_ENV", "ANTHROPIC_API_KEY")
    # No key yet -> not ready.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ModelProviderConfig().cloud_model_ready() is False
    # With key -> ready and constructs a real provider.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    cfg = ModelProviderConfig()
    assert cfg.cloud_model_ready() is True
    model = cfg.cloud_model()
    assert isinstance(model, AnthropicProvider)
    assert model.model_name == cfg.model_name


def test_safe_summary_keeps_legacy_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    summary = ModelProviderConfig().safe_summary()
    assert {"cloud_enabled", "provider", "endpoint_configured", "api_key_configured"} <= set(summary)
    assert summary["api_key_configured"] is False
    assert "model_name" in summary and "cloud_model_ready" in summary


def test_ask_stays_local_without_cloud(monkeypatch):
    for k in ["SHADOW_CLOUD_ENABLED", "ANTHROPIC_API_KEY", "SHADOW_MEMORY_DB"]:
        monkeypatch.delenv(k, raising=False)
    client, _ = _client()
    r = client.post("/agent/ask", json={"prompt": "what is in memory?"})
    assert r.status_code == 200
    body = r.json()
    assert body["model_used"] == "local_mock"
    assert body["cloud_allowed"] is False
    assert body["untrusted_context"] is True


def test_cloud_model_error_falls_back_to_local(monkeypatch):
    # Configure a "ready" cloud provider whose endpoint will fail, plus an active
    # cloud grant + approval, and confirm the node degrades to the local model.
    monkeypatch.setenv("SHADOW_CLOUD_ENABLED", "true")
    monkeypatch.setenv("SHADOW_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-unreachable")
    monkeypatch.setenv("SHADOW_MODEL_ENDPOINT", "http://127.0.0.1:9/none")
    monkeypatch.delenv("SHADOW_MEMORY_DB", raising=False)
    client, _ = _client()
    client.post("/consent", json={"data_source": "docs", "scope": "selected", "purpose": "answer", "model_access_level": "cloud_redacted"})
    r = client.post("/agent/ask", json={"prompt": "summarize", "allow_cloud": True, "cloud_approval": True})
    assert r.status_code == 200
    assert r.json()["model_used"] == "local_mock"  # degraded gracefully


def test_persistent_memory_survives_reopen_with_stable_key(monkeypatch, tmp_path):
    db = str(tmp_path / "mem.db")
    monkeypatch.setenv("SHADOW_MEMORY_KEY_FILE", str(tmp_path / "memory.key"))
    key = load_fernet_key("SHADOW_MEMORY_KEY", "SHADOW_MEMORY_KEY_FILE", str(tmp_path / "memory.key"))
    eng = MemoryEngine(EncryptedMemoryStore(path=db, key=key))
    eng.ingest("Project Alpha uses encrypted local memory.", MemorySource(kind="manual", title="notes"))
    # Reopen with the same stable key -> data is still readable.
    key2 = load_fernet_key("SHADOW_MEMORY_KEY", "SHADOW_MEMORY_KEY_FILE", str(tmp_path / "memory.key"))
    assert key2 == key
    eng2 = MemoryEngine(EncryptedMemoryStore(path=db, key=key2))
    assert any("Alpha" in r.item.text for r in eng2.search("Alpha", 5))
