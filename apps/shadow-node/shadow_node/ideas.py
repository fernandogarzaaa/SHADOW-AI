"""Idea cards for the Shadow Node (Cookie/Muse.AI parity, local-first).

An idea is a lightweight card: a title, an optional description, and a
lifecycle (new -> running -> done, or dismissed). Running an idea turns it
into a real agent plan via the normal AgentCore propose path; any risky
action in the plan raises an approval request and executes only through the
approval-gated /agent/execute path. Ideas persist encrypted in the runtime
store's "ideas" collection when configured, in-memory otherwise.
"""
from __future__ import annotations

import time
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

MAX_TITLE_LEN = 140
MAX_DESC_LEN = 2000

IDEA_STATUSES = ("new", "running", "done", "dismissed")


class PlannedAction(BaseModel):
    description: str
    requires_approval: bool = False


class Idea(BaseModel):
    id: str = Field(default_factory=lambda: f"idea_{uuid4().hex}")
    title: str
    description: str = ""
    status: str = "new"
    plan: list[PlannedAction] = []
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > MAX_TITLE_LEN:
            raise ValueError(f"title must be at most {MAX_TITLE_LEN} chars")
        return v

    @field_validator("description")
    @classmethod
    def _description(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) > MAX_DESC_LEN:
            raise ValueError(f"description must be at most {MAX_DESC_LEN} chars")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in IDEA_STATUSES:
            raise ValueError(f"status must be one of {IDEA_STATUSES}")
        return v


class IdeaCreate(BaseModel):
    title: str
    description: str = ""

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > MAX_TITLE_LEN:
            raise ValueError(f"title must be at most {MAX_TITLE_LEN} chars")
        return v


class IdeaUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    description: str | None = Field(default=None, max_length=MAX_DESC_LEN)
    status: str | None = None


class IdeaStore:
    def __init__(self, runtime_store=None):
        self._store = runtime_store
        self.ideas: dict[str, Idea] = {}
        if runtime_store is not None:
            for i in runtime_store.all("ideas", Idea):
                self.ideas[i.id] = i

    def _save(self, idea: Idea) -> None:
        if self._store is not None:
            self._store.put("ideas", idea.id, idea)

    def _drop(self, idea_id: str) -> None:
        if self._store is not None:
            self._store.delete("ideas", idea_id)

    def create(self, data: IdeaCreate) -> Idea:
        idea = Idea(title=data.title, description=data.description or "")
        self.ideas[idea.id] = idea
        self._save(idea)
        return idea

    def get(self, idea_id: str) -> Idea | None:
        return self.ideas.get(idea_id)

    def list(self, status: str | None = None) -> list[Idea]:
        ideas = list(self.ideas.values())
        if status:
            ideas = [i for i in ideas if i.status == status]
        ideas.sort(key=lambda i: i.updated_at, reverse=True)
        return ideas

    def update(self, idea_id: str, patch: IdeaUpdate) -> Idea | None:
        idea = self.ideas.get(idea_id)
        if idea is None:
            return None
        data = idea.model_dump()
        if patch.title is not None:
            data["title"] = patch.title
        if patch.description is not None:
            data["description"] = patch.description
        if patch.status is not None:
            data["status"] = patch.status
        data["updated_at"] = time.time()
        idea = Idea(**data)  # re-validate
        self.ideas[idea_id] = idea
        self._save(idea)
        return idea

    def delete(self, idea_id: str) -> bool:
        if idea_id not in self.ideas:
            return False
        del self.ideas[idea_id]
        self._drop(idea_id)
        return True

    def mark_running(self, idea_id: str, plan: list[PlannedAction]) -> Idea | None:
        idea = self.ideas.get(idea_id)
        if idea is None:
            return None
        idea.plan = plan
        idea.status = "running"
        idea.updated_at = time.time()
        self._save(idea)
        return idea
