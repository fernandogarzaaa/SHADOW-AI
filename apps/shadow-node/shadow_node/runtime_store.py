"""Encrypted, persistent runtime state for the Shadow Node.

When ``SHADOW_RUNTIME_DB`` is set, audit events, consent grants, and paired
devices survive process restarts in an encrypted SQLite database. When it is
unset (tests / ephemeral dev), the node uses plain in-memory collections and
behaves exactly as before — these classes are drop-in and transparent.
"""
from __future__ import annotations
import sqlite3
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

    def register(self, name: str, public_key: str, secret: str | None = None) -> Device:
        dev = super().register(name, public_key, secret)
        self._store.put("devices", dev.id, dev)
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


def build_runtime(db_path: str):
    """Return (store, audit_list, consents_list, sessions) wired for persistence."""
    store = EncryptedRuntimeStore(db_path)
    audit = PersistentList(store, "audit", AuditEvent)
    consents = PersistentList(store, "consents", ConsentGrant)
    sessions = PersistentDeviceSessionStore(store)
    return store, audit, consents, sessions
