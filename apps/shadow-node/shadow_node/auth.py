from __future__ import annotations
from datetime import datetime, timezone, timedelta
import base64
from fastapi import Header, HTTPException, Request
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .pairing import ub64
from .stores import DeviceStore, AuditStore
from agent_core import AuditEvent

class NonceStore:
    def __init__(self): self.seen: dict[str, datetime] = {}
    def check(self, device_id: str, nonce: str, now: datetime, ttl_seconds: int) -> bool:
        cutoff = now - timedelta(seconds=ttl_seconds)
        self.seen = {k:v for k,v in self.seen.items() if v >= cutoff}
        key=f"{device_id}:{nonce}"
        if key in self.seen: return False
        self.seen[key]=now; return True

class SignedRequestVerifier:
    def __init__(self, devices: DeviceStore, audit: AuditStore|None=None, ttl_seconds: int=300):
        self.devices=devices; self.audit=audit; self.ttl_seconds=ttl_seconds; self.nonces=NonceStore()
    def _audit_fail(self, request: Request, reason: str, device_id: str|None):
        if self.audit:
            self.audit.put(AuditEvent(actor=device_id or "unknown_device", event_type="auth_failure", status="blocked", result=f"{request.method} {request.url.path}: {reason}"))
    async def verify(self, request: Request):
        x_shadow_device_id=request.headers.get("x-shadow-device-id")
        x_shadow_signature=request.headers.get("x-shadow-signature")
        x_shadow_nonce=request.headers.get("x-shadow-nonce")
        x_shadow_timestamp=request.headers.get("x-shadow-timestamp")
        missing=[n for n,v in {"device":x_shadow_device_id,"signature":x_shadow_signature,"nonce":x_shadow_nonce,"timestamp":x_shadow_timestamp}.items() if not v]
        if missing:
            self._audit_fail(request, "missing signed request headers", x_shadow_device_id); raise HTTPException(401, "missing signed request headers")
        dev=self.devices.get(x_shadow_device_id)
        if not dev or not dev.trusted or dev.revoked_at is not None:
            self._audit_fail(request, "revoked or untrusted device", x_shadow_device_id); raise HTTPException(403, "revoked or untrusted device")
        try: ts=datetime.fromisoformat(x_shadow_timestamp.replace("Z","+00:00"))
        except Exception:
            self._audit_fail(request, "invalid timestamp", x_shadow_device_id); raise HTTPException(401, "invalid timestamp")
        now=datetime.now(timezone.utc)
        if abs((now-ts).total_seconds()) > self.ttl_seconds:
            self._audit_fail(request, "expired timestamp or clock skew", x_shadow_device_id); raise HTTPException(401, "expired timestamp or clock skew")
        if not self.nonces.check(x_shadow_device_id, x_shadow_nonce, now, self.ttl_seconds):
            self._audit_fail(request, "replayed nonce", x_shadow_device_id); raise HTTPException(409, "replayed nonce")
        body=await request.body()
        msg=b"\n".join([request.method.upper().encode(), request.url.path.encode(), body, x_shadow_nonce.encode(), x_shadow_timestamp.encode()])
        try:
            Ed25519PublicKey.from_public_bytes(ub64(dev.public_key)).verify(ub64(x_shadow_signature), msg)
        except Exception:
            self._audit_fail(request, "invalid signature", x_shadow_device_id); raise HTTPException(401, "invalid signature")
        return dev
