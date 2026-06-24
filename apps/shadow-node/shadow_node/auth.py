from __future__ import annotations
from datetime import datetime, timezone, timedelta
import os, sqlite3
from pathlib import Path
from fastapi import HTTPException, Request
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .pairing import ub64
from .stores import DeviceStore, AuditStore
from agent_core import AuditEvent

class SQLiteNonceStore:
    def __init__(self, db_path: str = "data/shadow_runtime.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn=sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self.conn.execute("CREATE TABLE IF NOT EXISTS auth_nonces(device_id TEXT NOT NULL, nonce TEXT NOT NULL, seen_at TEXT NOT NULL, PRIMARY KEY(device_id, nonce))")
        self.conn.commit()
    def check(self, device_id: str, nonce: str, now: datetime, ttl_seconds: int) -> bool:
        cutoff=(now-timedelta(seconds=ttl_seconds)).isoformat()
        self.conn.execute("DELETE FROM auth_nonces WHERE seen_at < ?", (cutoff,))
        self.conn.commit()
        try:
            self.conn.execute("INSERT INTO auth_nonces(device_id, nonce, seen_at) VALUES(?,?,?)", (device_id, nonce, now.isoformat()))
            self.conn.commit(); return True
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False

class SignedRequestVerifier:
    def __init__(self, devices: DeviceStore, audit: AuditStore|None=None, ttl_seconds: int=300, nonce_db_path: str|None=None):
        self.devices=devices; self.audit=audit; self.ttl_seconds=ttl_seconds; self.nonces=SQLiteNonceStore(nonce_db_path or os.getenv("SHADOW_RUNTIME_DB","data/shadow_runtime.db"))
    def _audit_fail(self, request: Request, reason: str, device_id: str|None):
        if self.audit:
            self.audit.put(AuditEvent(actor=device_id or "unknown_device", event_type="auth_failure", status="blocked", result=f"{request.method} {request.url.path}: {reason}"))
    async def verify(self, request: Request):
        device_id=request.headers.get("x-shadow-device-id")
        signature=request.headers.get("x-shadow-signature")
        nonce=request.headers.get("x-shadow-nonce")
        timestamp=request.headers.get("x-shadow-timestamp")
        if any(v is None or v == "" for v in [device_id, signature, nonce, timestamp]):
            self._audit_fail(request, "missing signed request headers", device_id); raise HTTPException(401, "missing signed request headers")
        dev=self.devices.get(device_id)
        if not dev or not dev.trusted or dev.revoked_at is not None:
            self._audit_fail(request, "revoked or untrusted device", device_id); raise HTTPException(403, "revoked or untrusted device")
        try: ts=datetime.fromisoformat(timestamp.replace("Z","+00:00"))
        except Exception:
            self._audit_fail(request, "invalid timestamp", device_id); raise HTTPException(401, "invalid timestamp")
        now=datetime.now(timezone.utc)
        if abs((now-ts).total_seconds()) > self.ttl_seconds:
            self._audit_fail(request, "expired timestamp or clock skew", device_id); raise HTTPException(401, "expired timestamp or clock skew")
        if not self.nonces.check(device_id, nonce, now, self.ttl_seconds):
            self._audit_fail(request, "replayed nonce", device_id); raise HTTPException(409, "replayed nonce")
        body=await request.body()
        msg=b"\n".join([request.method.upper().encode(), request.url.path.encode(), body, nonce.encode(), timestamp.encode()])
        try:
            Ed25519PublicKey.from_public_bytes(ub64(dev.public_key)).verify(ub64(signature), msg)
        except Exception:
            self._audit_fail(request, "invalid signature", device_id); raise HTTPException(401, "invalid signature")
        return dev
