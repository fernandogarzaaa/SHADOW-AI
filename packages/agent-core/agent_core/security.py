from __future__ import annotations
import hmac, hashlib, time, os, secrets
from dataclasses import dataclass, field
from typing import Callable
from .models import Device, AuditEvent, now

MAX_SKEW_SECONDS = 300
SESSION_SECONDS = 30 * 24 * 3600
# Set SHADOW_ED25519_KEYS=true to enable Ed25519 device-key mode.
ED25519_ENABLED = os.getenv("SHADOW_ED25519_KEYS", "false").lower() == "true"

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
    _HAS_ED25519 = True
except Exception:  # pragma: no cover
    _HAS_ED25519 = False


def fingerprint_for_key(public_key: str) -> str:
    return hashlib.sha256(public_key.encode()).hexdigest()[:32]


def _build_signed_message(method: str, path: str, body: str, nonce: str, timestamp: int) -> bytes:
    return "\n".join([method.upper(), path, body or "", nonce, str(timestamp)]).encode()


def sign_request(secret: str, method: str, path: str, body: str, nonce: str, timestamp: int) -> str:
    msg = _build_signed_message(method, path, body, nonce, timestamp)
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Ed25519 helpers (optional upgrade from HMAC)
# ---------------------------------------------------------------------------
def generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """Return (private_key_pem, public_key_bytes)."""
    if not _HAS_ED25519:
        raise RuntimeError("cryptography library required for Ed25519")
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv_pem, pub_bytes


def sign_ed25519(private_key_pem: bytes, method: str, path: str, body: str, nonce: str, timestamp: int) -> str:
    priv = serialization.load_pem_private_key(private_key_pem, password=None)
    msg = _build_signed_message(method, path, body, nonce, timestamp)
    return priv.sign(msg).hex()


def verify_ed25519(public_key_bytes: bytes, signature_hex: str, method: str, path: str, body: str, nonce: str, timestamp: int) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        sig = bytes.fromhex(signature_hex)
        msg = _build_signed_message(method, path, body, nonce, timestamp)
        pub.verify(sig, msg)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Device session store
# ---------------------------------------------------------------------------
@dataclass
class DeviceSessionStore:
    devices: dict[str, Device] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    nonces: dict[str, float] = field(default_factory=dict)  # nonce -> seen unix timestamp
    audit: list[AuditEvent] = field(default_factory=list)
    # Expo push tokens per device id (registered via POST /devices/{id}/push-token)
    push_tokens: dict[str, str] = field(default_factory=dict)
    # Ed25519 public keys per device (optional upgrade from HMAC secrets)
    ed25519_keys: dict[str, bytes] = field(default_factory=dict)
    # Optional sink(actor, event_type, payload) invoked on auth decisions so
    # the node can route them into the tamper-evident audit chain. Failures are
    # recorded; per-request successes are not (they would flood the chain).
    event_sink: Callable[[str, str, dict], None] | None = field(default=None)

    def _sink(self, event_type: str, payload: dict):
        if self.event_sink is not None:
            try:
                self.event_sink("sentinel_transport", event_type, payload)
            except Exception:
                pass  # auditing must never break auth

    def register(self, name: str, public_key: str, secret: str | None = None) -> Device:
        fp = fingerprint_for_key(public_key)
        dev = Device(name=name, public_key=public_key, fingerprint=fp, trusted=True)
        self.devices[dev.id] = dev
        self.secrets[dev.id] = secret or secrets.token_hex(32)
        return dev

    def register_ed25519(self, name: str, ed25519_public_key: bytes) -> Device:
        """Register a device with an Ed25519 public key instead of a shared secret."""
        public_key = ed25519_public_key.hex()[:64]
        fp = fingerprint_for_key(public_key)
        dev = Device(name=name, public_key=public_key, fingerprint=fp, trusted=True)
        self.devices[dev.id] = dev
        self.ed25519_keys[dev.id] = ed25519_public_key
        return dev

    def revoke(self, device_id: str):
        if device_id in self.devices:
            self.devices[device_id].revoked = True

    def _verify_hmac(self, dev: Device, signature: str, nonce: str, timestamp: str, method: str, path: str, body: str) -> tuple[bool, str]:
        expected = sign_request(self.secrets[dev.id], method, path, body, nonce, int(timestamp))
        if not hmac.compare_digest(signature, expected):
            return False, "invalid_signature"
        return True, "ok"

    def _verify_ed25519(self, dev: Device, signature: str, nonce: str, timestamp: str, method: str, path: str, body: str) -> tuple[bool, str]:
        pub = self.ed25519_keys.get(dev.id)
        if pub is None:
            return False, "no_ed25519_key"
        ok = verify_ed25519(pub, signature, method, path, body, nonce, int(timestamp))
        return (True, "ok") if ok else (False, "invalid_ed25519_signature")

    def verify(self, device_id: str | None, signature: str | None, nonce: str | None, timestamp: str | None,
               method: str, path: str, body: str = "") -> tuple[bool, str]:
        def fail(reason):
            self.audit.append(AuditEvent(actor="transport", event_type="auth_failed", status="blocked", result=reason, metadata={"device_id": device_id}))
            self._sink("auth.decision", {"outcome": "deny", "reason": reason, "device_id": device_id, "path": path})
            return False, reason

        if not device_id or device_id not in self.devices:
            return fail("unknown_device")
        dev = self.devices[device_id]
        if dev.revoked:
            return fail("revoked_device")
        if not dev.trusted:
            return fail("untrusted_device")
        if now() > dev.session_expires_at:
            return fail("session_expired")
        if not signature:
            return fail("missing_signature")
        if not nonce:
            return fail("missing_nonce")
        now_ts=int(time.time())
        for _n,_ts in list(self.nonces.items()):
            if now_ts-_ts>MAX_SKEW_SECONDS: del self.nonces[_n]
        if nonce in self.nonces:
            return fail("replayed_nonce")
        try:
            ts = int(timestamp or "0")
        except ValueError:
            return fail("invalid_timestamp")
        if abs(int(time.time()) - ts) > MAX_SKEW_SECONDS:
            return fail("expired_timestamp")

        # Ed25519 devices must never fall back to HMAC: the Ed25519 public key is public.
        if dev.id in self.ed25519_keys:
            if not ED25519_ENABLED:
                return fail("ed25519_disabled")
            if not _HAS_ED25519:
                return fail("ed25519_unavailable")
            ok, reason = self._verify_ed25519(dev, signature, nonce, timestamp, method, path, body)
        else:
            ok, reason = self._verify_hmac(dev, signature, nonce, timestamp, method, path, body)

        if not ok:
            return fail(reason)
        self.nonces[nonce]=now_ts
        return True, "ok"
