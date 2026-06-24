from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Generic, TypeVar
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel
from .crypto_config import load_fernet_key
from agent_core import ApprovalRequest, AuditEvent, ConsentGrant, AgentTask, Device

T = TypeVar("T", bound=BaseModel)

class SQLiteRuntimeStore(Generic[T]):
    table = "runtime"
    model: type[T]
    def __init__(self, db_path: str = "data/shadow_runtime.db", key: bytes | None = None):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.key = key or load_fernet_key("SHADOW_RUNTIME_KEY", "SHADOW_RUNTIME_KEY_FILE", "data/keys/runtime.key")
        self.cipher = Fernet(self.key)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self._init()
    def _init(self):
        self.conn.execute(f"CREATE TABLE IF NOT EXISTS {self.table}(id TEXT PRIMARY KEY, ciphertext BLOB NOT NULL, created_at TEXT, revoked_at TEXT)")
        self.conn.commit()
    def put(self, obj: T) -> T:
        payload = self.cipher.encrypt(obj.model_dump_json().encode())
        created = str(getattr(obj, "created_at", getattr(obj, "timestamp", getattr(obj, "registered_at", ""))))
        revoked = getattr(obj, "revoked_at", None)
        self.conn.execute(f"INSERT OR REPLACE INTO {self.table}(id,ciphertext,created_at,revoked_at) VALUES(?,?,?,?)", (obj.id, payload, created, str(revoked) if revoked else None))
        self.conn.commit(); return obj
    def get(self, id: str) -> T | None:
        row = self.conn.execute(f"SELECT ciphertext FROM {self.table} WHERE id=?", (id,)).fetchone()
        return self.model.model_validate_json(self.cipher.decrypt(row[0]).decode()) if row else None
    def list(self, include_revoked: bool = False) -> list[T]:
        rows = self.conn.execute(f"SELECT ciphertext FROM {self.table} ORDER BY created_at").fetchall()
        out = []
        for r in rows:
            try:
                out.append(self.model.model_validate_json(self.cipher.decrypt(r[0]).decode()))
            except InvalidToken:
                continue
        if include_revoked: return out
        return [o for o in out if getattr(o, "revoked_at", None) is None]
    def delete(self, id: str):
        self.conn.execute(f"DELETE FROM {self.table} WHERE id=?", (id,)); self.conn.commit()

class DeviceStore(SQLiteRuntimeStore[Device]): table="devices"; model=Device
class ApprovalStore(SQLiteRuntimeStore[ApprovalRequest]): table="approvals"; model=ApprovalRequest
class AuditStore(SQLiteRuntimeStore[AuditEvent]):
    table="audit"; model=AuditEvent
    def delete(self, id: str): raise RuntimeError("Audit events are append-only")
class ConsentStore(SQLiteRuntimeStore[ConsentGrant]): table="consents"; model=ConsentGrant
class TaskStore(SQLiteRuntimeStore[AgentTask]): table="tasks"; model=AgentTask
