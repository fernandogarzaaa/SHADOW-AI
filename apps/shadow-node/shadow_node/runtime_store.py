"""Encrypted, persistent runtime state for the Shadow Node.

When ``SHADOW_RUNTIME_DB`` is set, audit events, consent grants, and paired
devices survive process restarts in an encrypted SQLite database. When it is
unset (tests / ephemeral dev), the node uses plain in-memory collections and
behaves exactly as before — these classes are drop-in and transparent.
"""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from agent_core import AuditEvent, ConsentGrant, Device, DeviceSessionStore
from .crypto_config import load_fernet_key


class EncryptedRuntimeStore:
    def __init__(self, db_path: str, key: bytes | None = None):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.key = key or load_fernet_key("SHADOW_RUNTIME_KEY", "SHADOW_RUNTIME_KEY_FILE", "data/keys/runtime.key")
        self.cipher = Fernet(self.key)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS runtime(collection TEXT, id TEXT, ciphertext BLOB, seq INTEGER PRIMARY KEY AUTOINCREMENT)"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_coll ON runtime(collection)")
        self.conn.commit()

    def put(self, collection: str, id: str, obj) -> None:
        blob = self.cipher.encrypt(obj.model_dump_json().encode())
        # Replace by (collection, id) so updates (e.g. device revoke) don't duplicate.
        self.conn.execute("DELETE FROM runtime WHERE collection=? AND id=?", (collection, id))
        self.conn.execute("INSERT INTO runtime(collection, id, ciphertext) VALUES(?,?,?)", (collection, id, blob))
        self.conn.commit()

    def all(self, collection: str, model) -> list:
        rows = self.conn.execute(
            "SELECT ciphertext FROM runtime WHERE collection=? ORDER BY seq", (collection,)
        ).fetchall()
        out = []
        for (blob,) in rows:
            try:
                out.append(model.model_validate_json(self.cipher.decrypt(blob).decode()))
            except (InvalidToken, ValueError):
                continue
        return out

    def delete(self, collection: str, id: str) -> None:
        """Remove one persisted object (used by goal deletion)."""
        self.conn.execute(
            "DELETE FROM runtime WHERE collection=? AND id=?", (collection, id)
        )
        self.conn.commit()


class PersistentList(list):
    """A list that mirrors appends/extends into the encrypted runtime store."""

    def __init__(self, store: EncryptedRuntimeStore, collection: str, model):
        super().__init__(store.all(collection, model))
        self._store = store
        self._collection = collection

    def append(self, obj):
        super().append(obj)
        self._store.put(self._collection, getattr(obj, "id", str(len(self))), obj)

    def extend(self, objs):
        for o in objs:
            self.append(o)


class PersistentDeviceSessionStore(DeviceSessionStore):
    """DeviceSessionStore that persists devices + secrets and reloads them on boot."""

    def __init__(self, store: EncryptedRuntimeStore):
        super().__init__()
        self._store = store
        for dev in store.all("devices", Device):
            self.devices[dev.id] = dev
        for secret in store.all("device_secrets", _Secret):
            self.secrets[secret.id] = secret.value

    def register(self, name: str, public_key: str, secret: str | None = None, is_owner: bool = False,
                 credential_scheme: str = "stored") -> Device:
        dev = super().register(name, public_key, secret, is_owner=is_owner, credential_scheme=credential_scheme)
        self._store.put("devices", dev.id, dev)
        # HMAC-derived devices persist no per-device secret (the signing
        # secret is recomputed from the node master); persisting an empty
        # row would only confuse a future audit.
        if dev.id in self.secrets:
            self._store.put("device_secrets", dev.id, _Secret(id=dev.id, value=self.secrets[dev.id]))
        return dev

    def revoke(self, device_id: str):
        super().revoke(device_id)
        if device_id in self.devices:
            self._store.put("devices", device_id, self.devices[device_id])


# Minimal model so device secrets ride the same encrypted store.
from pydantic import BaseModel
class _Secret(BaseModel):
    id: str
    value: str


class _PauseFlag(BaseModel):
    """Durable emergency-pause flag (audit P1). Stored under
    collection='safety', id='emergency_pause'."""
    id: str = "emergency_pause"
    paused: bool = False
    updated_at: float = 0.0


def load_pause_flag(store: EncryptedRuntimeStore) -> bool:
    """Conservative load: no row means never paused (False); a row that
    cannot be decrypted means tampering or corruption -> True (fail
    closed: a broken kill switch must not silently disarm)."""
    rows = store.conn.execute(
        "SELECT ciphertext FROM runtime WHERE collection='safety' AND id='emergency_pause' ORDER BY seq"
    ).fetchall()
    if not rows:
        return False
    try:
        return _PauseFlag.model_validate_json(store.cipher.decrypt(rows[-1][0]).decode()).paused
    except (InvalidToken, ValueError):
        return True


def save_pause_flag(store: EncryptedRuntimeStore, paused: bool) -> None:
    import time as _time
    store.put("safety", "emergency_pause",
              _PauseFlag(paused=paused, updated_at=_time.time()))


def build_runtime(db_path: str):
    """Return (store, audit_list, consents_list, sessions) wired for persistence."""
    store = EncryptedRuntimeStore(db_path)
    audit = PersistentList(store, "audit", AuditEvent)
    consents = PersistentList(store, "consents", ConsentGrant)
    sessions = PersistentDeviceSessionStore(store)
    # Durable nonce replay state (audit P1): restarts must not reopen the
    # replay window. Falls back to the process-local ledger when the DB is
    # unavailable.
    sessions.nonce_ledger = PersistentNonceLedger(store)
    return store, audit, consents, sessions


class _NonceRow(BaseModel):
    """One seen HMAC nonce. Stored under collection='nonces',
    id='<device_id>:<nonce>'."""
    id: str
    device_id: str
    nonce: str
    seen_at: float


class PersistentNonceLedger:
    """NonceLedger backed by the encrypted runtime DB.

    seen()/record() are keyed (device_id, nonce) with the same semantics
    as the in-memory ledger. Rows expire MAX_SKEW_SECONDS after being
    seen; expired rows are pruned lazily (at most once a minute) since
    expiry is embedded in the ciphertext and cannot be filtered in SQL.
    Volume is bounded by design: one row per authenticated request, each
    living at most five minutes."""

    _PRUNE_INTERVAL = 60.0

    def __init__(self, store: EncryptedRuntimeStore):
        self._store = store
        self._last_prune = 0.0

    @staticmethod
    def _key(device_id: str, nonce: str) -> str:
        return f"{device_id}:{nonce}"

    def seen(self, device_id: str, nonce: str) -> bool:
        rows = self._store.conn.execute(
            "SELECT ciphertext FROM runtime WHERE collection='nonces' AND id=?",
            (self._key(device_id, nonce),),
        ).fetchall()
        return len(rows) > 0

    def record(self, device_id: str, nonce: str, seen_at: float) -> None:
        key = self._key(device_id, nonce)
        self._store.put("nonces", key,
                        _NonceRow(id=key, device_id=device_id, nonce=nonce, seen_at=seen_at))
        now = time.time()
        if now - self._last_prune >= self._PRUNE_INTERVAL:
            self._last_prune = now
            self._prune(now)

    def _prune(self, now: float) -> None:
        from agent_core import MAX_SKEW_SECONDS
        expired = [row.id for row in self._store.all("nonces", _NonceRow)
                   if now - row.seen_at > MAX_SKEW_SECONDS]
        for row_id in expired:
            self._store.delete("nonces", row_id)

    def claim(self, device_id: str, nonce: str, seen_at: float) -> bool:
        """Atomic compare-and-set across workers sharing one DB file.

        Runs inside a BEGIN IMMEDIATE transaction so two Uvicorn workers
        racing the same (device_id, nonce) serialize: exactly one insert
        wins and the loser gets False (replay). A stale row (older than
        MAX_SKEW_SECONDS) is treated as absent, not as a replay.
        """
        from agent_core import MAX_SKEW_SECONDS
        key = self._key(device_id, nonce)
        conn = self._store.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            rows = conn.execute(
                "SELECT ciphertext FROM runtime WHERE collection='nonces' AND id=?",
                (key,),
            ).fetchall()
            for (blob,) in rows:
                try:
                    row = _NonceRow.model_validate_json(
                        self._store.cipher.decrypt(blob).decode())
                except Exception:
                    continue  # corrupt row: treat as absent, overwrite below
                if seen_at - row.seen_at <= MAX_SKEW_SECONDS:
                    conn.execute("ROLLBACK")
                    return False
            conn.execute("DELETE FROM runtime WHERE collection='nonces' AND id=?", (key,))
            blob = self._store.cipher.encrypt(
                _NonceRow(id=key, device_id=device_id, nonce=nonce,
                          seen_at=seen_at).model_dump_json().encode())
            conn.execute(
                "INSERT INTO runtime(collection, id, ciphertext) VALUES(?,?,?)",
                ("nonces", key, blob))
            conn.execute("COMMIT")
            return True
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
