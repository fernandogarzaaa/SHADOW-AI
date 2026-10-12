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


def test_dashboard_accessibility_basics():
    body = client.get("/").text
    # nav entries are real links (keyboard-focusable), not bare <a> tags
    for view in ["ask", "memory", "actions", "models", "approvals", "audit"]:
        assert f'<a href="#{view}" data-view="{view}"' in body
    # emergency pause is an operable switch, not a mouse-only div
    assert 'id="pauseSw" class="switch" role="switch" tabindex="0"' in body
    # small screens keep navigation + emergency pause instead of hiding the sidebar
    assert "aside{display:none}" not in body
    for field in ["askInput", "memTitle", "memText", "memQuery"]:
        assert f'id="{field}" aria-label=' in body or f'id="{field}" type="search" aria-label=' in body
