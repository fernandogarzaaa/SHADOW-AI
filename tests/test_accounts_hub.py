"""Accounts hub (Hark item 5): uniform service directory, vault-backed credentials."""

import json

import pytest
from fastapi.testclient import TestClient
from shadow_node import accounts as accounts_mod
from shadow_node import provider_auth


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    """Fresh encrypted credential store, no env fallbacks."""
    monkeypatch.setenv("SHADOW_PROVIDERS_FILE", str(tmp_path / "p.enc"))
    monkeypatch.setenv("SHADOW_PROVIDERS_KEY_FILE", str(tmp_path / "p.key"))
    for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
        monkeypatch.delenv(k, raising=False)
    import shadow_node.main as m

    # Auth middleware is on by default (module-level AUTH_REQUIRED constant);
    # other test files flip it on the shared module and rely on file order.
    # Make these tests order-independent.
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    store = provider_auth.CredentialStore()
    monkeypatch.setattr(m, "credentials", store)
    return m, store, tmp_path


@pytest.fixture()
def client(isolated):
    m, _, _ = isolated
    return TestClient(m.app)


def test_list_accounts_uniform_rows_and_local_first_copy(client):
    data = client.get("/accounts").json()
    rows = data["accounts"]
    assert {r["id"] for r in rows} == {"anthropic", "openai", "gemini"}
    for r in rows:
        assert r["kind"] == "model_provider"
        assert r["display_name"] and r["description"]
        assert isinstance(r["auth_methods"], list) and r["auth_methods"]
        assert r["connected"] is False
        assert r["credential_type"] is None
        assert r["credential_source"] is None
        # the local-first guarantee is on every row
        assert "never leave this device" in r["local_first_note"]
        # no secret material in the shape
        assert "api_key" not in r and "oauth_token" not in r


def test_connect_stores_encrypted_and_status_updates(client, isolated):
    _, store, tmp_path = isolated
    secret = "sk-test-accounts-hub-123"
    res = client.post("/accounts/openai/connect", json={"api_key": secret})
    assert res.status_code == 200
    assert res.json() == {"connected": True, "service": "openai"}

    body = client.get("/accounts").text
    assert secret not in body
    row = next(
        r for r in client.get("/accounts").json()["accounts"] if r["id"] == "openai"
    )
    assert row["connected"] is True
    assert row["credential_type"] == "api_key"
    assert row["credential_source"] == "stored"

    # at rest the file is encrypted: the secret is not in the bytes
    raw = (tmp_path / "p.enc").read_bytes()
    assert secret.encode() not in raw
    # and a fresh store on the same files still resolves it
    fresh = provider_auth.CredentialStore(path=str(tmp_path / "p.enc"), key=store.key)
    assert fresh.get("openai")["api_key"] == secret


def test_detail_and_unknown_service(client):
    row = client.get("/accounts/gemini").json()
    assert row["id"] == "gemini"
    assert row["oauth_supported"] is True
    assert "never leave this device" in row["local_first_note"]
    assert client.get("/accounts/nope").status_code == 404


def test_connect_unknown_service_and_missing_key(client):
    assert (
        client.post("/accounts/nope/connect", json={"api_key": "x"}).status_code == 404
    )
    res = client.post("/accounts/openai/connect", json={"api_key": ""})
    assert res.status_code == 400


def test_disconnect_requires_confirm_and_is_irreversible(client):
    secret = "sk-disconnect-test"
    client.post("/accounts/openai/connect", json={"api_key": secret})

    # no confirm -> 409, still connected
    res = client.post("/accounts/openai/disconnect")
    assert res.status_code == 409
    assert client.get("/accounts/openai").json()["connected"] is True

    # confirm -> disconnected
    res = client.post("/accounts/openai/disconnect?confirm=true")
    assert res.status_code == 200
    assert res.json() == {"connected": False, "service": "openai"}
    assert client.get("/accounts/openai").json()["connected"] is False

    # idempotent
    assert client.post("/accounts/openai/disconnect?confirm=true").status_code == 200
    # unknown service -> 404 even with confirm
    assert client.post("/accounts/nope/disconnect?confirm=true").status_code == 404


def test_disconnect_wrong_method_rejected_by_scope(client):
    # runtime scope only allows POST on disconnect
    assert client.delete("/accounts/openai/disconnect").status_code in (400, 404, 405)


def test_env_fallback_shows_connected_without_secret_value(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key-abc")
    rows = {r["id"]: r for r in client.get("/accounts").json()["accounts"]}
    assert rows["openai"]["connected"] is True
    assert rows["openai"]["credential_source"] == "env"
    assert "env-key-abc" not in client.get("/accounts").text


def test_audit_events_carry_no_secret(isolated):
    m, _, _ = isolated
    c = TestClient(m.app)
    secret = "sk-audit-leak-check"
    before = len(m.audit)
    c.post("/accounts/anthropic/connect", json={"api_key": secret})
    c.post("/accounts/anthropic/disconnect?confirm=true")
    new_events = m.audit[before:]
    kinds = [e.event_type for e in new_events]
    assert "account_connected" in kinds
    assert "account_disconnected" in kinds
    blob = json.dumps([e.model_dump(mode="json") for e in new_events])
    assert secret not in blob


def test_account_row_defaults_connected_false():
    row = accounts_mod.AccountRow(id="x", display_name="X", kind="k", description="d")
    assert row.connected is False
    assert row.oauth_supported is False
    assert row.local_first_note == accounts_mod.LOCAL_FIRST_NOTE


def test_registry_unit_functions(isolated):
    _, store, _ = isolated
    assert set(accounts_mod.service_ids()) == {"anthropic", "openai", "gemini"}
    assert accounts_mod.get_account(store, "nope") is None
    with pytest.raises(KeyError):
        accounts_mod.connect_account(store, "nope", "x")
    with pytest.raises(KeyError):
        accounts_mod.disconnect_account(store, "nope")
    row = accounts_mod.connect_account(store, "gemini", "k")
    assert row.connected is True and row.id == "gemini"
    accounts_mod.disconnect_account(store, "gemini")
    assert accounts_mod.get_account(store, "gemini").connected is False
