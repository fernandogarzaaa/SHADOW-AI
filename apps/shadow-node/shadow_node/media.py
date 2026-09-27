"""Image generation for the Shadow Node (assistant parity: media).

Server-routed, BYOK: POST /media/generate calls a user-configured
OpenAI-compatible /images/generations endpoint and persists the returned
PNG bytes (base64) in the encrypted runtime store, capped so a personal
node cannot grow without bound. When no endpoint is configured the node
answers 503 with setup instructions.

Like the voice module, the integration is complete and exercised in tests
against a stub transport; it needs the operator's credentials to run.
"""
from __future__ import annotations

import base64
import os
import time
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field, field_validator

MEDIA_SIZES = ("1024x1024", "1792x1024", "1024x1792")
MAX_PROMPT_CHARS = 2000
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MiB per image
MEDIA_CAP = 200  # images kept
IMAGE_TIMEOUT = 120.0


class MediaNotConfigured(Exception):
    pass


class MediaProviderError(Exception):
    pass


def image_configured() -> bool:
    return bool(os.getenv("SHADOW_IMAGE_ENDPOINT", "").strip())


def capabilities() -> dict:
    ep = os.getenv("SHADOW_IMAGE_ENDPOINT", "").strip()
    host = urlparse(ep).hostname if ep else ""
    return {
        "generate": {
            "available": bool(ep),
            "provider": host or None if ep else None,
            "note": (
                "Image generation ready."
                if ep
                else "Set SHADOW_IMAGE_ENDPOINT and SHADOW_IMAGE_API_KEY_ENV to enable "
                     "image generation (OpenAI-compatible /images/generations)."
            ),
        }
    }


class MediaGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    size: str = "1024x1024"

    @field_validator("size")
    @classmethod
    def _size(cls, v: str) -> str:
        if v not in MEDIA_SIZES:
            raise ValueError(f"size must be one of {MEDIA_SIZES}")
        return v


class MediaItem(BaseModel):
    id: str = Field(default_factory=lambda: f"img_{uuid4().hex}")
    prompt: str
    size: str
    mime: str = "image/png"
    data_b64: str = ""
    created_at: float = Field(default_factory=time.time)

    def meta(self) -> dict:
        d = self.model_dump()
        data = d.pop("data_b64")
        d["bytes"] = len(base64.b64decode(data)) if data else 0
        return d


def generate_image(prompt: str, size: str = "1024x1024") -> tuple[bytes, str]:
    """Generate one image via the configured provider.

    Returns (png_bytes, mime). Raises MediaNotConfigured / MediaProviderError.
    """
    endpoint = os.getenv("SHADOW_IMAGE_ENDPOINT", "").strip()
    if not endpoint:
        raise MediaNotConfigured("no image endpoint configured (SHADOW_IMAGE_ENDPOINT)")
    prompt = (prompt or "").strip()
    if not prompt or len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError("prompt must be 1..2000 characters")
    if size not in MEDIA_SIZES:
        raise ValueError(f"size must be one of {MEDIA_SIZES}")

    url = endpoint.rstrip("/") + "/images/generations"
    headers = {}
    key_env = os.getenv("SHADOW_IMAGE_API_KEY_ENV", "")
    key = os.getenv(key_env, "") if key_env else ""
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": os.getenv("SHADOW_IMAGE_MODEL", "dall-e-3"),
        "prompt": prompt,
        "size": size,
        "response_format": "b64_json",
        "n": 1,
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise MediaProviderError(f"image provider rejected the request: HTTP {e.response.status_code}") from e
    except httpx.HTTPError as e:
        raise MediaProviderError(f"image provider unreachable: {e}") from e
    try:
        body = resp.json()
        b64 = body["data"][0]["b64_json"]
        raw = base64.b64decode(b64)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise MediaProviderError("image provider returned an unusable payload") from e
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise MediaProviderError("image provider returned an empty or oversized image")
    return raw, "image/png"


class MediaStore:
    """Bounded image journal with encrypted runtime-store persistence."""

    def __init__(self, runtime_store=None):
        self._store = runtime_store
        self._items: dict[str, MediaItem] = {}
        if runtime_store is not None:
            for item in runtime_store.all("media", MediaItem):
                self._items[item.id] = item
            ordered = sorted(self._items.values(), key=lambda i: i.created_at, reverse=True)
            for old in ordered[MEDIA_CAP:]:
                self._drop(old.id)

    def _persist(self, item: MediaItem) -> None:
        if self._store is not None:
            self._store.put("media", item.id, item)

    def _drop(self, item_id: str) -> None:
        self._items.pop(item_id, None)
        if self._store is not None:
            self._store.delete("media", item_id)

    def add(self, prompt: str, size: str, data: bytes, mime: str = "image/png") -> MediaItem:
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("image must be 1..10 MiB")
        item = MediaItem(prompt=prompt, size=size, mime=mime,
                         data_b64=base64.b64encode(data).decode())
        self._items[item.id] = item
        self._persist(item)
        if len(self._items) > MEDIA_CAP:
            oldest = min(self._items.values(), key=lambda i: i.created_at)
            self._drop(oldest.id)
        return item

    def get(self, item_id: str) -> MediaItem | None:
        return self._items.get(item_id)

    def content(self, item_id: str) -> tuple[bytes, str] | None:
        item = self._items.get(item_id)
        if item is None or not item.data_b64:
            return None
        return base64.b64decode(item.data_b64), item.mime

    def list(self, limit: int = 20, offset: int = 0) -> tuple[list[MediaItem], int]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        items = sorted(self._items.values(), key=lambda i: i.created_at, reverse=True)
        return items[offset:offset + limit], len(items)

    def delete(self, item_id: str) -> bool:
        if item_id not in self._items:
            return False
        self._drop(item_id)
        return True
