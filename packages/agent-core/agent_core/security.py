from __future__ import annotations
import hmac, hashlib, time, os, secrets, threading
from dataclasses import dataclass, field
from typing import Callable
from .models import Device, AuditEvent, now

MAX_SKEW_SECONDS = 300


# ---------------------------------------------------------------------------
# Nonce replay ledgers
# ---------------------------------------------------------------------------
class NonceLedger:
    """Uniqueness boundary for HMAC nonces, keyed (device_id, nonce).

    The in-memory ledger resets on process restart, reopening the replay
    window; the node injects a persistent ledger (encrypted runtime DB)
    when one is configured so restarts do not weaken replay protection.
    """

    def seen(self, device_id: str, nonce: str) -> bool:
        raise NotImplementedError

    def record(self, device_id: str, nonce: str, seen_at: float) -> None:
        raise NotImplementedError

    def claim(self, device_id: str, nonce: str, seen_at: float) -> bool:
        """Atomic check-and-record.

        Returns True when the nonce was fresh and is now recorded, False
        when it was already seen (replay). The default seen()+record()
        composite is NOT atomic; ledgers shared across threads or workers
        must override this with a real compare-and-set.
        """
        if self.seen(device_id, nonce):
            return False
        self.record(device_id, nonce, seen_at)
        return True


class InMemoryNonceLedger(NonceLedger):
    """Process-local ledger. Entries expire MAX_SKEW_SECONDS after being
    seen; expired entries are pruned lazily on access."""

    def __init__(self, backing: dict[str, float] | None = None):
        self.nonces: dict[str, float] = backing if backing is not None else {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(device_id: str, nonce: str) -> str:
        return f"{device_id}:{nonce}"

    def _prune(self, now_ts: float) -> None:
        for key, seen_at in list(self.nonces.items()):
            if now_ts - seen_at > MAX_SKEW_SECONDS:
                del self.nonces[key]

    def seen(self, device_id: str, nonce: str) -> bool:
        now_ts = time.time()
        self._prune(now_ts)
        return self._key(device_id, nonce) in self.nonces

    def record(self, device_id: str, nonce: str, seen_at: float) -> None:
        self._prune(seen_at)
        self.nonces[self._key(device_id, nonce)] = seen_at

    def claim(self, device_id: str, nonce: str, seen_at: float) -> bool:
        """Lock-atomic compare-and-set for threads sharing one process."""
        with self._lock:
            self._prune(seen_at)
            key = self._key(device_id, nonce)
            if key in self.nonces:
                return False
            self.nonces[key] = seen_at
            return True
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
    # Backing dict for the default in-memory nonce ledger, keyed
    # "device_id:nonce" -> seen unix timestamp. Tests and the no-DB dev
    # path clear or inspect this directly.
    nonces: dict[str, float] = field(default_factory=dict)
    # Injected by the node when an encrypted runtime DB is configured so
    # replay state survives restarts. None -> process-local ledger.
    nonce_ledger: NonceLedger | None = None
    # One in-memory ledger per store so claim() stays atomic across threads
    # (a fresh ledger per request would give every call its own lock).
    _memory_ledger: InMemoryNonceLedger | None = field(default=None, repr=False)
    # Node master secret for HMAC-derived device credentials
    # (shadow_node.device_credentials). When set, devices whose
    # credential_scheme is "hmac-vN" have their request-signing secret
    # derived at verify time instead of looked up from `secrets`.
    # None -> legacy behavior: every device uses its stored secret.
    master_secret: bytes | None = None

    def __post_init__(self):
        if self._memory_ledger is None:
            self._memory_ledger = InMemoryNonceLedger(self.nonces)
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

    def register(self, name: str, public_key: str, secret: str | None = None, is_owner: bool = False,
                 credential_scheme: str = "stored") -> Device:
        fp = fingerprint_for_key(public_key)
        dev = Device(name=name, public_key=public_key, fingerprint=fp, trusted=True, is_owner=is_owner,
                     credential_scheme=credential_scheme)
        self.devices[dev.id] = dev
        # HMAC-derived devices ("hmac-vN") store nothing per device: the
        # signing secret is recomputed from the node master secret at
        # verify time (see device_signing_secret). Stored-scheme devices
        # keep the legacy random secret.
        if not credential_scheme.startswith("hmac-"):
            self.secrets[dev.id] = secret or secrets.token_hex(32)
        return dev

    def device_signing_secret(self, dev: Device) -> str | None:
        """Resolve the HMAC secret used to sign/verify a device's requests.

        Derived devices recompute from the node master secret (fail
        closed when the master is unavailable); stored devices use the
        persisted random secret. Returns None when no secret can be
        resolved.
        """
        if dev.credential_scheme.startswith("hmac-"):
            if self.master_secret is None:
                return None
            try:
                # Deferred: shadow_node depends on agent_core, so this
                # import must not run at module load.
                from shadow_node.device_credentials import derive_device_token, version_from_scheme
            except ImportError:
                return None
            version = version_from_scheme(dev.credential_scheme)
            if version is None:
                return None
            try:
                return derive_device_token(self.master_secret, dev.id, version)
            except Exception:
                return None
        return self.secrets.get(dev.id)

    def register_ed25519(self, name: str, ed25519_public_key: bytes, is_owner: bool = False) -> Device:
        """Register a device with an Ed25519 public key instead of a shared secret."""
        public_key = ed25519_public_key.hex()[:64]
        fp = fingerprint_for_key(public_key)
        dev = Device(name=name, public_key=public_key, fingerprint=fp, trusted=True, is_owner=is_owner)
        self.devices[dev.id] = dev
        self.ed25519_keys[dev.id] = ed25519_public_key
        return dev

    def revoke(self, device_id: str):
        if device_id in self.devices:
            self.devices[device_id].revoked = True

    def _verify_hmac(self, dev: Device, signature: str, nonce: str, timestamp: str, method: str, path: str, body: str) -> tuple[bool, str]:
        secret = self.device_signing_secret(dev)
        if secret is None:
            # Fail closed: derived-scheme device with no master secret
            # configured, or stored-scheme device with no secret on file.
            return False, "unknown_device_secret"
        expected = sign_request(secret, method, path, body, nonce, int(timestamp))
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
        ledger = self.nonce_ledger if self.nonce_ledger is not None else self._memory_ledger
        if ledger.seen(device_id, nonce):
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
        # Atomic compare-and-set: two workers racing the same nonce serialize
        # here, and the loser is rejected as a replay.
        if not ledger.claim(device_id, nonce, now_ts):
            return fail("replayed_nonce")
        return True, "ok"


# ---------------------------------------------------------------------------
# Action authorization envelope
#
# An approval binds the FULL security-relevant state of an action, not just
# tool_name/params/description. The envelope is canonicalized to JSON and
# hashed; the hash is stored on the ApprovalRequest at creation and must be
# reproduced by the presented action at claim time. Any divergence in
# destination, data scope, risk, destructiveness, or policy version fails
# the claim, even if tool/params/description match.
# ---------------------------------------------------------------------------

AUTHORIZATION_ENVELOPE_VERSION = "v1"


def authorization_envelope(action: "AgentAction") -> dict:
    """Canonical security-relevant view of an action for approval binding."""
    import json as _json  # local import: keeps module import light
    params = action.params if isinstance(action.params, dict) else {}
    return {
        "envelope_version": AUTHORIZATION_ENVELOPE_VERSION,
        "tool": action.tool_name,
        "params": _json.loads(_json.dumps(params, sort_keys=True, default=str)),
        "description": action.description,
        "destination": action.destination,
        "data_scope": sorted(action.data_used or []),
        "model_used": action.model_used,
        "risk": action.risk.value if hasattr(action.risk, "value") else str(action.risk),
        "destructive": bool(action.destructive),
        "requires_approval": bool(action.requires_approval),
    }


def envelope_hash(action: "AgentAction") -> str:
    """sha256 over the canonical JSON encoding of the authorization envelope."""
    import json as _json
    canonical = _json.dumps(authorization_envelope(action), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
