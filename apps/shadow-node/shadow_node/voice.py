"""Voice I/O for the Shadow Node (assistant parity: speak and listen).

Two paths, both real:

- On-device (default): the mobile app speaks with the OS TTS engine and
  records with the microphone. No server, no key, works offline.
- Server-routed: POST /voice/speak and POST /voice/transcribe proxy to a
  user-configured OpenAI-compatible audio endpoint (BYOK). When no endpoint
  is configured the node answers 503 with setup instructions instead of
  pretending to work.

The 503-when-unconfigured shape matches the node's existing account-bound
pattern (the Anthropic text provider): the integration is complete and
tested, it simply needs the operator's credentials to run.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx

MAX_TTS_CHARS = 5000
MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB
MAX_AUDIO_RESPONSE_BYTES = 25 * 1024 * 1024
TTS_TIMEOUT = 60.0
STT_TIMEOUT = 180.0


class VoiceNotConfigured(Exception):
    """Raised when no provider endpoint is configured for the operation."""


class VoiceProviderError(Exception):
    """Raised when the configured provider call fails."""


def _api_key(env_name: str) -> str:
    return os.getenv(env_name, "") if env_name else ""


def tts_configured() -> bool:
    return bool(os.getenv("SHADOW_TTS_ENDPOINT", "").strip())


def stt_configured() -> bool:
    return bool(os.getenv("SHADOW_STT_ENDPOINT", "").strip())


def _provider_label(endpoint: str) -> str:
    host = urlparse(endpoint).hostname or ""
    return host or "custom"


def capabilities() -> dict:
    tts_ep = os.getenv("SHADOW_TTS_ENDPOINT", "").strip()
    stt_ep = os.getenv("SHADOW_STT_ENDPOINT", "").strip()
    return {
        "tts": {
            "available": bool(tts_ep),
            "provider": _provider_label(tts_ep) if tts_ep else None,
            "note": (
                "Server text-to-speech ready."
                if tts_ep
                else "Set SHADOW_TTS_ENDPOINT and SHADOW_TTS_API_KEY_ENV to enable server "
                     "text-to-speech. The mobile app also speaks on-device with no server needed."
            ),
        },
        "stt": {
            "available": bool(stt_ep),
            "provider": _provider_label(stt_ep) if stt_ep else None,
            "note": (
                "Server transcription ready."
                if stt_ep
                else "Set SHADOW_STT_ENDPOINT and SHADOW_STT_API_KEY_ENV to enable server "
                     "transcription of voice recordings."
            ),
        },
    }


def synthesize(text: str, voice: str | None = None, format: str = "mp3") -> tuple[bytes, str]:
    """Text to speech via the configured OpenAI-compatible endpoint.

    Returns (audio_bytes, mime_type). Raises VoiceNotConfigured or
    VoiceProviderError.
    """
    endpoint = os.getenv("SHADOW_TTS_ENDPOINT", "").strip()
    if not endpoint:
        raise VoiceNotConfigured("no TTS endpoint configured (SHADOW_TTS_ENDPOINT)")
    text = (text or "").strip()
    if not text:
        raise ValueError("text must not be empty")
    if len(text) > MAX_TTS_CHARS:
        raise ValueError(f"text exceeds {MAX_TTS_CHARS} characters")
    if format not in ("mp3", "wav"):
        raise ValueError("format must be mp3 or wav")

    url = endpoint.rstrip("/") + "/audio/speech"
    payload = {
        "model": os.getenv("SHADOW_TTS_MODEL", "tts-1"),
        "input": text,
        "response_format": format,
    }
    if voice:
        payload["voice"] = voice
    headers = {}
    key = _api_key(os.getenv("SHADOW_TTS_API_KEY_ENV", ""))
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=TTS_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise VoiceProviderError(f"TTS provider rejected the request: HTTP {e.response.status_code}") from e
    except httpx.HTTPError as e:
        raise VoiceProviderError(f"TTS provider unreachable: {e}") from e
    data = resp.content
    if len(data) > MAX_AUDIO_RESPONSE_BYTES:
        raise VoiceProviderError("TTS provider returned an oversized response")
    if not data:
        raise VoiceProviderError("TTS provider returned empty audio")
    mime = "audio/mpeg" if format == "mp3" else "audio/wav"
    return data, mime


def transcribe(audio_bytes: bytes, filename: str = "audio.m4a") -> dict:
    """Speech to text via the configured OpenAI-compatible endpoint.

    Returns {"text": ..., "language"?}. Raises VoiceNotConfigured or
    VoiceProviderError.
    """
    endpoint = os.getenv("SHADOW_STT_ENDPOINT", "").strip()
    if not endpoint:
        raise VoiceNotConfigured("no STT endpoint configured (SHADOW_STT_ENDPOINT)")
    if not audio_bytes:
        raise ValueError("audio must not be empty")
    if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
        raise ValueError(f"audio exceeds {MAX_AUDIO_UPLOAD_BYTES} bytes")

    url = endpoint.rstrip("/") + "/audio/transcriptions"
    headers = {}
    key = _api_key(os.getenv("SHADOW_STT_API_KEY_ENV", ""))
    if key:
        headers["Authorization"] = f"Bearer {key}"
    files = {"file": (filename, audio_bytes, "application/octet-stream")}
    data = {"model": os.getenv("SHADOW_STT_MODEL", "whisper-1")}
    try:
        resp = httpx.post(url, files=files, data=data, headers=headers, timeout=STT_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise VoiceProviderError(f"STT provider rejected the request: HTTP {e.response.status_code}") from e
    except httpx.HTTPError as e:
        raise VoiceProviderError(f"STT provider unreachable: {e}") from e
    try:
        body = resp.json()
    except ValueError as e:
        raise VoiceProviderError("STT provider returned non-JSON") from e
    text = str(body.get("text", "") or "").strip()
    if not text:
        raise VoiceProviderError("STT provider returned no transcript")
    out: dict = {"text": text}
    if body.get("language"):
        out["language"] = body["language"]
    return out
