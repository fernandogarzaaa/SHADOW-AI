"""Request hygiene: body limit, content-type enforcement, fetch-metadata
rejection, and security response headers.

Adapted from OpenDots' API middleware (``src/server/app.ts``, MIT (c) Atai
Barkai), which applies ``bodyLimit`` (413), rejects ``sec-fetch-site:
cross-site`` (403), requires ``application/json`` on non-GET/HEAD (415),
compares the owner token with ``timingSafeEqual``, and sets
``Cache-Control: no-store`` / ``X-Content-Type-Options: nosniff``.

Adaptations for the Shadow Node:
- The timing-safe compare already exists (``security.py`` uses
  ``hmac.compare_digest``); it is not duplicated here.
- The body limit defaults to 25 MB (``SHADOW_MAX_BODY_BYTES``), not
  OpenDots' 1 MB: the node accepts voice audio and media uploads.
- ``/voice/transcribe`` is exempt from the JSON-only rule: it accepts
  multipart audio uploads as well as JSON.
- ``sec-fetch-site: cross-site`` is rejected unless the ``Origin`` is in
  the explicit CORS allowlist (the deployed-PWA scenario), instead of
  OpenDots' unconditional rejection.
"""
from __future__ import annotations

import os

#: Default cap for request bodies. Voice recordings and media uploads need
#: headroom well beyond a JSON API's 1 MB; operators can lower it.
MAX_BODY_BYTES = int(os.getenv("SHADOW_MAX_BODY_BYTES", "25000000"))

#: Routes that legitimately accept non-JSON bodies (multipart uploads).
MULTIPART_PATHS = frozenset({"/voice/transcribe"})

#: Methods that never carry a meaningful body for content-type purposes.
BODYLESS_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class HygieneError(ValueError):
    """A request failed a hygiene check. Carries its HTTP status code."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def check_body_limit(content_length: str | None) -> None:
    """Reject oversized request bodies (413) and garbage lengths (400)."""
    if content_length is None or content_length == "":
        return
    try:
        length = int(content_length)
    except ValueError:
        raise HygieneError(400, "bad_content_length", "Unparseable Content-Length.")
    if length < 0:
        raise HygieneError(400, "bad_content_length", "Negative Content-Length.")
    if length > MAX_BODY_BYTES:
        raise HygieneError(
            413,
            "body_too_large",
            f"Request body exceeds the {MAX_BODY_BYTES}-byte limit.",
        )


def _has_body(headers) -> bool:
    try:
        if int(headers.get("content-length", "0")) > 0:
            return True
    except ValueError:
        return True  # malformed length: body-limit check reports it
    return "chunked" in headers.get("transfer-encoding", "").lower()


def check_content_type(method: str, path: str, headers) -> None:
    """Non-GET/HEAD/OPTIONS requests with a body must be application/json
    (415), except the multipart upload routes."""
    if method.upper() in BODYLESS_METHODS:
        return
    if path in MULTIPART_PATHS:
        return
    if not _has_body(headers):
        return
    ctype = headers.get("content-type", "")
    if "application/json" not in ctype.lower():
        raise HygieneError(
            415, "unsupported_media_type", "Use application/json for request bodies."
        )


def check_fetch_site(fetch_site: str | None, origin: str | None, cors_origins) -> None:
    """Reject cross-site requests (403) unless the origin is explicitly
    trusted via the CORS allowlist. Native clients send no fetch metadata
    and are unaffected."""
    if fetch_site != "cross-site":
        return
    if origin and origin in cors_origins:
        return
    raise HygieneError(403, "cross_site_blocked", "Cross-site requests are not allowed.")


def check_request_hygiene(method: str, path: str, headers, cors_origins) -> None:
    """Run all hygiene checks. Raises HygieneError on the first failure."""
    check_body_limit(headers.get("content-length"))
    check_content_type(method, path, headers)
    check_fetch_site(headers.get("sec-fetch-site"), headers.get("origin"), cors_origins)


class BodyLimitMiddleware:
    """Pure-ASGI streaming body cap.

    check_body_limit only sees Content-Length; a chunked request has none,
    so its size is unknown until read. This reads the body up front,
    counting bytes, and answers 413 as soon as MAX_BODY_BYTES is exceeded;
    otherwise it replays the (bounded) buffered body to the app. No handler,
    and not the auth middleware that reads the body to verify signatures,
    can be made to buffer an unbounded upload.
    """

    def __init__(self, app, max_bytes: int | None = None):
        self.app = app
        self.max_bytes = max_bytes if max_bytes is not None else MAX_BODY_BYTES

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"].upper() in BODYLESS_METHODS:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        if b"content-length" in headers:
            # Declared length: check_body_limit already rejects oversize
            # bodies from the header, and auth rejects unknown devices
            # before reading the body, so don't buffer here.
            return await self.app(scope, receive, send)
        chunks, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > self.max_bytes:
                payload = (
                    '{"error":{"code":"body_too_large","message":"Request body exceeds the '
                    f'{self.max_bytes}-byte limit."}}}}'
                ).encode()
                await send({"type": "http.response.start", "status": 413,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(payload)).encode()),
                                        (b"connection", b"close")]})
                await send({"type": "http.response.body", "body": payload})
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        buffered = b"".join(chunks)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": buffered, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
