"""Credential vault with surrogate tokens and just-in-time injection.

Real secrets live here and only here: encrypted at rest in the runtime DB
(Fernet via EncryptedRuntimeStore) or in process memory when no DB is
configured. Tools and workers never see raw secrets. They receive short-lived
surrogate references (``shv_...`` tokens); the vault resolves a surrogate to
the real value at the execution boundary, injects it into the tool call, and
logs the resolution to the audit chain. The value itself never appears in
prompts, logs, screenshots, tool results, or the audit payload.

Per the Personal Agent OS spec: credential vault, surrogate tokens,
just-in-time injection, credential ACLs (scopes), credential audit.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from .models import new_id, now

SURROGATE_PREFIX = "shv_"
DEFAULT_SURROGATE_TTL_SECONDS = 300
# Values shorter than this are never scrubbed from text: scrubbing a 2-char
# secret would redact half the dictionary.
_MIN_SCRUB_LEN = 8
REDACTED = "[redacted]"


class CredentialRecord(BaseModel):
    name: str
    value: str
    scopes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class SurrogateRecord(BaseModel):
    token: str
    credential_name: str
    scopes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    expires_at: datetime = Field(default_factory=lambda: now() + timedelta(seconds=DEFAULT_SURROGATE_TTL_SECONDS))


class CredentialVault:
    """Owns every secret the node holds. Boundary for JIT secret injection."""

    def __init__(self, store=None, audit=None):
        # store: EncryptedRuntimeStore-like with put(collection, id, obj) and
        # all(collection, model). None means in-memory only (tests, ephemeral).
        # audit: AuditChain-like with record(actor, event_type, payload).
        self._store = store
        self._audit = audit
        self._credentials: dict[str, CredentialRecord] = {}
        self._surrogates: dict[str, SurrogateRecord] = {}
        if store is not None:
            for rec in store.all("vault_credentials", CredentialRecord):
                self._credentials[rec.name] = rec
            for rec in store.all("vault_surrogates", SurrogateRecord):
                if "__revoked__" in rec.scopes:
                    continue  # tombstone: stays revoked, no need to keep it resident
                self._surrogates[rec.token] = rec
            self.prune_expired()

    # -- credential lifecycle ------------------------------------------------
    def set_credential(self, name: str, value: str, scopes: list[str] | None = None) -> CredentialRecord:
        if not name or not name.strip():
            raise ValueError("credential name must not be empty")
        if not value:
            raise ValueError("credential value must not be empty")
        rec = CredentialRecord(name=name.strip(), value=value, scopes=scopes or [])
        old = self._credentials.get(rec.name)
        if old is not None:
            rec.created_at = old.created_at
        self._credentials[rec.name] = rec
        if self._store is not None:
            self._store.put("vault_credentials", rec.name, rec)
        self._record("credential.stored", {"credential_name": rec.name, "rotated": old is not None})
        return rec

    def rotate_credential(self, name: str, new_value: str) -> CredentialRecord:
        if name not in self._credentials:
            raise KeyError(f"unknown credential: {name}")
        rec = self.set_credential(name, new_value, scopes=self._credentials[name].scopes)
        # Rotation invalidates outstanding surrogates: they were minted against
        # the old value's lifetime.
        for token in [t for t, s in self._surrogates.items() if s.credential_name == name]:
            self.revoke_surrogate(token, reason="credential_rotated")
        self._record("credential.rotated", {"credential_name": name})
        return rec

    def revoke_credential(self, name: str) -> None:
        if name not in self._credentials:
            raise KeyError(f"unknown credential: {name}")
        del self._credentials[name]
        if self._store is not None:
            # EncryptedRuntimeStore has no delete; overwrite with a tombstone
            # and filter it on load. Simpler and honest: keep a revoked marker.
            self._store.put("vault_credentials", name, CredentialRecord(name=name, value="", scopes=["__revoked__"]))
        for token in [t for t, s in self._surrogates.items() if s.credential_name == name]:
            self.revoke_surrogate(token, reason="credential_revoked")
        self._record("credential.revoked", {"credential_name": name})

    def credential_names(self) -> list[str]:
        return sorted(n for n, r in self._credentials.items() if "__revoked__" not in r.scopes)

    def _get_record(self, name: str) -> CredentialRecord | None:
        rec = self._credentials.get(name)
        if rec is None or "__revoked__" in rec.scopes:
            return None
        return rec

    # -- surrogates ------------------------------------------------------------
    def mint_surrogate(
        self,
        credential_name: str,
        scopes: list[str] | None = None,
        ttl_seconds: int = DEFAULT_SURROGATE_TTL_SECONDS,
    ) -> str:
        if self._get_record(credential_name) is None:
            raise KeyError(f"unknown credential: {credential_name}")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        token = SURROGATE_PREFIX + secrets.token_hex(16)
        rec = SurrogateRecord(
            token=token,
            credential_name=credential_name,
            scopes=scopes or [],
            expires_at=now() + timedelta(seconds=ttl_seconds),
        )
        self._surrogates[token] = rec
        if self._store is not None:
            self._store.put("vault_surrogates", token, rec)
        self._record("surrogate.minted", {"credential_name": credential_name, "scopes": rec.scopes})
        return token

    def revoke_surrogate(self, token: str, reason: str = "operator_revoked") -> bool:
        rec = self._surrogates.pop(token, None)
        if rec is None:
            return False
        if self._store is not None:
            self._store.put(
                "vault_surrogates",
                token,
                SurrogateRecord(
                    token=token,
                    credential_name=rec.credential_name,
                    scopes=["__revoked__"],
                    expires_at=rec.expires_at,
                ),
            )
        self._record("surrogate.revoked", {"credential_name": rec.credential_name, "reason": reason})
        return True

    def prune_expired(self) -> int:
        """Drop expired surrogates (memory and store). Returns the count."""
        expired = [t for t, s in self._surrogates.items() if "__revoked__" not in s.scopes and now() > s.expires_at]
        for token in expired:
            rec = self._surrogates.pop(token)
            if self._store is not None:
                self._store.put(
                    "vault_surrogates",
                    token,
                    SurrogateRecord(
                        token=token,
                        credential_name=rec.credential_name,
                        scopes=["__revoked__"],
                        expires_at=rec.expires_at,
                    ),
                )
        return len(expired)

    def resolve_surrogate(self, token: str, required_scope: str | None = None) -> str | None:
        """Resolve a surrogate to its raw secret. Boundary-only use.

        Returns None for unknown, expired, revoked, or scope-mismatched
        tokens. Every attempt is recorded in the audit chain without the value.
        """
        rec = self._surrogates.get(token)
        if rec is None or "__revoked__" in rec.scopes:
            self._record("credential.resolve_denied", {"reason": "unknown_or_revoked_surrogate"})
            return None
        if now() > rec.expires_at:
            self._surrogates.pop(token, None)
            self._record("credential.resolve_denied", {"credential_name": rec.credential_name, "reason": "surrogate_expired"})
            return None
        cred = self._get_record(rec.credential_name)
        if cred is None:
            self._record("credential.resolve_denied", {"credential_name": rec.credential_name, "reason": "credential_revoked"})
            return None
        if required_scope is not None and required_scope not in rec.scopes and required_scope not in cred.scopes:
            self._record(
                "credential.resolve_denied",
                {"credential_name": rec.credential_name, "reason": f"scope_mismatch: {required_scope}"},
            )
            return None
        self._record("credential.resolved", {"credential_name": rec.credential_name, "scopes": rec.scopes})
        return cred.value

    # -- just-in-time injection -------------------------------------------------
    def inject(self, params: dict[str, Any], required_scope: str | None = None) -> tuple[dict[str, Any], list[str]]:
        """Return a copy of params with surrogates replaced by real values.

        The caller's original dict is never mutated, so stored execution
        records keep surrogates while only the live tool call sees secrets.
        Returns (injected_params, resolved_credential_names).
        """
        injected: dict[str, Any] = {}
        resolved: list[str] = []
        for key, value in params.items():
            if isinstance(value, str) and value.startswith(SURROGATE_PREFIX):
                secret = self.resolve_surrogate(value, required_scope=required_scope)
                if secret is None:
                    # Unresolvable surrogate: leave the token in place so the
                    # tool sees an opaque value rather than a missing param,
                    # and let the tool's own validation report the failure.
                    injected[key] = value
                else:
                    injected[key] = secret
                    rec = self._surrogates.get(value)
                    if rec is not None:
                        resolved.append(rec.credential_name)
            else:
                injected[key] = value
        return injected, resolved

    # -- scrubbing ---------------------------------------------------------------
    def scrub(self, text: str) -> str:
        """Redact active surrogate tokens and known secret values from text."""
        if not isinstance(text, str) or not text:
            return text
        out = text
        for token in self._surrogates:
            if token in out:
                out = out.replace(token, REDACTED)
        for rec in self._credentials.values():
            if "__revoked__" in rec.scopes:
                continue
            if len(rec.value) >= _MIN_SCRUB_LEN and rec.value in out:
                out = out.replace(rec.value, REDACTED)
        return out

    def scrub_obj(self, obj: Any) -> Any:
        """Recursively scrub strings inside a JSON-like structure."""
        if isinstance(obj, str):
            return self.scrub(obj)
        if isinstance(obj, dict):
            return {k: self.scrub_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.scrub_obj(v) for v in obj]
        return obj

    # -- internals -----------------------------------------------------------------
    def _record(self, event_type: str, payload: dict) -> None:
        if self._audit is not None:
            try:
                self._audit.record("sentinel_vault", event_type, payload)
            except Exception:
                pass  # auditing must never break the vault
