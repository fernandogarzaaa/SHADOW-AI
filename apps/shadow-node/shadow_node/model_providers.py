from __future__ import annotations
import os
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

    def __init__(self, api_key: str, model_name: str, endpoint: str = "", timeout: float = 60.0):
        self.api_key = api_key
        self.model_name = model_name
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.timeout = timeout

    def complete(self, prompt: str, context: str = "") -> str:
        # Persona-aware system prompt (Phase 1): the user's vibe text is
        # part of the identity; the untrusted-context safety suffix stays.
        system = get_system_prompt()
        user_content = f"<untrusted_context>\n{context}\n</untrusted_context>\n\nUser request: {prompt}"
        payload = {
            "model": self.model_name,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": user_content}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        resp = httpx.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        return "".join(parts).strip() or "(empty response)"


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
        self.model_name = os.getenv("SHADOW_MODEL_NAME", "claude-sonnet-4-6")

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
