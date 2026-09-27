"""Adversarial tests: OAuth transaction binding (audit P1).

The old flow handed the PKCE verifier to the client and kept no
server-side record: the exchange endpoint trusted whatever verifier and
redirect_uri the client echoed, with no state validation, no device
binding, no expiry, and reusable transactions.

Now: transactions are persisted (encrypted) and bound to
(state, device, provider, redirect_uri, verifier); the verifier never
leaves the node; exchange consumes the transaction exactly once.
"""

import json

import pytest
from cryptography.fernet import Fernet

from shadow_node import provider_auth


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-456")
    return provider_auth.OAuthTransactionStore(
        path=str(tmp_path / "txns.enc"), key=Fernet.generate_key())


class _TokenResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"access_token": "ya29.token", "refresh_token": "rt-1"}


@pytest.fixture()
def token_endpoint(monkeypatch):
    seen = {}

    def fake_post(url, data=None, timeout=None):
        seen["url"] = url
        seen["data"] = dict(data)
        return _TokenResponse()

    monkeypatch.setattr(provider_auth.httpx, "post", fake_post)
    return seen


def _start(store, provider="gemini", redirect="https://node.local/oauth/cb",
           device="dev-1"):
    return provider_auth.start_oauth(provider, redirect, device, store)


def test_exchange_happy_path_consumes_transaction(store, token_endpoint):
    res = _start(store)
    cred = provider_auth.exchange_code("gemini", res["state"], "authcode-1",
                                       "dev-1", store)
    assert cred["oauth_token"] == "ya29.token"
    # the token endpoint got the SERVER-STORED verifier and redirect_uri
    assert token_endpoint["url"] == "https://oauth2.googleapis.com/token"
    assert token_endpoint["data"]["redirect_uri"] == "https://node.local/oauth/cb"
    assert token_endpoint["data"]["code"] == "authcode-1"
    assert len(token_endpoint["data"]["code_verifier"]) > 40
    # single-use: replaying the same state fails
    with pytest.raises(ValueError, match="unknown or already-used"):
        provider_auth.exchange_code("gemini", res["state"], "authcode-1",
                                    "dev-1", store)


def test_exchange_with_unknown_state_fails(store, token_endpoint):
    with pytest.raises(ValueError, match="unknown or already-used"):
        provider_auth.exchange_code("gemini", "nope-not-a-state", "code",
                                    "dev-1", store)
    assert token_endpoint == {}  # provider never contacted


def test_exchange_bound_to_provider(store, token_endpoint):
    res = _start(store, provider="gemini")
    with pytest.raises(ValueError, match="different provider"):
        provider_auth.exchange_code("openai", res["state"], "code",
                                    "dev-1", store)


def test_exchange_bound_to_device(store, token_endpoint):
    """A second device cannot complete a flow started by the first."""
    res = _start(store, device="dev-1")
    with pytest.raises(ValueError, match="different device"):
        provider_auth.exchange_code("gemini", res["state"], "code",
                                    "dev-2", store)
    assert token_endpoint == {}


def test_expired_transaction_is_rejected(store, token_endpoint, monkeypatch):
    res = _start(store)
    # age the transaction past the TTL
    real_now = provider_auth._utcnow
    monkeypatch.setattr(provider_auth, "_utcnow",
                        lambda: real_now() + provider_auth.OAUTH_TXN_TTL_SECONDS + 1)
    with pytest.raises(ValueError, match="expired"):
        provider_auth.exchange_code("gemini", res["state"], "code",
                                    "dev-1", store)
    assert token_endpoint == {}


def test_transaction_survives_restart_but_consumed_does_not(tmp_path, monkeypatch, token_endpoint):
    """Persistence is encrypted on disk: a fresh store instance (a restart)
    sees pending transactions, but a consumed one stays consumed."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-456")
    key = Fernet.generate_key()
    path = str(tmp_path / "txns.enc")
    s1 = provider_auth.OAuthTransactionStore(path=path, key=key)
    pending = provider_auth.start_oauth("gemini", "https://node.local/cb",
                                        "dev-1", s1)
    used = provider_auth.start_oauth("gemini", "https://node.local/cb",
                                     "dev-1", s1)
    provider_auth.exchange_code("gemini", used["state"], "code", "dev-1", s1)

    s2 = provider_auth.OAuthTransactionStore(path=path, key=key)  # "restart"
    cred = provider_auth.exchange_code("gemini", pending["state"], "code",
                                       "dev-1", s2)
    assert cred["oauth_token"] == "ya29.token"
    with pytest.raises(ValueError, match="unknown or already-used"):
        provider_auth.exchange_code("gemini", used["state"], "code",
                                    "dev-1", s2)


def test_corrupt_transaction_file_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    path = tmp_path / "txns.enc"
    path.write_bytes(b"not-encrypted-json")
    store = provider_auth.OAuthTransactionStore(path=str(path),
                                                key=Fernet.generate_key())
    with pytest.raises(ValueError, match="unknown or already-used"):
        provider_auth.exchange_code("gemini", "whatever", "code",
                                    "dev-1", store)


def test_verifier_and_redirect_never_come_from_client(store, token_endpoint):
    """Even if an attacker supplies their own verifier/redirect at the
    exchange step, the server uses only the stored values. (The new API
    does not even accept them; this pins the token-call contents.)"""
    res = _start(store, redirect="https://node.local/legit-cb")
    provider_auth.exchange_code("gemini", res["state"], "attacker-code",
                                "dev-1", store)
    assert token_endpoint["data"]["redirect_uri"] == "https://node.local/legit-cb"
    assert token_endpoint["data"]["code"] == "attacker-code"  # code is theirs
    assert "attacker" not in token_endpoint["data"]["code_verifier"]


def test_sweep_removes_expired(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-123")
    store = provider_auth.OAuthTransactionStore(
        path=str(tmp_path / "t.enc"), key=Fernet.generate_key(), ttl=1)
    provider_auth.start_oauth("gemini", "https://node.local/cb", "dev-1", store)
    assert len(store._data) == 1
    real_now = provider_auth._utcnow
    monkeypatch.setattr(provider_auth, "_utcnow", lambda: real_now() + 5)
    assert store.sweep() == 1
    assert store._data == {}
    # and the file on disk agrees
    raw = json.loads(store.cipher.decrypt(store.path.read_bytes()).decode())
    assert raw == {}
