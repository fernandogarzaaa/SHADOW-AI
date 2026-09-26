"""Tamper-evident append-only audit log for Sentinel-lite.

Every policy decision, approval event, credential resolution, and execution
verdict is recorded here. Entries are hash-chained: each entry's hash covers
the previous entry's hash plus the entry's canonical content, so any edit,
deletion, or reordering of history is detectable by ``verify()``.

Entries persist in the encrypted runtime DB (collection ``audit_chain``) when
one is configured, and in memory otherwise. The log is append-only: entries
are never updated or deleted through this API.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import BaseModel, Field

from .models import new_id, now

GENESIS_HASH = "GENESIS"


class AuditEntry(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ach"))
    seq: int = 0
    timestamp: datetime = Field(default_factory=now)
    actor: str = ""
    event_type: str = ""
    payload: dict = Field(default_factory=dict)
    prev_hash: str = GENESIS_HASH
    hash: str = ""


def _canonical(entry: AuditEntry) -> bytes:
    """Deterministic byte encoding of everything the hash covers."""
    return json.dumps(
        {
            "seq": entry.seq,
            "id": entry.id,
            "timestamp": entry.timestamp.isoformat(),
            "actor": entry.actor,
            "event_type": entry.event_type,
            "payload": entry.payload,
            "prev_hash": entry.prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()


def entry_hash(entry: AuditEntry) -> str:
    return hashlib.sha256(_canonical(entry)).hexdigest()


class AuditChain:
    """Append-only, hash-chained audit log."""

    def __init__(self, store=None):
        # store: EncryptedRuntimeStore-like with put(collection, id, obj) and
        # all(collection, model). None means in-memory only.
        self._store = store
        self._entries: list[AuditEntry] = []
        if store is not None:
            self._entries = sorted(store.all("audit_chain", AuditEntry), key=lambda e: e.seq)

    def __len__(self) -> int:
        return len(self._entries)

    def record(self, actor: str, event_type: str, payload: dict | None = None) -> AuditEntry:
        prev = self._entries[-1].hash if self._entries else GENESIS_HASH
        entry = AuditEntry(
            seq=len(self._entries),
            actor=actor,
            event_type=event_type,
            payload=dict(payload or {}),
            prev_hash=prev,
        )
        entry.hash = entry_hash(entry)
        self._entries.append(entry)
        if self._store is not None:
            self._store.put("audit_chain", entry.id, entry)
        return entry

    def entries(self, limit: int | None = None) -> list[AuditEntry]:
        if limit is None:
            return list(self._entries)
        return list(self._entries[-limit:])

    def verify(self) -> tuple[bool, list[str]]:
        """Recompute the whole chain. Returns (ok, problems)."""
        problems: list[str] = []
        expected_prev = GENESIS_HASH
        for i, entry in enumerate(self._entries):
            if entry.seq != i:
                problems.append(f"entry {entry.id}: seq {entry.seq} breaks continuity (expected {i})")
            if entry.prev_hash != expected_prev:
                problems.append(f"entry {entry.id}: prev_hash does not link to previous entry")
            if entry.hash != entry_hash(entry):
                problems.append(f"entry {entry.id}: content hash mismatch (tampered content)")
            expected_prev = entry.hash
        return (len(problems) == 0, problems)
