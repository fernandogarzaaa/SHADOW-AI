from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
from uuid import uuid4

def now(): return datetime.now(timezone.utc)
class MemoryType(str, Enum):
    USER_FACT="user_fact"; PREFERENCE="preference"; WRITING_STYLE="writing_style"; ROUTINE="routine"; TASK="task"; CONTACT_ENTITY="contact_entity"; PROJECT="project"; DOCUMENT_CHUNK="document_chunk"; EMAIL_CHUNK="email_chunk"; CALENDAR_CONTEXT="calendar_context"; SENSITIVE_ITEM="sensitive_item"
class MemoryCategory(str, Enum): PROFILE="profile"; PROJECT="project"; NOTE="note"; CONNECTOR="connector"; SENSITIVE="sensitive"; TASK="task"
class MemorySource(BaseModel):
    id: str=Field(default_factory=lambda:f"src_{uuid4().hex}"); kind: str; title: str; uri: str|None=None; consent_grant_id: str|None=None; version: int=1
class MemoryItem(BaseModel):
    id: str=Field(default_factory=lambda:f"mem_{uuid4().hex}"); type: MemoryType=MemoryType.DOCUMENT_CHUNK; category: MemoryCategory=MemoryCategory.NOTE; text: str; source: MemorySource; tags: list[str]=[]; confidence: float=0.5; sensitive: bool=False; do_not_send_to_cloud: bool=False; content_hash: str|None=None; created_at: datetime=Field(default_factory=now); updated_at: datetime=Field(default_factory=now); revoked_at: datetime|None=None; expires_at: datetime|None=None
class SearchResult(BaseModel):
    item: MemoryItem; score: float; freshness: float; attribution: str; explanation: str; untrusted_context: bool=True
