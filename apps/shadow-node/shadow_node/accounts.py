"""Accounts hub: uniform directory of third-party services the node can act through.

Local-first adaptation of Hark Pro's accounts screen: one uniform list of
services, every row carrying the "stays on this device" guarantee. Credentials
are stored encrypted in the node vault (provider_auth.CredentialStore: Fernet
at rest, chmod 0600) and never leave the user's machine. No secret value ever
appears in an API response, an audit event, or a log.

The registry is seeded from real sources only: the frontier model providers in
providers.CATALOG. New service kinds can be registered by extending
SERVICE_DEFS; nothing is faked or listed without a real backing integration.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .provider_auth import OAUTH, CredentialStore
from .providers import CATALOG

#: Copy shown on every row. Plain words, no em dashes.
LOCAL_FIRST_NOTE = (
    "Credentials are encrypted and stored on this device only. "
    "They never leave this device."
)


class ServiceDef(BaseModel):
    """A service the node can act through."""

    id: str
    display_name: str
    kind: str
    description: str
    auth_methods: list[str] = Field(default_factory=list)
    oauth_supported: bool = False


class AccountRow(BaseModel):
    """Uniform row for the accounts directory. Never carries secret values."""

    id: str
    display_name: str
    kind: str
    description: str
    auth_methods: list[str] = Field(default_factory=list)
    oauth_supported: bool = False
    connected: bool = False
    credential_type: str | None = None
    credential_source: str | None = None
    local_first_note: str = LOCAL_FIRST_NOTE


def _catalog_defs() -> list[ServiceDef]:
    """Build service definitions from the real provider catalog."""
    defs = []
    for name, spec in CATALOG.items():
        defs.append(
            ServiceDef(
                id=name,
                display_name=spec["label"],
                kind="model_provider",
                description=spec.get("note", ""),
                auth_methods=list(spec.get("auth_methods", [])),
                oauth_supported=name in OAUTH,
            )
        )
    return defs


#: The full service directory. Seeded from real integrations only.
SERVICE_DEFS: list[ServiceDef] = _catalog_defs()


def service_ids() -> list[str]:
    return [d.id for d in SERVICE_DEFS]


def _row(store: CredentialStore, d: ServiceDef) -> AccountRow:
    cred = store.resolve(d.id)
    return AccountRow(
        id=d.id,
        display_name=d.display_name,
        kind=d.kind,
        description=d.description,
        auth_methods=d.auth_methods,
        oauth_supported=d.oauth_supported,
        connected=bool(cred),
        credential_type=(cred or {}).get("type"),
        credential_source=(cred or {}).get("source", "stored" if cred else None),
    )


def list_accounts(store: CredentialStore) -> list[AccountRow]:
    """Uniform rows for every service. Never includes secret values."""
    return [_row(store, d) for d in SERVICE_DEFS]


def get_account(store: CredentialStore, service_id: str) -> AccountRow | None:
    for d in SERVICE_DEFS:
        if d.id == service_id:
            return _row(store, d)
    return None


def connect_account(
    store: CredentialStore, service_id: str, api_key: str
) -> AccountRow:
    """Store a credential encrypted in the node vault. Raises KeyError if unknown."""
    if service_id not in service_ids():
        raise KeyError(service_id)
    store.set(service_id, {"type": "api_key", "api_key": api_key, "source": "stored"})
    row = get_account(store, service_id)
    assert row is not None
    return row


def disconnect_account(store: CredentialStore, service_id: str) -> None:
    """Remove a credential from the node vault. Idempotent. Raises KeyError if unknown."""
    if service_id not in service_ids():
        raise KeyError(service_id)
    store.delete(service_id)
