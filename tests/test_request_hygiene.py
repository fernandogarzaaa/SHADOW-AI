"""Backlog #10: middleware hygiene.

OpenDots source: src/server/app.ts lines 32-76 (bodyLimit 413,
sec-fetch-site 403, content-type 415, timingSafeEqual, no-store/nosniff).
MIT (c) Atai Barkai. The timing-safe compare already existed
(security.py:201 hmac.compare_digest); the rest is ported here.
"""
import pytest
from fastapi.testclient import TestClient

import shadow_node.main as _main
from shadow_node.main import app
from shadow_node.request_hygiene import (
    MAX_BODY_BYTES,
    HygieneError,
    check_body_limit,
    check_content_type,
    check_fetch_site,
    check_request_hygiene,
)


@pytest.fixture
def no_auth(monkeypatch):
    monkeypatch.setattr(_main, "AUTH_REQUIRED", False)


client = TestClient(app)


# --- pure unit tests ---------------------------------------------------------

def test_body_limit_rejects_oversize():
    with pytest.raises(HygieneError) as e:
        check_body_limit(str(MAX_BODY_BYTES + 1))
    assert e.value.status_code == 413


def test_body_limit_accepts_at_limit():
    check_body_limit(str(MAX_BODY_BYTES))
    check_body_limit(None)
    check_body_limit("0")


def test_body_limit_rejects_garbage():
    with pytest.raises(HygieneError) as e:
        check_body_limit("not-a-number")
    assert e.value.status_code == 400


def test_content_type_requires_json_with_body():
    h = {"content-length": "10", "content-type": "text/plain"}
    with pytest.raises(HygieneError) as e:
        check_content_type("POST", "/agent/ask", h)
    assert e.value.status_code == 415


def test_content_type_allows_json():
    check_content_type("POST", "/agent/ask", {"content-length": "10", "content-type": "application/json"})


def test_content_type_skipped_without_body_and_for_bodiless_methods():
    check_content_type("POST", "/agent/ask", {})
    check_content_type("GET", "/agent/ask", {"content-type": "text/plain"})
    check_content_type("OPTIONS", "/agent/ask", {"content-length": "5"})


def test_content_type_multipart_exempt_path():
    check_content_type(
        "POST", "/voice/transcribe",
        {"content-length": "10", "content-type": "multipart/form-data; boundary=x"},
    )


def test_fetch_site_cross_site_blocked():
    with pytest.raises(HygieneError) as e:
        check_fetch_site("cross-site", "https://evil.example", [])
    assert e.value.status_code == 403


def test_fetch_site_allows_trusted_origin_and_nonnative():
    check_fetch_site("cross-site", "http://localhost:19006", ["http://localhost:19006"])
    check_fetch_site("same-origin", None, [])
    check_fetch_site(None, None, [])


# --- middleware integration --------------------------------------------------

def test_middleware_413_on_oversize_body(no_auth):
    r = client.post(
        "/agent/ask", content=b"x",
        headers={"content-length": str(MAX_BODY_BYTES + 1), "content-type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "body_too_large"


def test_middleware_415_on_wrong_content_type(no_auth):
    r = client.post("/agent/ask", content=b"hello", headers={"content-type": "text/plain"})
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_media_type"


def test_middleware_403_on_cross_site(no_auth):
    r = client.post(
        "/agent/ask", json={"q": "hi"},
        headers={"sec-fetch-site": "cross-site", "origin": "https://evil.example"},
    )
    assert r.status_code == 403


def test_middleware_allows_trusted_cross_site_origin(no_auth, monkeypatch):
    monkeypatch.setattr(_main, "CORS_ORIGINS", ["https://app.example"])
    r = client.post(
        "/agent/ask", json={"q": "hi"},
        headers={"sec-fetch-site": "cross-site", "origin": "https://app.example"},
    )
    # passes hygiene; the handler may 4xx/5xx for the dummy payload, but not 403-cross-site
    assert r.status_code != 403 or r.json().get("error", {}).get("code") != "cross_site_blocked"


def test_middleware_sets_security_headers(no_auth):
    r = client.get("/health")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_middleware_valid_json_request_passes(no_auth):
    r = client.post("/pair/start", json={})
    assert r.status_code in (200, 400, 422)  # hygiene passed; handler decides
