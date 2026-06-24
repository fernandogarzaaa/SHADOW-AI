from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import base64, hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from agent_core import Device, now
from .stores import DeviceStore

def b64(b: bytes) -> str: return base64.urlsafe_b64encode(b).decode().rstrip("=")
def ub64(s: str) -> bytes: return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
def public_key_text(pk: Ed25519PublicKey) -> str: return b64(pk.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
def fingerprint(public_key: str) -> str: return hashlib.sha256(public_key.encode()).hexdigest()
@dataclass
class PairingChallenge:
    pairing_id: str; code: str; nonce: str; challenge: str; expires_at: datetime; used: bool = False
class PairingService:
    def __init__(self, device_store: DeviceStore, ttl_seconds: int = 300):
        self.device_store=device_store; self.ttl_seconds=ttl_seconds; self.challenges: dict[str, PairingChallenge]={}; self.node_private=Ed25519PrivateKey.generate(); self.node_public=public_key_text(self.node_private.public_key())
    def start(self) -> dict:
        pid=f"pair_{uuid4().hex}"; nonce=b64(uuid4().bytes+uuid4().bytes); challenge=b64(uuid4().bytes+uuid4().bytes); exp=datetime.now(timezone.utc)+timedelta(seconds=self.ttl_seconds)
        self.challenges[pid]=PairingChallenge(pid, pid[-6:].upper(), nonce, challenge, exp)
        return {"pairing_id":pid,"code":pid[-6:].upper(),"nonce":nonce,"challenge":challenge,"expires_at":exp.isoformat(),"node_public_key":self.node_public}
    def confirm(self, pairing_id: str, device_name: str, device_public_key: str, signature: str, nonce: str) -> Device:
        ch=self.challenges.get(pairing_id)
        if not ch: raise ValueError("pairing not found")
        if ch.used: raise ValueError("pairing challenge already used")
        if ch.expires_at < datetime.now(timezone.utc): raise ValueError("pairing challenge expired")
        if nonce != ch.nonce: raise ValueError("invalid nonce")
        pk=Ed25519PublicKey.from_public_bytes(ub64(device_public_key)); pk.verify(ub64(signature), f"{pairing_id}:{ch.challenge}:{nonce}".encode())
        ch.used=True
        dev=Device(name=device_name, public_key=device_public_key, trusted=True, pinned_key_fingerprint=fingerprint(device_public_key))
        return self.device_store.put(dev)
    def revoke(self, device_id: str) -> Device:
        dev=self.device_store.get(device_id)
        if not dev: raise ValueError("device not found")
        dev.trusted=False; dev.revoked_at=now(); return self.device_store.put(dev)
    def assert_trusted(self, device_id: str):
        dev=self.device_store.get(device_id)
        if not dev or not dev.trusted or dev.revoked_at is not None: raise PermissionError("device is not trusted")
        return dev
class DemoDeviceIdentity:
    def __init__(self): self.private=Ed25519PrivateKey.generate(); self.public=public_key_text(self.private.public_key())
    def sign_confirmation(self, pairing_id: str, challenge: str, nonce: str) -> str: return b64(self.private.sign(f"{pairing_id}:{challenge}:{nonce}".encode()))
