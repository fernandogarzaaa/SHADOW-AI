"""HMAC-derived per-device credentials for the Shadow Node pairing ceremony.

Instead of minting a random secret per device and storing it, the node
derives each device's request-signing secret deterministically from a
single node master secret::

    token = HMAC-SHA256(master, "shadow-device:v<version>:<device_id>")

The derivation pattern is adapted from OpenDots' per-Dot computer
credentials (CopilotKit/OpenDots, MIT, Copyright (c) Atai Barkai):
``HMAC-SHA256(COMPUTER_TOKEN, "opendots-computer:" + id)``. The idea is
the same (one master secret, per-agent derived tokens, nothing stored
per device); the domain string, versioning, rotation story, and master
secret lifecycle here are SHADOW's own.

Why derivation instead of stored random secrets:

* Nothing per device to protect: a stolen device database yields no
  usable credentials without the master secret.
* Rotation is a version bump: the version is part of the derivation
  input, so old tokens stop verifying the moment the version moves.
* Device identity is preserved: the device_id is in the derivation
  string, so the consent ledger and audit log keep per-device
  attribution.

Rotation (deliberately simple, no grace period):

1. Replace the master secret (new ``SHADOW_MASTER_SECRET`` value or a
   new key file) AND bump ``DEVICE_TOKEN_VERSION``.
2. Every device must re-pair: tokens derived under the old version no
   longer verify, and confirm returns 401 ``invalid_signature`` until
   the device completes a fresh pairing ceremony.
3. Devices paired before this scheme existed (``credential_scheme`` =
   ``"stored"``) are unaffected by master rotation; they keep their
   stored random secrets until revoked or re-paired.

Security notes:

* The master secret is the crown jewel: anyone holding it can derive
  every device token. It is never logged, never returned by any API,
  and the key file is written with 0600 permissions.
* Derivation gives no forward secrecy: a leaked master compromises
  past tokens too. For a local-first node this is the accepted
  trade-off; rotate promptly on suspected compromise.
* Authenticated ECDH remains the documented upgrade path if the node
  ever goes remote or multi-user (see GOAL.md build order item 1).

Verification MUST use :func:`verify_device_token` (constant-time
``hmac.compare_digest``), never ``==``.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

# Current derivation version. Bump on master rotation; the version rides
# in the derivation input, so a bump invalidates every previously
# derived token and forces re-pairing (fail closed, no dual-accept).
DEVICE_TOKEN_VERSION = 1

_MASTER_ENV = "SHADOW_MASTER_SECRET"
_MASTER_FILE_ENV = "SHADOW_MASTER_SECRET_FILE"
_MASTER_DEFAULT_PATH = "data/keys/master.key"


def token_scheme_for_version(version: int) -> str:
    """Credential-scheme label stored on the Device row, e.g. ``"hmac-v1"``."""
    return f"hmac-v{version}"


def version_from_scheme(scheme: str) -> int | None:
    """Parse the derivation version out of a credential-scheme label."""
    if scheme.startswith("hmac-v"):
        try:
            return int(scheme[len("hmac-v"):])
        except ValueError:
            return None
    return None


def load_master_secret() -> bytes:
    """Load or create the node master secret. Never logs the value.

    Resolution order:
      1. ``SHADOW_MASTER_SECRET`` env: 64 hex chars are decoded to 32
         bytes; any other non-empty value is used as UTF-8 bytes.
      2. ``SHADOW_MASTER_SECRET_FILE`` env (default
         ``data/keys/master.key``): raw file bytes, if the file exists.
      3. A freshly generated 32-byte secret, persisted to the file path
         with 0600 permissions.

    Raises RuntimeError if a configured value is present but empty.
    """
    explicit = os.getenv(_MASTER_ENV)
    if explicit is not None:
        if not explicit.strip():
            raise RuntimeError(f"{_MASTER_ENV} is set but empty")
        text = explicit.strip()
        # Accept hex (preferred: unambiguous 32 bytes) or a raw passphrase.
        if len(text) % 2 == 0:
            try:
                return bytes.fromhex(text)
            except ValueError:
                pass
        return text.encode("utf-8")
    key_file = Path(os.getenv(_MASTER_FILE_ENV, _MASTER_DEFAULT_PATH))
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        data = key_file.read_bytes().strip()
        if not data:
            raise RuntimeError(f"master secret file {key_file} is empty")
        return data
    secret = secrets.token_bytes(32)
    key_file.write_bytes(secret)
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    return secret


def _derivation_input(device_id: str, version: int) -> bytes:
    if not device_id:
        raise ValueError("device_id must not be empty")
    return f"shadow-device:v{version}:{device_id}".encode("utf-8")


def derive_device_token(master: bytes, device_id: str, version: int = DEVICE_TOKEN_VERSION) -> str:
    """Derive a device's request-signing secret. Deterministic: the same
    (master, device_id, version) always yields the same hex token."""
    if not master:
        raise ValueError("master secret must not be empty")
    return hmac.new(master, _derivation_input(device_id, version), hashlib.sha256).hexdigest()


def verify_device_token(master: bytes, device_id: str, presented: str,
                        version: int = DEVICE_TOKEN_VERSION) -> bool:
    """Constant-time check of a presented device token. Fails closed on
    any error (bad types, empty inputs, undecodable values)."""
    try:
        if not master or not device_id or not presented:
            return False
        expected = derive_device_token(master, device_id, version)
        return hmac.compare_digest(expected, presented)
    except Exception:
        return False
