"""Tests for HMAC-derived per-device credentials (OpenDots backlog #6).

Covers: determinism, per-device uniqueness, the exact derivation
format, wrong-master / tampered-token rejection, fail-closed behavior,
constant-time comparison, version rotation, master-secret lifecycle,
and the /pair/confirm integration (derived token returned, nothing
stored per device, token authenticates requests).
"""
import hashlib
import hmac
import os
import stat
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent_core import sign_request
from shadow_node.device_credentials import (
    DEVICE_TOKEN_VERSION,
    derive_device_token,
    load_master_secret,
    token_scheme_for_version,
    verify_device_token,
    version_from_scheme,
)

TEST_MASTER = bytes.fromhex("aa" * 32)
OTHER_MASTER = bytes.fromhex("bb" * 32)


# ---------------------------------------------------------------------------
# Unit: derivation and verification
# ---------------------------------------------------------------------------

def test_derivation_is_deterministic():
    assert derive_device_token(TEST_MASTER, "dev-1") == derive_device_token(TEST_MASTER, "dev-1")


def test_derivation_is_per_device_unique():
    assert derive_device_token(TEST_MASTER, "dev-1") != derive_device_token(TEST_MASTER, "dev-2")


def test_derivation_depends_on_master():
    assert derive_device_token(TEST_MASTER, "dev-1") != derive_device_token(OTHER_MASTER, "dev-1")


def test_derivation_format_matches_spec():
    # token == HMAC-SHA256(master, "shadow-device:v1:<device_id>"), hex
    expected = hmac.new(TEST_MASTER, b"shadow-device:v1:dev-1", hashlib.sha256).hexdigest()
    assert derive_device_token(TEST_MASTER, "dev-1") == expected
    assert len(expected) == 64


def test_verify_accepts_correct_token():
    token = derive_device_token(TEST_MASTER, "dev-1")
    assert verify_device_token(TEST_MASTER, "dev-1", token) is True


def test_verify_rejects_wrong_master():
    token = derive_device_token(TEST_MASTER, "dev-1")
    assert verify_device_token(OTHER_MASTER, "dev-1", token) is False


def test_verify_rejects_tampered_token():
    token = derive_device_token(TEST_MASTER, "dev-1")
    tampered = ("0" if token[0] != "0" else "1") + token[1:]
    assert tampered != token
    assert verify_device_token(TEST_MASTER, "dev-1", tampered) is False


def test_verify_rejects_wrong_device():
    token = derive_device_token(TEST_MASTER, "dev-1")
    assert verify_device_token(TEST_MASTER, "dev-2", token) is False


def test_verify_fails_closed_on_bad_inputs():
    assert verify_device_token(b"", "dev-1", "x") is False
    assert verify_device_token(TEST_MASTER, "", "x") is False
    assert verify_device_token(TEST_MASTER, "dev-1", "") is False
    assert verify_device_token(TEST_MASTER, "dev-1", None) is False  # type: ignore[arg-type]
    assert verify_device_token(None, "dev-1", "x") is False  # type: ignore[arg-type]


def test_derive_rejects_empty_inputs():
    with pytest.raises(ValueError):
        derive_device_token(b"", "dev-1")
    with pytest.raises(ValueError):
        derive_device_token(TEST_MASTER, "")


def test_verify_uses_constant_time_compare():
    token = derive_device_token(TEST_MASTER, "dev-1")
    with patch("shadow_node.device_credentials.hmac.compare_digest",
               wraps=hmac.compare_digest) as spy:
        assert verify_device_token(TEST_MASTER, "dev-1", token) is True
        assert verify_device_token(TEST_MASTER, "dev-1", "0" * 64) is False
    assert spy.call_count == 2


def test_version_rotation_changes_output_and_invalidates_old():
    v1 = derive_device_token(TEST_MASTER, "dev-1", version=1)
    v2 = derive_device_token(TEST_MASTER, "dev-1", version=2)
    assert v1 != v2
    # Old token does not verify under the new version (fail closed, re-pair).
    assert verify_device_token(TEST_MASTER, "dev-1", v1, version=2) is False
    assert verify_device_token(TEST_MASTER, "dev-1", v2, version=2) is True


def test_scheme_helpers():
    assert token_scheme_for_version(1) == "hmac-v1"
    assert token_scheme_for_version(2) == "hmac-v2"
    assert version_from_scheme("hmac-v1") == 1
    assert version_from_scheme("hmac-v12") == 12
    assert version_from_scheme("stored") is None
    assert version_from_scheme("hmac-x") is None
    assert version_from_scheme("") is None


# ---------------------------------------------------------------------------
# Unit: master secret lifecycle
# ---------------------------------------------------------------------------

def test_master_from_hex_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SHADOW_MASTER_SECRET", "cc" * 32)
    monkeypatch.delenv("SHADOW_MASTER_SECRET_FILE", raising=False)
    assert load_master_secret() == bytes.fromhex("cc" * 32)


def test_master_from_raw_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SHADOW_MASTER_SECRET", "a-long-enough-passphrase-value")
    monkeypatch.delenv("SHADOW_MASTER_SECRET_FILE", raising=False)
    assert load_master_secret() == b"a-long-enough-passphrase-value"


def test_master_empty_env_raises(monkeypatch):
    monkeypatch.setenv("SHADOW_MASTER_SECRET", "   ")
    with pytest.raises(RuntimeError):
        load_master_secret()


def test_master_generated_and_persisted_with_0600(monkeypatch, tmp_path):
    key_file = tmp_path / "keys" / "master.key"
    monkeypatch.delenv("SHADOW_MASTER_SECRET", raising=False)
    monkeypatch.setenv("SHADOW_MASTER_SECRET_FILE", str(key_file))
    first = load_master_secret()
    assert len(first) == 32
    assert key_file.exists()
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    # Stable across loads: never regenerated while the file exists.
    assert load_master_secret() == first


def test_master_prefers_env_over_file(monkeypatch, tmp_path):
    key_file = tmp_path / "master.key"
    key_file.write_bytes(b"file-secret-value-ignored")
    monkeypatch.setenv("SHADOW_MASTER_SECRET", "dd" * 32)
    monkeypatch.setenv("SHADOW_MASTER_SECRET_FILE", str(key_file))
    assert load_master_secret() == bytes.fromhex("dd" * 32)


# ---------------------------------------------------------------------------
# Integration: pairing ceremony + request auth
# ---------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch):
    import shadow_node.main as m
    # Pin a fixed master so derivation is deterministic in tests.
    monkeypatch.setattr(m, "_MASTER_SECRET", TEST_MASTER)
    monkeypatch.setattr(m.sessions, "master_secret", TEST_MASTER)
    monkeypatch.setattr(m, "AUTH_REQUIRED", True)
    dev_snap = dict(m.sessions.devices)
    sec_snap = dict(m.sessions.secrets)
    pair_snap = dict(m.pairing)
    master_snap = m.sessions.master_secret
    m.sessions.devices.clear()
    m.sessions.secrets.clear()
    m.pairing.clear()
    yield TestClient(m.app), m
    m.sessions.devices.clear(); m.sessions.devices.update(dev_snap)
    m.sessions.secrets.clear(); m.sessions.secrets.update(sec_snap)
    m.pairing.clear(); m.pairing.update(pair_snap)
    m.sessions.master_secret = master_snap


def _signed(device_id, secret, method, path, body="", nonce="n1"):
    ts = int(time.time())
    return {"x-shadow-device-id": device_id, "x-shadow-nonce": nonce,
            "x-shadow-timestamp": str(ts),
            "x-shadow-signature": sign_request(secret, method, path, body, nonce, ts)}


def _pair_bootstrap_device(api):
    """First-ever device: bootstrap auto-approves, returns (device, secret)."""
    client, m = api
    pid = client.post("/pair/start",
                      json={"device_name": "Phone", "public_key": "phone-pub"}).json()["pairing_id"]
    r = client.post("/pair/confirm", json={"pairing_id": pid})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["device"], body["secret"]


def test_pair_confirm_returns_derived_token_and_stores_nothing(api):
    client, m = api
    device, secret = _pair_bootstrap_device(api)
    device_id = device["id"]
    assert device["credential_scheme"] == f"hmac-v{DEVICE_TOKEN_VERSION}"
    assert secret == derive_device_token(TEST_MASTER, device_id)
    # Stateless: no per-device secret persisted.
    assert device_id not in m.sessions.secrets


def test_derived_token_authenticates_requests(api):
    client, m = api
    device, secret = _pair_bootstrap_device(api)
    device_id = device["id"]
    r = client.get("/devices", headers=_signed(device_id, secret, "GET", "/devices"))
    assert r.status_code == 200, r.text
    # Wrong token -> 401.
    bad = _signed(device_id, "0" * 64, "GET", "/devices", nonce="n2")
    assert client.get("/devices", headers=bad).status_code == 401


def test_legacy_stored_device_still_verifies(api):
    """Pre-HMAC devices (credential_scheme "stored") keep working."""
    client, m = api
    dev = m.sessions.register("Legacy", "legacy-pub", "legacy-secret")
    assert dev.credential_scheme == "stored"
    r = client.get("/devices", headers=_signed(dev.id, "legacy-secret", "GET", "/devices"))
    assert r.status_code == 200, r.text


def test_derived_device_fails_closed_without_master(api):
    """A derived-scheme device with no master configured cannot auth."""
    client, m = api
    m.sessions.master_secret = None
    dev = m.sessions.register("Orphan", "orphan-pub", credential_scheme="hmac-v1")
    ok, reason = m.sessions.verify(dev.id, "0" * 64, "n1", str(int(time.time())),
                                   "GET", "/devices", "")
    assert ok is False
    assert reason == "unknown_device_secret"
