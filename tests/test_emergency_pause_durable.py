"""Adversarial tests: durable emergency pause (audit P1).

Before: emergency_paused lived on an in-memory UserProfile, so a restart
silently disarmed the kill switch. Now the flag is persisted in the
encrypted runtime DB and restored at startup; an unreadable flag fails
closed (stays paused).

Note: these tests never importlib.reload shadow_node.main, because a
reload rebinds module globals (sessions, app) that other test modules
hold references to.
"""
import sqlite3

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


def _mkstore(tmp_path):
    from shadow_node.runtime_store import EncryptedRuntimeStore
    return EncryptedRuntimeStore(str(tmp_path / "rt.db"), key=Fernet.generate_key())


@pytest.fixture
def live(monkeypatch, tmp_path):
    """The real app with its runtime-DB globals pointed at a tmp store."""
    import shadow_node.main as m
    from shadow_node.runtime_store import EncryptedRuntimeStore
    store = EncryptedRuntimeStore(str(tmp_path / "rt.db"), key=Fernet.generate_key())
    monkeypatch.setattr(m, "_runtime_db", str(tmp_path / "rt.db"))
    monkeypatch.setattr(m, "_runtime_store", store, raising=False)
    monkeypatch.setattr(m, "AUTH_REQUIRED", False)
    paused_before = m.profile.emergency_paused
    m.profile.emergency_paused = False
    yield TestClient(m.app), m, store
    m.profile.emergency_paused = paused_before


def test_pause_flag_roundtrip(tmp_path):
    from shadow_node.runtime_store import save_pause_flag, load_pause_flag
    store = _mkstore(tmp_path)
    assert load_pause_flag(store) is False  # never paused
    save_pause_flag(store, True)
    assert load_pause_flag(store) is True
    save_pause_flag(store, False)
    assert load_pause_flag(store) is False


def test_endpoint_persists_pause_flag(live):
    """POST /emergency_pause writes through to the runtime DB, which is
    exactly what startup reads back via load_pause_flag."""
    from shadow_node.runtime_store import load_pause_flag
    client, m, store = live
    r = client.post("/emergency_pause", json={"paused": True, "reason": "runaway agent"})
    assert r.json()["paused"] is True
    assert load_pause_flag(store) is True
    assert m.profile.emergency_paused is True


def test_endpoint_persists_resume(live):
    from shadow_node.runtime_store import load_pause_flag
    client, m, store = live
    client.post("/emergency_pause", json={"paused": True, "reason": "t"})
    client.post("/emergency_pause", json={"paused": False, "reason": "all clear"})
    assert load_pause_flag(store) is False
    assert m.profile.emergency_paused is False


def test_startup_restore_path_uses_persisted_value(tmp_path):
    """Simulates the startup line `profile.emergency_paused =
    load_pause_flag(_runtime_store)`: a paused flag written by a previous
    process is honored by the next one."""
    from shadow_node.runtime_store import save_pause_flag, load_pause_flag
    s1 = _mkstore(tmp_path)
    save_pause_flag(s1, True)
    # "restart": a fresh store object over the same DB file
    from shadow_node.runtime_store import EncryptedRuntimeStore
    s2 = EncryptedRuntimeStore(str(tmp_path / "rt.db"), key=s1.key)
    assert load_pause_flag(s2) is True


def test_corrupt_flag_fails_closed(tmp_path):
    """A tampered/unreadable pause row must not silently disarm the switch:
    startup stays paused."""
    from shadow_node.runtime_store import load_pause_flag
    store = _mkstore(tmp_path)
    conn = sqlite3.connect(str(tmp_path / "rt.db"))
    conn.execute("INSERT INTO runtime(collection, id, ciphertext) VALUES(?,?,?)",
                 ("safety", "emergency_pause", b"not-valid-ciphertext"))
    conn.commit()
    conn.close()
    assert load_pause_flag(store) is True
