"""Cross-device assistant continuity (Hark backlog item 11).

One assistant identity across iOS, desktop, and web. The node on the user's
own hardware stays the source of truth; clients stay thin.

What already existed (verified, not rebuilt):
- Durable node-side conversations: ``agent_core.SessionStore`` persists every
  mutation to the runtime KV, listed via ``GET /agent/sessions``.
- Device identity: ``agent_core.DeviceSessionStore``; paired devices
  authenticate with the ``x-shadow-device-id`` header plus request signatures.
- Node-side memory: the memory engine ingests compacted session summaries, so
  memory follows the user with no client-local state to migrate.

What this module adds:
- Device presence: lightweight last-seen heartbeats so the node can report
  which registered clients are active.
- Explicit handoff: ``POST /agent/sessions/{session_id}/handoff`` packages an
  immutable snapshot of a conversation; another registered device claims it
  via ``POST /continuity/handoffs/{handoff_id}/claim`` and resumes exactly
  where the first left off. Handoff is always explicit and user-initiated,
  never automatic. Pending approvals and active plans are resolved live at
  claim time (they are node-global), while the message snapshot is frozen at
  handoff time for audit.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from agent_core import new_id, now
from pydantic import BaseModel, Field

#: A pending handoff that is never claimed stops being claimable after this.
HANDOFF_TTL = timedelta(hours=24)

_HANDOFF_COLLECTION = "handoffs"
_PRESENCE_COLLECTION = "device_presence"


class HandoffStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class HandoffRecord(BaseModel):
    """An explicit, user-initiated conversation handoff between devices."""

    id: str = Field(default_factory=lambda: new_id("handoff"))
    session_id: str
    from_device_id: str | None = None
    from_device_name: str | None = None
    target_device_id: str | None = None
    target_device_name: str | None = None
    note: str = ""
    status: HandoffStatus = HandoffStatus.PENDING
    created_at: datetime = Field(default_factory=now)
    claimed_at: datetime | None = None
    claimed_by_device_id: str | None = None
    # Immutable snapshot of the conversation at handoff time.
    snapshot: dict[str, Any] = Field(default_factory=dict)
    # Counts at creation time, for display and audit. Live state is resolved
    # at claim time because approvals and plans are node-global.
    pending_approval_count: int = 0
    active_plan_count: int = 0


class DevicePresence(BaseModel):
    """Last-seen heartbeat for one registered client."""

    device_id: str
    display_name: str | None = None
    platform: str | None = None
    first_seen_at: datetime = Field(default_factory=now)
    last_seen_at: datetime = Field(default_factory=now)


def build_session_snapshot(session: Any) -> dict[str, Any]:
    """Freeze the resumable conversation state at handoff time."""
    messages = getattr(session, "messages", []) or []
    return {
        "session_id": session.id,
        "title": getattr(session, "title", ""),
        "message_count": len(messages),
        "compacted": any(
            getattr(m, "kind", "") == "compaction_summary" for m in messages
        ),
        "messages": [m.model_dump(mode="json") for m in messages],
    }


def _expired(record: HandoffRecord) -> bool:
    return now() - record.created_at > HANDOFF_TTL


class HandoffStore:
    """KV-backed handoff records. Survives node restarts like sessions do."""

    def __init__(self, kv: Any | None = None):
        self._kv = kv

    def _persist(self, record: HandoffRecord) -> None:
        if self._kv is None:
            return
        self._kv.put(_HANDOFF_COLLECTION, record.id, record)

    def create(
        self,
        *,
        session_id: str,
        from_device_id: str | None,
        from_device_name: str | None = None,
        target_device_id: str | None = None,
        target_device_name: str | None = None,
        note: str = "",
        snapshot: dict[str, Any] | None = None,
        pending_approval_count: int = 0,
        active_plan_count: int = 0,
    ) -> HandoffRecord:
        record = HandoffRecord(
            session_id=session_id,
            from_device_id=from_device_id,
            from_device_name=from_device_name,
            target_device_id=target_device_id,
            target_device_name=target_device_name,
            note=note,
            snapshot=dict(snapshot or {}),
            pending_approval_count=pending_approval_count,
            active_plan_count=active_plan_count,
        )
        self._persist(record)
        return record

    def get(self, handoff_id: str) -> HandoffRecord:
        if self._kv is None:
            raise KeyError(f"unknown handoff: {handoff_id}")
        for r in self._kv.all(_HANDOFF_COLLECTION, HandoffRecord):
            if r.id == handoff_id:
                return r
        raise KeyError(f"unknown handoff: {handoff_id}")

    def list_pending(self) -> list[HandoffRecord]:
        """Pending handoffs, most recent first. Expired ones are marked."""
        if self._kv is None:
            return []
        pending = []
        for r in self._kv.all(_HANDOFF_COLLECTION, HandoffRecord):
            if r.status is not HandoffStatus.PENDING:
                continue
            if _expired(r):
                r.status = HandoffStatus.EXPIRED
                self._persist(r)
                continue
            pending.append(r)
        return sorted(pending, key=lambda r: r.created_at, reverse=True)

    def claim(self, handoff_id: str, device_id: str | None) -> HandoffRecord:
        """Claim a pending handoff for the calling device.

        Raises KeyError for unknown ids or ids targeted at another device
        (indistinguishable on purpose: no existence leak), ValueError when the
        handoff is no longer claimable.
        """
        record = self.get(handoff_id)
        if record.target_device_id and record.target_device_id != device_id:
            raise KeyError(f"unknown handoff: {handoff_id}")
        if record.status is not HandoffStatus.PENDING:
            raise ValueError(f"handoff is {record.status.value}, not pending")
        if _expired(record):
            record.status = HandoffStatus.EXPIRED
            self._persist(record)
            raise ValueError("handoff expired")
        record.status = HandoffStatus.CLAIMED
        record.claimed_at = now()
        record.claimed_by_device_id = device_id
        self._persist(record)
        return record

    def cancel(self, handoff_id: str, device_id: str | None) -> HandoffRecord:
        """Cancel a pending handoff. Only the creating device may cancel."""
        record = self.get(handoff_id)
        if record.from_device_id != device_id:
            raise KeyError(f"unknown handoff: {handoff_id}")
        if record.status is not HandoffStatus.PENDING:
            raise ValueError(f"handoff is {record.status.value}, not pending")
        record.status = HandoffStatus.CANCELLED
        self._persist(record)
        return record


def note_presence(
    kv: Any,
    device_id: str,
    display_name: str | None = None,
    platform: str | None = None,
) -> DevicePresence:
    """Record a heartbeat for a device. Idempotent per device."""
    existing: DevicePresence | None = None
    for p in kv.all(_PRESENCE_COLLECTION, DevicePresence):
        if p.device_id == device_id:
            existing = p
            break
    if existing is None:
        record = DevicePresence(
            device_id=device_id, display_name=display_name, platform=platform
        )
    else:
        record = existing
        record.last_seen_at = now()
        if display_name:
            record.display_name = display_name
        if platform:
            record.platform = platform
    kv.put(_PRESENCE_COLLECTION, device_id, record)
    return record


def list_presence(kv: Any) -> list[DevicePresence]:
    if kv is None:
        return []
    return sorted(
        kv.all(_PRESENCE_COLLECTION, DevicePresence),
        key=lambda p: p.last_seen_at,
        reverse=True,
    )
