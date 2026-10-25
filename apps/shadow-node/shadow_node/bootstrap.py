"""One-time bootstrap code for first-owner enrollment.

A fresh node (or one whose owner devices have all expired or been revoked)
has nobody who can approve a pairing. Previously the first /pair/confirm
self-approved as owner, so whoever reached the port first owned the node.
Now the node prints a short single-use code to its own terminal; the first
owner must present it at /pair/confirm. Only someone with access to the
node's console (or to SHADOW_BOOTSTRAP_CODE) can claim ownership.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import sys
import threading

MAX_FAILURES = 5

_log = logging.getLogger("shadow_node.bootstrap")


def _digest(code: str) -> bytes:
    normalized = code.strip().replace("-", "").replace(" ", "").lower()
    return hashlib.sha256(normalized.encode()).digest()


class BootstrapCode:
    """Holds only the hash of the current code; the plaintext is shown once."""

    def __init__(self, fixed: str | None = None):
        self._lock = threading.Lock()
        self._hash: bytes | None = None
        self._failures = 0
        # Operator-supplied code (headless/Docker deploys). It is never
        # rotated away, but it is still consumed by a successful bootstrap.
        self._fixed = fixed

    @property
    def active(self) -> bool:
        return self._hash is not None

    def ensure(self) -> str | None:
        """Issue a code if none is active. Returns the new plaintext code
        (also announced on stderr) or None when one was already active."""
        with self._lock:
            if self._hash is not None:
                return None
            return self._issue_locked()

    def _issue_locked(self) -> str:
        self._failures = 0
        if self._fixed:
            code = self._fixed
            self._hash = _digest(code)
            _announce("SHADOW BOOTSTRAP CODE set from SHADOW_BOOTSTRAP_CODE")
            return code
        raw = secrets.token_hex(4).upper()
        code = f"{raw[:4]}-{raw[4:]}"
        self._hash = _digest(code)
        _announce(f"SHADOW BOOTSTRAP CODE: {code}  (single use; pair your first device with it)")
        return code

    def check(self, code: str | None) -> bool:
        """Constant-time check. A wrong code counts as a failure; after
        MAX_FAILURES the code rotates (a fixed operator code is kept)."""
        if not code:
            return False
        with self._lock:
            if self._hash is None:
                return False
            if hmac.compare_digest(self._hash, _digest(code)):
                return True
            self._failures += 1
            if self._failures >= MAX_FAILURES and not self._fixed:
                self._hash = None
                self._issue_locked()
            return False

    def consume(self) -> None:
        with self._lock:
            self._hash = None
            self._failures = 0

    @property
    def failures(self) -> int:
        return self._failures


def _announce(line: str) -> None:
    bar = "=" * min(len(line), 78)
    # stderr directly: uvicorn's logging config may not surface our logger,
    # and the operator must see this line in the terminal.
    print(f"\n{bar}\n{line}\n{bar}\n", file=sys.stderr, flush=True)
    _log.warning(line.split(":")[0])  # never log the code itself to log sinks


def from_env() -> BootstrapCode:
    return BootstrapCode(fixed=os.getenv("SHADOW_BOOTSTRAP_CODE") or None)
