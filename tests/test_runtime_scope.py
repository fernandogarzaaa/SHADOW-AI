"""Backlog #7: runtime scope guard middleware.

OpenDots source: src/server/runtime-scope.ts (explicit (path, method)
allowlist + strict ID validation + path/body/query ID cross-check).
MIT (c) Atai Barkai.
"""
import pytest
from fastapi.testclient import TestClient

from shadow_node.main import app
from shadow_node.runtime_scope import (
    SCOPED_ROUTES,
    RuntimeScopeError,
    check_runtime_scope,
)


# --- pure unit tests ---------------------------------------------------------

def test_allowed_scoped_request_returns_params():
    params = check_runtime_scope("GET", "/artifacts/art_abc123")
    assert params == {"artifact_id": "art_abc123"}


def test_disallowed_method_denied():
    with pytest.raises(RuntimeScopeError):
        check_runtime_scope("GET", "/agent/execute")


def test_malformed_ids_denied():
    for bad in ["..\\x", ".hidden", "has space", "trail/", "semi;colon;ok"]:
        # "trail/" cannot match the template (extra segment) -> None, not an error;
        # the rest must raise.
        if "/" in bad:
            assert check_runtime_scope("GET", f"/artifacts/{bad}") is None
        else:
            with pytest.raises(RuntimeScopeError):
                check_runtime_scope("GET", f"/artifacts/{bad}")


def test_valid_id_shapes_pass():
    for good in ["art_abc123", "a", "UUID-1234.abcd_ef:12", "x" * 128]:
        assert check_runtime_scope("GET", f"/artifacts/{good}") == {"artifact_id": good}


def test_path_query_disagreement_denied():
    with pytest.raises(RuntimeScopeError):
        check_runtime_scope("GET", "/artifacts/art_123", {"artifact_id": "art_999"})


def test_path_query_agreement_ok():
    assert check_runtime_scope("GET", "/artifacts/art_123", {"artifact_id": "art_123"}) == {
        "artifact_id": "art_123"
    }


def test_unscoped_path_returns_none():
    assert check_runtime_scope("GET", "/health") is None
    assert check_runtime_scope("GET", "/no/such/route") is None


# --- allowlist <-> route table sync (both directions) -----------------------

def _app_routes():
    out = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        out.setdefault(path, set()).update(m.upper() for m in methods if m != "HEAD")
    return out


def test_allowlist_covers_all_scoped_app_routes():
    scoped_prefixes = {"/" + t.strip("/").split("/")[0] for t in SCOPED_ROUTES}
    app_routes = _app_routes()
    missing = []
    for path, methods in sorted(app_routes.items()):
        first = "/" + path.strip("/").split("/")[0] if path != "/" else "/"
        if first not in scoped_prefixes:
            continue
        listed = SCOPED_ROUTES.get(path)
        if listed is None:
            missing.append(f"{path} not listed")
        elif set(methods) != set(listed):
            missing.append(f"{path}: app={sorted(methods)} listed={sorted(listed)}")
    assert not missing, "SCOPED_ROUTES out of sync with app route table:\n" + "\n".join(missing)


def test_allowlist_has_no_phantom_entries():
    app_routes = _app_routes()
    phantom = [t for t in SCOPED_ROUTES if t not in app_routes]
    assert not phantom, f"phantom allowlist entries: {phantom}"


# --- middleware integration --------------------------------------------------

import shadow_node.main as _main


@pytest.fixture
def no_auth(monkeypatch):
    # auth_middleware runs outside (before) the scope guard; disable it so
    # these tests exercise the guard itself.
    monkeypatch.setattr(_main, "AUTH_REQUIRED", False)


client = TestClient(app)


def test_middleware_rejects_malformed_id_with_400(no_auth):
    r = client.get("/artifacts/.hidden")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "runtime_scope_denied"


def test_middleware_rejects_wrong_method_with_400(no_auth):
    r = client.get("/agent/execute")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "runtime_scope_denied"


def test_middleware_rejects_path_query_disagreement(no_auth):
    r = client.get("/artifacts/art_123", params={"artifact_id": "art_999"})
    assert r.status_code == 400


def test_middleware_passes_through_unscoped_routes():
    r = client.get("/health")
    assert r.status_code == 200


def test_middleware_passes_through_valid_scoped_request(no_auth):
    r = client.get("/artifacts/art_doesnotexist123")
    # well-formed ID passes the guard; the handler then 404s on the missing item
    assert r.status_code == 404
