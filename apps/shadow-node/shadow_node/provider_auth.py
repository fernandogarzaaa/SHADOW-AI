"""Provider credentials + OAuth (PKCE) sign-in for frontier model providers.

Two real, legitimate ways to connect a frontier provider:

- **API key** — stored encrypted on the local node (never logged, never in git).
- **OAuth (PKCE)** — for providers that genuinely support programmatic inference
  via OAuth. Google (Gemini/Vertex) is the real example; the flow is standard
  Authorization-Code-with-PKCE.

We deliberately do NOT implement "use my ChatGPT Plus / Claude Pro / Gemini
Advanced subscription" — those consumer subscriptions cannot legitimately power
third-party API calls. ``CATALOG[provider]["subscription_oauth"]`` is False for
all current providers to make that explicit in the UI.
"""
from __future__ import annotations
import os, json, base64, hashlib, secrets
from pathlib import Path
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet
from .crypto_config import load_fernet_key
from .providers import CATALOG


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


# OAuth endpoint configs for providers that support programmatic OAuth inference.
OAUTH = {
    "gemini": {
        "auth_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/generative-language.retriever https://www.googleapis.com/auth/cloud-platform",
        "client_id_env": "GOOGLE_OAUTH_CLIENT_ID",
        "client_secret_env": "GOOGLE_OAUTH_CLIENT_SECRET",
        "extra": {"access_type": "offline", "prompt": "consent"},
    },
}


class CredentialStore:
    """Encrypted at-rest store for per-provider credentials."""

    def __init__(self, path: str | None = None, key: bytes | None = None):
        self.path = Path(path or os.getenv("SHADOW_PROVIDERS_FILE", "data/keys/providers.enc"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.key = key or load_fernet_key("SHADOW_PROVIDERS_KEY", "SHADOW_PROVIDERS_KEY_FILE", "data/keys/providers.key")
        self.cipher = Fernet(self.key)
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.cipher.decrypt(self.path.read_bytes()).decode())
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self.path.write_bytes(self.cipher.encrypt(json.dumps(self._data).encode()))
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def set(self, provider: str, cred: dict) -> None:
        self._data[provider] = cred
        self._save()

    def get(self, provider: str) -> dict | None:
        return self._data.get(provider)

    def delete(self, provider: str) -> None:
        self._data.pop(provider, None)
        self._save()

    def resolve(self, provider: str) -> dict | None:
        """Resolve a usable credential: stored creds first, else env API key."""
        cred = self.get(provider)
        if cred and (cred.get("api_key") or cred.get("oauth_token")):
            return cred
        env_key = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}.get(provider)
        if env_key and os.getenv(env_key):
            return {"type": "api_key", "api_key": os.getenv(env_key), "source": "env"}
        return None

    def status(self) -> list[dict]:
        out = []
        for name, spec in CATALOG.items():
            cred = self.resolve(name)
            out.append({
                "provider": name,
                "label": spec["label"],
                "default_model": spec["default_model"],
                "auth_methods": spec["auth_methods"],
                "subscription_oauth": spec["subscription_oauth"],
                "oauth_supported": name in OAUTH,
                "note": spec["note"],
                "connected": bool(cred),
                "credential_type": (cred or {}).get("type"),
                "credential_source": (cred or {}).get("source", "stored" if cred else None),
            })
        return out


# --- OAuth (PKCE) helpers ---

def start_oauth(provider: str, redirect_uri: str) -> dict:
    cfg = OAUTH.get(provider)
    if not cfg:
        raise ValueError(f"{provider} does not support programmatic OAuth")
    client_id = os.getenv(cfg["client_id_env"], "")
    if not client_id:
        raise ValueError(f"set {cfg['client_id_env']} to enable {provider} OAuth")
    verifier = secrets.token_urlsafe(64)
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": cfg["scope"],
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        **cfg.get("extra", {}),
    }
    return {
        "authorization_url": f"{cfg['auth_endpoint']}?{urlencode(params)}",
        "state": state,
        "code_verifier": verifier,
    }


def exchange_code(provider: str, code: str, code_verifier: str, redirect_uri: str, timeout: float = 30.0) -> dict:
    cfg = OAUTH.get(provider)
    if not cfg:
        raise ValueError(f"{provider} does not support OAuth")
    data = {
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "client_id": os.getenv(cfg["client_id_env"], ""),
        "client_secret": os.getenv(cfg["client_secret_env"], ""),
    }
    r = httpx.post(cfg["token_endpoint"], data=data, timeout=timeout)
    r.raise_for_status()
    tok = r.json()
    return {"type": "oauth", "oauth_token": tok.get("access_token"), "refresh_token": tok.get("refresh_token"), "source": "oauth"}
