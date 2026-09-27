"""Durable artifacts for the Shadow Node (assistant parity: documents that persist).

An artifact is a versioned document the assistant builds for the user:
notes, reports, code, tables, pages. Fully offline: content lives in the
encrypted runtime store (or in-memory when no DB is configured), versions
are append-only, and caps keep the store bounded.

The agent creates and revises artifacts through the `artifact_create`,
`artifact_update`, and `artifact_read` tools; the mobile app browses,
edits, and restores versions through the /artifacts REST endpoints.
"""
from __future__ import annotations

import time
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

ARTIFACT_KINDS = ("markdown", "html", "code", "csv", "json", "text")
MAX_TITLE_LEN = 200
MAX_CONTENT_BYTES = 1024 * 1024  # 1 MiB per artifact version
MAX_TAGS = 10
MAX_TAG_LEN = 40
ARTIFACT_CAP = 500  # newest artifacts kept
VERSION_CAP = 50  # versions kept per artifact
AGENT_READ_LIMIT = 20_000  # chars returned to the agent per read


class ArtifactCreate(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE_LEN)
    kind: str = "markdown"
    content: str = ""
    tags: list[str] = Field(default_factory=list)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in ARTIFACT_KINDS:
            raise ValueError(f"kind must be one of {ARTIFACT_KINDS}")
        return v

    @field_validator("content")
    @classmethod
    def _content_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise ValueError(f"content exceeds {MAX_CONTENT_BYTES} bytes")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        if len(v) > MAX_TAGS:
            raise ValueError(f"at most {MAX_TAGS} tags")
        for t in v:
            if len(t) > MAX_TAG_LEN:
                raise ValueError(f"tag too long: {t[:20]}...")
        return v


class ArtifactUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LEN)
    kind: str | None = None
    content: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str | None) -> str | None:
        if v is not None and v not in ARTIFACT_KINDS:
            raise ValueError(f"kind must be one of {ARTIFACT_KINDS}")
        return v

    @field_validator("content")
    @classmethod
    def _content_size(cls, v: str | None) -> str | None:
        if v is not None and len(v.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise ValueError(f"content exceeds {MAX_CONTENT_BYTES} bytes")
        return v


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: f"art_{uuid4().hex}")
    title: str
    kind: str = "markdown"
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    version: int = 1
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def meta(self) -> dict:
        d = self.model_dump()
        d.pop("content")
        d["size_bytes"] = len(self.content.encode("utf-8"))
        return d


class ArtifactVersion(BaseModel):
    artifact_id: str
    version: int
    title: str
    kind: str
    content: str
    created_at: float


class ArtifactStore:
    """Versioned artifact journal with encrypted runtime-store persistence."""

    def __init__(self, runtime_store=None):
        self._store = runtime_store
        self._artifacts: dict[str, Artifact] = {}
        if runtime_store is not None:
            for a in runtime_store.all("artifacts", Artifact):
                self._artifacts[a.id] = a
            # Retention: keep the newest ARTIFACT_CAP, drop the rest with
            # their version rows so restarts do not resurrect pruned items.
            ordered = sorted(self._artifacts.values(), key=lambda a: a.created_at, reverse=True)
            for old in ordered[ARTIFACT_CAP:]:
                self._drop(old.id)

    # -- persistence helpers ------------------------------------------------
    def _persist(self, artifact: Artifact) -> None:
        if self._store is not None:
            self._store.put("artifacts", artifact.id, artifact)

    def _persist_version(self, v: ArtifactVersion) -> None:
        if self._store is not None:
            self._store.put("artifact_versions", f"{v.artifact_id}:v{v.version}", v)

    def _drop(self, artifact_id: str) -> None:
        self._artifacts.pop(artifact_id, None)
        if self._store is not None:
            self._store.delete("artifacts", artifact_id)
            for row in self._store.all("artifact_versions", ArtifactVersion):
                if row.artifact_id == artifact_id:
                    self._store.delete("artifact_versions", f"{row.artifact_id}:v{row.version}")

    def _versions(self, artifact_id: str) -> list[ArtifactVersion]:
        if self._store is not None:
            rows = [r for r in self._store.all("artifact_versions", ArtifactVersion)
                    if r.artifact_id == artifact_id]
        else:
            rows = getattr(self, "_mem_versions", {}).get(artifact_id, [])
        return sorted(rows, key=lambda r: r.version)

    def _remember_version(self, v: ArtifactVersion) -> None:
        if self._store is None:
            self._mem_versions = getattr(self, "_mem_versions", {})
            self._mem_versions.setdefault(v.artifact_id, []).append(v)
        self._persist_version(v)
        # Prune oldest versions beyond the cap.
        rows = self._versions(v.artifact_id)
        for old in rows[:-VERSION_CAP] if len(rows) > VERSION_CAP else []:
            if self._store is not None:
                self._store.delete("artifact_versions", f"{old.artifact_id}:v{old.version}")
            else:
                self._mem_versions[v.artifact_id].remove(old)

    # -- public API ----------------------------------------------------------
    def create(self, req: ArtifactCreate) -> Artifact:
        now = time.time()
        a = Artifact(title=req.title.strip(), kind=req.kind, content=req.content,
                     tags=req.tags, version=1, created_at=now, updated_at=now)
        self._artifacts[a.id] = a
        self._persist(a)
        self._remember_version(ArtifactVersion(artifact_id=a.id, version=1, title=a.title,
                                              kind=a.kind, content=a.content, created_at=now))
        # Enforce the artifact cap: evict the oldest.
        if len(self._artifacts) > ARTIFACT_CAP:
            oldest = min(self._artifacts.values(), key=lambda x: x.created_at)
            self._drop(oldest.id)
        return a

    def get(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def list(self, limit: int = 20, offset: int = 0, kind: str | None = None) -> tuple[list[Artifact], int]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        items = sorted(self._artifacts.values(), key=lambda a: a.updated_at, reverse=True)
        if kind:
            items = [a for a in items if a.kind == kind]
        return items[offset:offset + limit], len(items)

    def update(self, artifact_id: str, req: ArtifactUpdate) -> Artifact | None:
        a = self._artifacts.get(artifact_id)
        if a is None:
            return None
        if req.title is not None:
            a.title = req.title.strip()
        if req.kind is not None:
            a.kind = req.kind
        if req.content is not None:
            a.content = req.content
        a.version += 1
        a.updated_at = time.time()
        self._persist(a)
        self._remember_version(ArtifactVersion(artifact_id=a.id, version=a.version, title=a.title,
                                              kind=a.kind, content=a.content, created_at=a.updated_at))
        return a

    def versions(self, artifact_id: str) -> list[dict] | None:
        if artifact_id not in self._artifacts:
            return None
        return [{"version": v.version, "created_at": v.created_at,
                 "size_bytes": len(v.content.encode("utf-8"))} for v in self._versions(artifact_id)]

    def get_version(self, artifact_id: str, version: int) -> Artifact | None:
        a = self._artifacts.get(artifact_id)
        if a is None:
            return None
        for v in self._versions(artifact_id):
            if v.version == version:
                return Artifact(id=a.id, title=v.title, kind=v.kind, content=v.content,
                                tags=a.tags, version=v.version, created_at=a.created_at,
                                updated_at=v.created_at)
        return None

    def delete(self, artifact_id: str) -> bool:
        if artifact_id not in self._artifacts:
            return False
        self._drop(artifact_id)
        return True
