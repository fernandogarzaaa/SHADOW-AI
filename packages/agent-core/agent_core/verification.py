"""Evidence-based completion for the SHADOW node.

Core principle: execution is not success. A state-changing action must produce
evidence that the intended world-state change actually occurred.

Every call through ``AgentCore.execute`` produces an :class:`ExecutionRecord`
carrying the intent, the policy decision, the tool observation, before/after
world-state snapshots, and a final deterministic verdict: one of VERIFIED,
FAILED, UNCERTAIN, or CONFLICTING. The rules are deliberately mechanical and
explainable; there is no LLM acting as judge.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from .models import AgentAction, new_id, now

# Tools whose handlers are expected to change on-disk workspace state.
MUTATING_TOOLS = frozenset({
    "note.create",
    "note.append",
    "reminder.create",
    "calendar.create",
    "email.draft",
})

# Tools that only observe; they never change world state.
READ_ONLY_TOOLS = frozenset({
    "note.list",
    "http.get",
})

# Safety caps so a hostile or huge workspace cannot blow up verification.
_MAX_SNAPSHOT_FILES = 5000
_MAX_READ_BYTES = 1 << 20  # 1 MiB per file for content checks


class VerificationStatus(str, Enum):
    """Final verdict on an execution. Exactly one of these, never 'success'."""

    VERIFIED = "verified"        # evidence confirms the intended world-state change
    FAILED = "failed"            # the action clearly did not achieve its intent
    UNCERTAIN = "uncertain"      # the outcome cannot be determined from evidence
    CONFLICTING = "conflicting"  # observed state contradicts the intended change


class FileState(BaseModel):
    exists: bool = True
    sha256: str = ""
    size: int = 0


class WorldStateDiff(BaseModel):
    """Before/after diff of the observable workspace."""

    before: dict[str, FileState] = Field(default_factory=dict)
    after: dict[str, FileState] = Field(default_factory=dict)
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.modified)


class EvidenceItem(BaseModel):
    kind: str  # policy_decision | tool_output | world_state_diff | error
    summary: str
    data: dict = Field(default_factory=dict)


class ExecutionRecord(BaseModel):
    """The complete, auditable trace of one agent action execution."""

    id: str = Field(default_factory=lambda: new_id("exec"))
    intent: str = ""
    action: AgentAction | None = None
    approval_id: str | None = None
    approved: bool = False
    double_confirmed: bool = False
    policy_allowed: bool = False
    policy_reason: str = ""
    tool_result: dict | None = None
    tool_error: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    world_state: WorldStateDiff | None = None
    verification: VerificationStatus = VerificationStatus.UNCERTAIN
    verification_reason: str = "not yet verified"
    started_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None

    def summary(self) -> dict:
        return {
            "id": self.id,
            "intent": self.intent,
            "tool_name": self.action.tool_name if self.action else None,
            "approval_id": self.approval_id,
            "verification": self.verification.value,
            "verification_reason": self.verification_reason,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def workspace_root() -> Path:
    """Resolve the observable workspace dir (same default as the action executor)."""
    return Path(os.getenv("SHADOW_WORKSPACE_DIR", "data/workspace"))


def snapshot_workspace(root: Path) -> dict[str, FileState]:
    """Capture a deterministic snapshot of every file under root.

    Read-only: never creates or mutates anything. Missing root snapshots as empty.
    """
    snap: dict[str, FileState] = {}
    if not root.is_dir():
        return snap
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if count >= _MAX_SNAPSHOT_FILES:
            break
        count += 1
        rel = path.relative_to(root).as_posix()
        try:
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    digest.update(chunk)
                    size += len(chunk)
            snap[rel] = FileState(exists=True, sha256=digest.hexdigest(), size=size)
        except OSError:
            continue
    return snap


def diff_snapshots(before: dict[str, FileState], after: dict[str, FileState]) -> WorldStateDiff:
    added = sorted(p for p in after if p not in before)
    removed = sorted(p for p in before if p not in after)
    modified = sorted(
        p for p in after
        if p in before and (after[p].sha256 != before[p].sha256 or after[p].size != before[p].size)
    )
    return WorldStateDiff(before=before, after=after, added=added, removed=removed, modified=modified)


def _read_text_capped(root: Path, rel: str) -> str:
    try:
        data = (root / rel).read_bytes()[:_MAX_READ_BYTES]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _md_files(paths: list[str]) -> list[str]:
    return [p for p in paths if p.endswith(".md")]


def _intent_check(tool_name: str, params: dict, diff: WorldStateDiff, root: Path) -> tuple[bool, str]:
    """Deterministic predicate: does the observed diff match the stated intent?

    Returns (matches, detail). Each check reads back the actual world state;
    nothing is trusted from the tool's own report.
    """
    changed_md = _md_files(diff.added + diff.modified)
    if tool_name == "note.create":
        title = str(params.get("title", ""))
        for rel in changed_md:
            if title and title in _read_text_capped(root, rel):
                return True, f"note file {rel} contains the requested title"
        return False, "no created or modified note contains the requested title"
    if tool_name == "note.append":
        body = str(params.get("body", ""))
        for rel in changed_md:
            if body in _read_text_capped(root, rel):
                return True, f"note file {rel} contains the appended body"
        return False, "no modified note contains the appended body"
    if tool_name == "reminder.create":
        text = str(params.get("text", ""))
        rel = "reminders.jsonl"
        if rel in diff.added or rel in diff.modified:
            if text and text in _read_text_capped(root, rel):
                return True, "reminders.jsonl contains the new reminder text"
            return False, "reminders.jsonl changed but the reminder text is missing"
        return False, "reminders.jsonl was not written"
    if tool_name == "calendar.create":
        title = str(params.get("title", ""))
        rel = "calendar_events.jsonl"
        if rel in diff.added or rel in diff.modified:
            if title and title in _read_text_capped(root, rel):
                return True, "calendar_events.jsonl contains the new event title"
            return False, "calendar_events.jsonl changed but the event title is missing"
        return False, "calendar_events.jsonl was not written"
    if tool_name == "email.draft":
        subject = str(params.get("subject", ""))
        drafts = [p for p in diff.added if p.startswith("drafts/")]
        for rel in drafts:
            if subject and subject in _read_text_capped(root, rel):
                return True, f"draft file {rel} contains the requested subject"
        return False, "no new draft file contains the requested subject"
    return False, f"no intent check defined for tool {tool_name}"


def _read_only_check(tool_name: str, result: dict) -> tuple[bool, str]:
    if tool_name == "http.get":
        if "status" in result and "body" in result:
            return True, f"observation returned: HTTP {result.get('status')}"
        return False, "http.get response is missing status or body"
    if tool_name == "note.list":
        notes = result.get("notes")
        if isinstance(notes, list):
            return True, f"observation returned: {len(notes)} notes listed"
        return False, "note.list response is missing the notes list"
    return False, f"no observation check defined for read-only tool {tool_name}"


def verify_execution(
    action: AgentAction,
    policy_allowed: bool,
    policy_reason: str,
    tool_result: dict | None,
    tool_error: str | None,
    diff: WorldStateDiff | None,
    root: Path | None,
) -> tuple[VerificationStatus, str]:
    """Classify an execution. Pure function: no I/O, no LLM, fully deterministic."""
    if not policy_allowed:
        return VerificationStatus.FAILED, f"blocked by policy: {policy_reason}"
    if tool_error:
        return VerificationStatus.FAILED, f"tool raised an error: {tool_error[:300]}"
    if tool_result is None:
        return VerificationStatus.FAILED, "tool returned no result"
    if isinstance(tool_result, dict) and tool_result.get("ok") is False:
        reason = tool_result.get("reason") or "the tool reported failure"
        return VerificationStatus.FAILED, f"tool reported failure: {str(reason)[:300]}"
    if isinstance(tool_result, dict) and tool_result.get("status") == "mock_executed":
        return (
            VerificationStatus.UNCERTAIN,
            "no registered tool handler exists; the mock run has no observable world-state effect to check",
        )
    name = action.tool_name
    if name in READ_ONLY_TOOLS:
        ok, detail = _read_only_check(name, tool_result if isinstance(tool_result, dict) else {})
        return (VerificationStatus.VERIFIED, detail) if ok else (VerificationStatus.UNCERTAIN, detail)
    if name in MUTATING_TOOLS:
        if diff is None or root is None:
            return VerificationStatus.UNCERTAIN, "world state could not be observed for this run"
        if not diff.changed:
            return (
                VerificationStatus.FAILED,
                "tool reported success but world state did not change",
            )
        matches, detail = _intent_check(name, action.params or {}, diff, root)
        if matches:
            return VerificationStatus.VERIFIED, detail
        return VerificationStatus.CONFLICTING, f"observed state contradicts the intended change: {detail}"
    return (
        VerificationStatus.UNCERTAIN,
        f"tool {name} is outside the known read-only and mutating sets; intent could not be checked",
    )


def json_safe(value):
    """Coerce an arbitrary tool result into JSON-serializable data for storage."""
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return {"unserializable": str(type(value))}


def evidence_policy(allowed: bool, reason: str) -> EvidenceItem:
    return EvidenceItem(
        kind="policy_decision",
        summary=f"policy {'allowed' if allowed else 'blocked'} execution: {reason}",
        data={"allowed": allowed, "reason": reason},
    )


def evidence_tool_output(result: dict | None) -> EvidenceItem:
    return EvidenceItem(
        kind="tool_output",
        summary="tool observation captured",
        data={"result": json_safe(result or {})},
    )


def evidence_world_state(diff: WorldStateDiff) -> EvidenceItem:
    return EvidenceItem(
        kind="world_state_diff",
        summary=(
            f"world state: {len(diff.added)} added, "
            f"{len(diff.modified)} modified, {len(diff.removed)} removed"
        ),
        data={"added": diff.added, "modified": diff.modified, "removed": diff.removed},
    )


def evidence_error(error: str) -> EvidenceItem:
    return EvidenceItem(
        kind="error",
        summary=f"execution raised: {error[:200]}",
        data={"error": error[:2000]},
    )
