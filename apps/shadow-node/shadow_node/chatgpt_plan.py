"""Use your ChatGPT plan: OpenAI's "Sign in with ChatGPT" (SIWC) plan usage.

OpenAI's open-source/locally-hosted program lets an app send Responses API
requests billed to the user's ChatGPT Plus/Pro plan. Shadow is open source
and runs on the user's own machine, which is the eligible case. See
docs/research/subscription-auth-2026-10.md for the sources; the protocol
here follows developers.openai.com/siwc/token-sharing-open-source:

- OAuth Authorization Code + PKCE (S256), public client, no secret. First
  sign-in registers dynamically with client_id=dynamic_agent_client and a
  stable per-host ext_agent_host_id; later sign-ins reuse the issued id.
- Redirect is an HTTP loopback on 127.0.0.1 (never "localhost").
- The ID token is verified against OpenAI's JWKS (issuer, audience = issued
  client id, expiry, nonce) before the account is activated.
- Inference: POST /v1/responses with stream=true and store=false, full
  history in `input`, `instructions` instead of system items, no sampling
  params. Only `response.completed` counts as success.
- Plan-usage errors stop inference; there is never a silent fallback to the
  user's API key.

Tokens live only on the node, encrypted in the provider CredentialStore.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import uuid
from urllib.parse import urlencode

import httpx

ISSUER = "https://auth.openai.com"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
API_BASE = "https://api.openai.com/v1"
RESOURCE = API_BASE
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
MANAGE_USAGE_URL = "https://chatgpt.com/settings/usage"
CALLBACK_PATH = "/auth/callback"
APP_NAME = "Shadow"
TXN_TTL_SECONDS = 600
REFRESH_MARGIN_SECONDS = 120

PROVIDER = "chatgpt_plan"
_HOST_KEY = "_chatgpt_host_id"

# Plan-usage error codes (errors-and-recovery) mapped to user-facing text.
PLAN_ERRORS = {
    "subscription_sharing_usage_limit_exceeded": "You've reached your ChatGPT plan usage limit for now.",
    "subscription_sharing_usage_unavailable": "ChatGPT plan usage is temporarily unavailable.",
    "subscription_sharing_user_not_eligible": "This ChatGPT account isn't eligible to use its plan in other apps (Plus or Pro is required).",
}


class ChatGPTPlanError(RuntimeError):
    """A sign-in or inference failure with a short, user-safe message."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _safe_return_to(origin: str | None, port: int) -> str:
    """Where the callback page links back to: the dashboard origin the user
    started from, but only a loopback origin (never an arbitrary site)."""
    from urllib.parse import urlparse
    try:
        u = urlparse(origin or "")
        if u.scheme in ("http", "https") and u.hostname in ("127.0.0.1", "localhost", "::1") and not u.path.strip("/"):
            return f"{u.scheme}://{u.netloc}"
    except ValueError:
        pass
    return f"http://127.0.0.1:{int(port)}"


def redirect_uri(port: int) -> str:
    # SIWC: loopback on 127.0.0.1 only; only the port may vary.
    return f"http://127.0.0.1:{int(port)}{CALLBACK_PATH}"


# --- ID token verification -----------------------------------------------------------

_jwks_cache: dict = {"at": 0.0, "keys": {}, "discovery": None}
_jwks_lock = threading.Lock()


def _discovery(http) -> dict:
    with _jwks_lock:
        if _jwks_cache["discovery"] and time.time() - _jwks_cache["at"] < 3600:
            return _jwks_cache["discovery"]
    r = http.get(DISCOVERY_URL, timeout=15)
    r.raise_for_status()
    doc = r.json()
    keys = {}
    jr = http.get(doc["jwks_uri"], timeout=15)
    jr.raise_for_status()
    for k in jr.json().get("keys", []):
        if k.get("kty") == "RSA" and k.get("kid"):
            keys[k["kid"]] = k
    with _jwks_lock:
        _jwks_cache.update(at=time.time(), keys=keys, discovery=doc)
    return doc


def verify_id_token(id_token: str, client_id: str, nonce: str, http) -> dict:
    """Verify an RS256 ID token against OpenAI's JWKS; return its claims."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    try:
        header_b64, payload_b64, sig_b64 = id_token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        claims = json.loads(_b64url_decode(payload_b64))
    except ValueError as e:
        raise ChatGPTPlanError("Sign-in returned a malformed ID token.") from e
    if header.get("alg") != "RS256":
        raise ChatGPTPlanError("Sign-in returned an unsupported ID token algorithm.")
    doc = _discovery(http)
    jwk = _jwks_cache["keys"].get(header.get("kid"))
    if jwk is None:
        _jwks_cache["at"] = 0.0  # key rotation: refetch once
        doc = _discovery(http)
        jwk = _jwks_cache["keys"].get(header.get("kid"))
    if jwk is None:
        raise ChatGPTPlanError("Couldn't verify the sign-in (unknown signing key).")
    pub = rsa.RSAPublicNumbers(
        int.from_bytes(_b64url_decode(jwk["e"]), "big"),
        int.from_bytes(_b64url_decode(jwk["n"]), "big"),
    ).public_key()
    try:
        pub.verify(_b64url_decode(sig_b64), f"{header_b64}.{payload_b64}".encode(),
                   padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as e:
        raise ChatGPTPlanError("Couldn't verify the sign-in (bad signature).") from e
    aud = claims.get("aud")
    audiences = aud if isinstance(aud, list) else [aud]
    if claims.get("iss") != doc.get("issuer", ISSUER):
        raise ChatGPTPlanError("Sign-in came from an unexpected issuer.")
    if client_id not in audiences:
        raise ChatGPTPlanError("Sign-in was issued for a different app.")
    if float(claims.get("exp", 0)) < time.time() - 60:
        raise ChatGPTPlanError("Sign-in expired; try again.")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ChatGPTPlanError("Sign-in nonce didn't match; try again.")
    return claims


# --- Sign-in, refresh, sign-out ----------------------------------------------------------


class ChatGPTPlanAuth:
    """Owns the SIWC flow and the stored token set for one node."""

    def __init__(self, credentials, http_client=None):
        self.credentials = credentials  # provider_auth.CredentialStore
        self.http = http_client or httpx
        self._txns: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()

    # host id: stable, opaque, per node install (not a secret)
    def host_id(self) -> str:
        meta = self.credentials.get(_HOST_KEY)
        if not meta:
            meta = {"value": f"urn:uuid:{uuid.uuid4()}"}
            self.credentials.set(_HOST_KEY, meta)
        return meta["value"]

    def start(self, port: int, device_id: str | None, return_to: str | None = None) -> dict:
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        existing = self.credentials.get(PROVIDER) or {}
        client_id = existing.get("client_id") or "dynamic_agent_client"
        params = {
            "client_id": client_id,
            "ext_agent_host_id": self.host_id(),
            "response_type": "code",
            "redirect_uri": redirect_uri(port),
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        }
        if client_id == "dynamic_agent_client":
            params["agent_name_hint"] = APP_NAME
        else:
            # Reauthorization of the same account on this host.
            if existing.get("id_token"):
                params["id_token_hint"] = existing["id_token"]
            if existing.get("email"):
                params["login_hint"] = existing["email"]
        with self._lock:
            self._sweep()
            self._txns[state] = {
                "verifier": verifier, "nonce": nonce, "redirect_uri": params["redirect_uri"],
                "client_id": client_id, "device_id": device_id, "created_at": time.time(),
                "return_to": _safe_return_to(return_to, port),
            }
        # The URL may carry id_token_hint: callers must not log it.
        return {"authorization_url": f"{AUTHORIZE_URL}?{urlencode(params)}", "state": state,
                "redirect_uri": params["redirect_uri"]}

    def _sweep(self) -> None:
        now = time.time()
        for s, t in list(self._txns.items()):
            if now - t["created_at"] > TXN_TTL_SECONDS:
                del self._txns[s]

    def complete(self, state: str, code: str, issued_client_id: str | None, granted_scope: str | None) -> dict:
        """Handle the loopback callback: exchange the code, verify, store."""
        with self._lock:
            self._sweep()
            txn = self._txns.pop(state, None)
        if txn is None:
            raise ChatGPTPlanError("This sign-in link expired or was already used. Start again from Shadow.")
        client_id = issued_client_id or txn["client_id"]
        if client_id == "dynamic_agent_client":
            raise ChatGPTPlanError("Sign-in didn't return an app registration. Start again.")
        r = self.http.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": txn["verifier"],
            "redirect_uri": txn["redirect_uri"],
            "resource": RESOURCE,
        }, timeout=30)
        if r.status_code >= 400:
            raise ChatGPTPlanError("ChatGPT sign-in failed while exchanging the code. Start again.")
        tok = r.json()
        claims = verify_id_token(tok.get("id_token", ""), client_id, txn["nonce"], self.http)
        scopes = (tok.get("scope") or granted_scope or "").split()
        record = {
            "type": "chatgpt_plan",
            "source": "chatgpt_signin",
            "issuer": ISSUER,
            "client_id": client_id,
            "ext_agent_host_id": self.host_id(),
            "subject": claims.get("sub"),
            "email": claims.get("email"),
            "id_token": tok.get("id_token"),
            "access_token": tok.get("access_token"),
            "refresh_token": tok.get("refresh_token"),
            "token_type": tok.get("token_type", "Bearer"),
            "expires_at": time.time() + float(tok.get("expires_in", 3600)),
            "scopes": scopes,
            "plan_usage": PLAN_SCOPE in scopes,
            "model": (self.credentials.get(PROVIDER) or {}).get("model"),
            "saved_at": time.time(),
        }
        self.credentials.set(PROVIDER, record)
        return {"email": record["email"], "plan_usage": record["plan_usage"], "return_to": txn["return_to"]}

    def access_token(self) -> str:
        """A valid access token, refreshing (serialized) near expiry."""
        cred = self.credentials.get(PROVIDER)
        if not cred or not cred.get("access_token"):
            raise ChatGPTPlanError("ChatGPT isn't connected. Continue with ChatGPT in Models.", "not_connected")
        if not cred.get("plan_usage"):
            raise ChatGPTPlanError("ChatGPT plan usage wasn't granted. Sign in again and allow plan usage, or use an API key.",
                                   "plan_usage_not_granted")
        if cred.get("expires_at", 0) - time.time() > REFRESH_MARGIN_SECONDS:
            return cred["access_token"]
        with self._refresh_lock:
            cred = self.credentials.get(PROVIDER) or {}
            if cred.get("expires_at", 0) - time.time() > REFRESH_MARGIN_SECONDS:
                return cred["access_token"]  # another thread refreshed it
            r = self.http.post(TOKEN_URL, data={
                "grant_type": "refresh_token",
                "client_id": cred["client_id"],
                "refresh_token": cred.get("refresh_token", ""),
                "resource": RESOURCE,
            }, timeout=30)
            if r.status_code >= 400:
                raise ChatGPTPlanError("Your ChatGPT sign-in expired. Continue with ChatGPT again.", "reauth_required")
            tok = r.json()
            # Replace the access token, expiry, scopes and rotating refresh
            # token together.
            cred.update(
                access_token=tok["access_token"],
                refresh_token=tok.get("refresh_token", cred.get("refresh_token")),
                expires_at=time.time() + float(tok.get("expires_in", 3600)),
            )
            if tok.get("scope"):
                cred["scopes"] = tok["scope"].split()
                cred["plan_usage"] = PLAN_SCOPE in cred["scopes"]
            if tok.get("id_token"):
                cred["id_token"] = tok["id_token"]
            self.credentials.set(PROVIDER, cred)
            return cred["access_token"]

    def sign_out(self) -> dict:
        cred = self.credentials.get(PROVIDER) or {}
        confirmed = False
        if cred.get("refresh_token"):
            try:
                doc = _discovery(self.http)
                r = self.http.post(doc["revocation_endpoint"], data={
                    "token": cred["refresh_token"], "token_type_hint": "refresh_token",
                    "client_id": cred.get("client_id", ""),
                }, timeout=15)
                confirmed = r.status_code == 200
            except Exception:
                confirmed = False
        # Keep client_id + email so the same account can sign in again on
        # this host (SIWC: reuse the registration), but drop every token.
        keep = {k: cred[k] for k in ("client_id", "email", "ext_agent_host_id") if k in cred}
        if keep:
            keep["type"] = "chatgpt_plan_signed_out"
            self.credentials.set(PROVIDER, keep)
        else:
            self.credentials.delete(PROVIDER)
        return {"revoked": confirmed}

    def models(self) -> list[dict]:
        r = self.http.get(f"{API_BASE}/models", headers={"Authorization": f"Bearer {self.access_token()}"}, timeout=20)
        if r.status_code >= 400:
            raise ChatGPTPlanError(f"Couldn't list ChatGPT plan models (HTTP {r.status_code}).")
        data = r.json()
        rows = data.get("models") or data.get("data") or []
        out = []
        for m in rows:
            if m.get("visibility", "list") != "list":
                continue
            slug = m.get("slug") or m.get("id")
            if slug:
                out.append({"slug": slug, "display_name": m.get("display_name") or slug})
        return out


# --- Inference --------------------------------------------------------------------------


class ChatGPTPlanProvider:
    """Responses API over the user's ChatGPT plan. Same complete() surface as
    the other frontier providers."""

    name = PROVIDER
    cloud = True

    def __init__(self, auth: ChatGPTPlanAuth, model: str, timeout: float = 120.0, http_client=None):
        self.auth = auth
        self.model = model
        self.timeout = timeout
        self.http = http_client or httpx

    def complete(self, prompt: str, context: str = "") -> str:
        from .persona import get_system_prompt

        if not self.model:
            raise ChatGPTPlanError("Pick a ChatGPT model in Models first.", "no_model")
        body = {
            "model": self.model,
            "instructions": get_system_prompt(),
            "input": [{
                "role": "user",
                "content": f"<untrusted_context>\n{context}\n</untrusted_context>\n\nUser request: {prompt}",
            }],
            "store": False,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.auth.access_token()}", "Content-Type": "application/json",
                   "Accept": "text/event-stream"}
        parts: list[str] = []
        with self.http.stream("POST", f"{API_BASE}/responses", json=body, headers=headers, timeout=self.timeout) as r:
            if r.status_code >= 400:
                r.read()
                raise _http_error(r)
            completed = False
            for event in _sse_events(r.iter_lines()):
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    parts.append(event.get("delta", ""))
                elif kind == "response.completed":
                    completed = True
                    break
                elif kind == "response.failed":
                    err = (event.get("response") or {}).get("error") or {}
                    code = err.get("code")
                    raise ChatGPTPlanError(PLAN_ERRORS.get(code, "The ChatGPT model couldn't answer."), code)
                elif kind == "response.incomplete":
                    reason = ((event.get("response") or {}).get("incomplete_details") or {}).get("reason")
                    text = "".join(parts).strip()
                    if text:
                        return f"{text}\n\n[response incomplete: {reason or 'stopped early'}]"
                    raise ChatGPTPlanError("The ChatGPT model stopped before answering.", "incomplete")
                elif kind == "error":
                    code = event.get("code") or (event.get("error") or {}).get("code")
                    raise ChatGPTPlanError(PLAN_ERRORS.get(code, "The ChatGPT model returned an error."), code)
            if not completed:
                raise ChatGPTPlanError("The connection to ChatGPT ended before the answer finished.", "interrupted")
        text = "".join(parts).strip()
        if not text:
            raise ChatGPTPlanError("The ChatGPT model returned an empty answer.", "empty")
        return text


def _http_error(r) -> ChatGPTPlanError:
    code = None
    try:
        payload = r.json()
        code = (payload.get("error") or {}).get("code")
    except Exception:
        pass
    if code in PLAN_ERRORS:
        return ChatGPTPlanError(PLAN_ERRORS[code], code)
    if r.status_code == 401:
        return ChatGPTPlanError("Your ChatGPT sign-in is no longer valid. Continue with ChatGPT again.", "reauth_required")
    return ChatGPTPlanError(f"ChatGPT returned HTTP {r.status_code}.", code)


def _sse_events(lines):
    """Parse server-sent events into JSON payloads (data: lines)."""
    data: list[str] = []
    for line in lines:
        if line == "":
            if data:
                raw = "\n".join(data)
                data = []
                if raw.strip() == "[DONE]":
                    return
                try:
                    yield json.loads(raw)
                except ValueError:
                    continue
            continue
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        try:
            yield json.loads("\n".join(data))
        except ValueError:
            pass
