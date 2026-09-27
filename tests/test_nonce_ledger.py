"""Nonce replay ledger: device-scoped uniqueness, expiry, and persistence.

Re-audit item: replay state was memory-only, so restarts reopened the
replay window. The node now injects a PersistentNonceLedger (encrypted
runtime DB) when SHADOW_RUNTIME_DB is set; otherwise the in-memory
ledger from agent_core is used.
"""

import tempfile
import time

from agent_core import DeviceSessionStore, InMemoryNonceLedger, MAX_SKEW_SECONDS
from shadow_node.runtime_store import (
    EncryptedRuntimeStore,
    PersistentNonceLedger,
    _NonceRow,
)


def test_in_memory_ledger_device_scoped():
    led = InMemoryNonceLedger()
    led.record("devA", "n1", time.time())
    assert led.seen("devA", "n1") is True
    # Same nonce from a different device is a different (device_id, nonce)
    # pair and must NOT count as a replay.
    assert led.seen("devB", "n1") is False


def test_in_memory_ledger_expiry():
    led = InMemoryNonceLedger()
    led.record("devA", "n-old", time.time() - MAX_SKEW_SECONDS - 1)
    assert led.seen("devA", "n-old") is False
    # Prune cleaned the backing dict.
    assert led.nonces == {}


def test_verify_uses_injected_ledger():
    s = DeviceSessionStore()
    led = InMemoryNonceLedger()
    s.nonce_ledger = led
    dev = s.register("Phone", "pubkey", "secret")
    led.record(dev.id, "replay-me", time.time())
    ok, reason = s.verify(dev.id, "sig", "replay-me", str(int(time.time())),
                         "GET", "/devices", "")
    # Fails on replay before signature is even checked.
    assert ok is False and reason == "replayed_nonce"


def test_persistent_ledger_survives_restart():
    with tempfile.TemporaryDirectory() as d:
        db = f"{d}/runtime.db"
        store = EncryptedRuntimeStore(db)
        led1 = PersistentNonceLedger(store)
        led1.record("devA", "n-restart", time.time())
        assert led1.seen("devA", "n-restart") is True
        # Simulate a process restart: new store handle, new ledger.
        store2 = EncryptedRuntimeStore(db)
        led2 = PersistentNonceLedger(store2)
        assert led2.seen("devA", "n-restart") is True
        assert led2.seen("devA", "n-other") is False


def test_persistent_ledger_prunes_expired():
    with tempfile.TemporaryDirectory() as d:
        db = f"{d}/runtime.db"
        store = EncryptedRuntimeStore(db)
        led = PersistentNonceLedger(store)
        led.record("devA", "n-stale", time.time() - MAX_SKEW_SECONDS - 1)
        led.record("devA", "n-fresh", time.time())
        # Force a prune (interval gate would otherwise skip it).
        led._last_prune = 0.0
        led.record("devA", "n-trigger", time.time())
        assert led.seen("devA", "n-stale") is False
        assert led.seen("devA", "n-fresh") is True
        rows = store.all("nonces", _NonceRow)
        assert {r.nonce for r in rows} == {"n-fresh", "n-trigger"}


def test_claim_is_atomic_across_threads():
    """Two threads racing the same nonce: exactly one claim wins."""
    import threading
    led = InMemoryNonceLedger()
    results = []
    def worker():
        results.append(led.claim("devA", "race", time.time()))
    ts = [threading.Thread(target=worker) for _ in range(16)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert sum(results) == 1


def test_persistent_claim_race_serializes():
    """Two connections racing claim() on the same DB: exactly one wins."""
    import threading
    path = tempfile.NamedTemporaryFile().name
    key = EncryptedRuntimeStore(path, key=None).key
    results = []
    def worker():
        store = EncryptedRuntimeStore(path, key=key)
        led = PersistentNonceLedger(store)
        results.append(led.claim("devA", "race", time.time()))
    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert sum(results) == 1


def test_persistent_claim_stale_row_is_not_replay():
    """A row older than MAX_SKEW_SECONDS is treated as absent, not replay."""
    path = tempfile.NamedTemporaryFile().name
    key = EncryptedRuntimeStore(path, key=None).key
    store = EncryptedRuntimeStore(path, key=key)
    led = PersistentNonceLedger(store)
    assert led.claim("devA", "old", time.time() - MAX_SKEW_SECONDS - 10) is True
    # Fresh claim on the same nonce now succeeds: the stale row was replaced.
    assert led.claim("devA", "old", time.time()) is True
    # And a second fresh claim is a replay.
    assert led.claim("devA", "old", time.time()) is False


def test_owner_flag_survives_restart():
    """The bootstrap owner flag must persist: register() writes the row
    with is_owner set, so a restart keeps strict owner enforcement."""
    from shadow_node.runtime_store import PersistentDeviceSessionStore
    path = tempfile.NamedTemporaryFile().name
    key = EncryptedRuntimeStore(path, key=None).key
    store = EncryptedRuntimeStore(path, key=key)
    reg = PersistentDeviceSessionStore(store)
    dev = reg.register("iPhone", "pubkey", "secret", is_owner=True)
    assert dev.is_owner is True
    reg2 = PersistentDeviceSessionStore(EncryptedRuntimeStore(path, key=key))
    assert reg2.devices[dev.id].is_owner is True
