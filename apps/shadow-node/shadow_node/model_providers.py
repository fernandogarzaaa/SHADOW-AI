from __future__ import annotations
import os
import random
import time

import httpx

from .persona import get_system_prompt


def sanitize_proxy_env() -> None:
    """Normalize bracketed IPv6 entries in no_proxy/NO_PROXY.

    httpx (<=0.28) raises ``InvalidURL: Invalid port`` when a no_proxy entry
    looks like ``[::1]`` -- it parses the entry as a URL and chokes on the
    brackets. curl and urllib accept both forms, and bare ``::1`` matches the
    same hosts in httpx, so stripping the brackets is semantics-preserving.
    Without this, every provider call fails in proxied environments whose
    no_proxy contains bracketed IPv6 literals (common on corporate networks).
    Process-local and idempotent.
    """
    for key in ("no_proxy", "NO_PROXY"):
        raw = os.environ.get(key)
        if not raw:
            continue
        parts = []
        for entry in raw.split(","):
            entry = entry.strip()
            if len(entry) > 2 and entry.startswith("[") and entry.endswith("]"):
                entry = entry[1:-1]
            if entry:
                parts.append(entry)
        os.environ[key] = ",".join(parts)


sanitize_proxy_env()


class LocalMockModel:
    """Deterministic offline model used by default and as a safe fallback."""
    name = "local_mock"
    cloud = False

    def complete(self, prompt: str, context: str = "") -> str:
        return "Local mock answer based on approved local context."


DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"


class ModelResponseError(RuntimeError):
    """A cloud model call failed or returned something unusable. Callers
    surface this to the user instead of substituting a fabricated answer."""


class AnthropicProvider:
    """Real Claude model provider.

    Only invoked when cloud use is policy-approved AND an API key is configured.
    Calls the Anthropic Messages API directly over httpx (which honours the
    environment proxy) so no extra SDK dependency is required.
    """
    name = "anthropic"
    cloud = True
    DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"
    # Server-side refusal fallback: on a safety decline the API re-runs the
    # request on a fallback model inside the same call.
    FALLBACK_BETA = "server-side-fallback-2026-07-01"
    RETRY_STATUSES = {429, 500, 502, 503, 529}

    # Bounded so one ask can't hold a request worker for long during an
    # outage: ~2 attempts x 120s worst case plus at most 2 short waits.
    def __init__(self, api_key: str, model_name: str, endpoint: str = "", timeout: float = 120.0,
                 max_tokens: int | None = None, max_retries: int = 2):
        self.api_key = api_key
        self.model_name = model_name or DEFAULT_ANTHROPIC_MODEL
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.timeout = timeout
        self.max_tokens = max_tokens or int(os.getenv("SHADOW_MODEL_MAX_TOKENS", "16000"))
        self.max_retries = max_retries

    def _post(self, headers: dict, payload: dict) -> httpx.Response:
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout)
            except httpx.TransportError as e:
                if attempt == self.max_retries:
                    raise ModelResponseError(f"anthropic: network error: {e}") from e
                time.sleep(delay)
                delay = min(delay * 2, 10.0)
                continue
            if resp.status_code not in self.RETRY_STATUSES or attempt == self.max_retries:
                return resp
            # 429 (rate limit) / 529 (overloaded) / transient 5xx: honour
            # retry-after when present, else exponential backoff with jitter.
            try:
                wait = float(resp.headers.get("retry-after", ""))
            except ValueError:
                wait = delay + random.uniform(0, 0.5)
            time.sleep(min(wait, 10.0))
            delay = min(delay * 2, 10.0)
        return resp  # pragma: no cover - loop always returns

    def complete(self, prompt: str, context: str = "") -> str:
        # Persona-aware system prompt (Phase 1): the user's vibe text is
        # part of the identity; the untrusted-context safety suffix stays.
        system = get_system_prompt()
        user_content = f"<untrusted_context>\n{context}\n</untrusted_context>\n\nUser request: {prompt}"
        payload = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_content}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        if self.endpoint == self.DEFAULT_ENDPOINT:
            # Only on the first-party API: custom endpoints may be proxies or
            # gateways that reject the beta parameter.
            headers["anthropic-beta"] = self.FALLBACK_BETA
            payload["fallbacks"] = "default"
        resp = self._post(headers, payload)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except ValueError:
                detail = resp.text[:200]
            raise ModelResponseError(f"anthropic: HTTP {resp.status_code}: {detail}")
        data = resp.json()
        stop = data.get("stop_reason")
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "".join(parts).strip()
        if stop == "refusal":
            category = (data.get("stop_details") or {}).get("category")
            raise ModelResponseError(f"anthropic: request declined ({category or 'policy'})")
        if stop == "max_tokens":
            # Return what we have, but never silently: mark the truncation.
            return (text + "\n\n[response truncated: max_tokens reached]").strip()
        if not text:
            raise ModelResponseError("anthropic: empty response")
        return text


class ModelProviderConfig:
    """Resolves which model backend is active from environment configuration.

    Defaults to ``local_mock`` (fully offline). A real cloud model is only
    constructed when the provider is a known cloud provider AND its API key is
    present in the environment; otherwise the local mock is used as a safe
    fallback so the node never hard-fails on a missing secret.
    """
    CLOUD_PROVIDERS = {"anthropic"}

    def __init__(self):
        self.cloud_enabled = os.getenv("SHADOW_CLOUD_ENABLED", "false").lower() == "true"
        self.provider = os.getenv("SHADOW_MODEL_PROVIDER", "local_mock")
        self.endpoint = os.getenv("SHADOW_MODEL_ENDPOINT", "")
        self.api_key_env = os.getenv("SHADOW_MODEL_API_KEY_ENV", "ANTHROPIC_API_KEY")
        self.model_name = os.getenv("SHADOW_MODEL_NAME", DEFAULT_ANTHROPIC_MODEL)

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "") if self.api_key_env else ""

    def cloud_model_ready(self) -> bool:
        """True when a real cloud model can actually be invoked."""
        return self.cloud_enabled and self.provider in self.CLOUD_PROVIDERS and bool(self.api_key)

    def cloud_model(self):
        """Construct the configured cloud model, or None if not ready."""
        if not self.cloud_model_ready():
            return None
        if self.provider == "anthropic":
            return AnthropicProvider(self.api_key, self.model_name, self.endpoint)
        return None

    def safe_summary(self) -> dict:
        return {
            "cloud_enabled": self.cloud_enabled,
            "provider": self.provider,
            "endpoint_configured": bool(self.endpoint),
            "api_key_configured": bool(self.api_key),
            "model_name": self.model_name,
            "cloud_model_ready": self.cloud_model_ready(),
        }
