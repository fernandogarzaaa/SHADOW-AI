"""Smoke test for the minimalist web dashboard served by the node."""
from fastapi.testclient import TestClient
import shadow_node.main as m

client = TestClient(m.app)


def test_dashboard_served_at_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert '<div class="app">' in body
    for view in ["view-ask", "view-memory", "view-actions", "view-approvals", "view-audit"]:
        assert view in body


def test_dashboard_exempt_from_auth_when_enabled():
    m.AUTH_REQUIRED = True
    try:
        c = TestClient(m.app)
        assert c.get("/").status_code == 200          # UI loads
        assert c.get("/health").status_code == 200     # health loads
        assert c.get("/audit").status_code == 401      # protected route still gated
    finally:
        m.AUTH_REQUIRED = False
