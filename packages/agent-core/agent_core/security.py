from __future__ import annotations
import hmac, hashlib, time
from dataclasses import dataclass, field
from .models import Device, AuditEvent, now

MAX_SKEW_SECONDS=300
SESSION_SECONDS=30*24*3600

def fingerprint_for_key(public_key:str)->str:
    return hashlib.sha256(public_key.encode()).hexdigest()[:32]

def sign_request(secret:str, method:str, path:str, body:str, nonce:str, timestamp:int)->str:
    msg="\n".join([method.upper(), path, body or "", nonce, str(timestamp)]).encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

@dataclass
class DeviceSessionStore:
    devices: dict[str, Device]=field(default_factory=dict)
    secrets: dict[str, str]=field(default_factory=dict)
    nonces: set[str]=field(default_factory=set)
    audit: list[AuditEvent]=field(default_factory=list)
    def register(self, name:str, public_key:str, secret:str|None=None)->Device:
        fp=fingerprint_for_key(public_key); dev=Device(name=name, public_key=public_key, fingerprint=fp, trusted=True)
        self.devices[dev.id]=dev; self.secrets[dev.id]=secret or hashlib.sha256((public_key+dev.id).encode()).hexdigest(); return dev
    def revoke(self, device_id:str):
        self.devices[device_id].revoked=True
    def verify(self, device_id:str|None, signature:str|None, nonce:str|None, timestamp:str|None, method:str, path:str, body:str="")->tuple[bool,str]:
        def fail(reason):
            self.audit.append(AuditEvent(actor="transport", event_type="auth_failed", status="blocked", result=reason, metadata={"device_id":device_id}))
            return False, reason
        if not device_id or device_id not in self.devices: return fail("unknown_device")
        dev=self.devices[device_id]
        if dev.revoked: return fail("revoked_device")
        if not dev.trusted: return fail("untrusted_device")
        if now() > dev.session_expires_at: return fail("session_expired")
        if not signature: return fail("missing_signature")
        if not nonce: return fail("missing_nonce")
        if nonce in self.nonces: return fail("replayed_nonce")
        try: ts=int(timestamp or "0")
        except ValueError: return fail("invalid_timestamp")
        if abs(int(time.time())-ts) > MAX_SKEW_SECONDS: return fail("expired_timestamp")
        expected=sign_request(self.secrets[device_id], method, path, body, nonce, ts)
        if not hmac.compare_digest(signature, expected): return fail("invalid_signature")
        self.nonces.add(nonce); return True,"ok"
