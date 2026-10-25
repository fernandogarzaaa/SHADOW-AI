"""Web dashboard served by the node: structure, CSP, static assets, a11y basics,
and the JS signer's agreement with the Python signature-v2 vectors."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import shadow_node.main as m

client = TestClient(m.app)
ROOT = Path(__file__).resolve().parents[1]
VIEWS = ["overview", "ask", "approvals", "actions", "memory", "goals", "schedule",
         "feed", "panels", "devices", "models", "audit"]


def test_dashboard_served_at_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert 'id="app"' in body and 'id="connect"' in body
    for view in VIEWS:
        assert f'id="view-{view}"' in body
        assert f'href="#/{view}" data-view="{view}"' in body


def test_dashboard_csp_and_framing_headers():
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-eval" not in csp
    assert r.headers["x-frame-options"] == "DENY"


def test_no_inline_script_or_handlers():
    body = client.get("/").text
    assert not re.search(r"\son[a-z]+\s*=", body), "inline event handler found"
    for tag in re.findall(r"<script\b[^>]*>(.*?)</script>", body, re.S):
        assert tag.strip() == "", "inline script found"
    js = (ROOT / "apps/shadow-node/shadow_node/web/app.js").read_text()
    assert ".innerHTML" in js and "onclick=" not in js


@pytest.mark.parametrize("asset,ctype", [
    ("app.js", "javascript"), ("signer.js", "javascript"),
    ("styles.css", "text/css"), ("favicon.svg", "image/svg+xml"),
])
def test_static_assets_served_without_auth(asset, ctype, monkeypatch):
    monkeypatch.setattr(m, "AUTH_REQUIRED", True)
    r = TestClient(m.app).get(f"/web/{asset}")
    assert r.status_code == 200 and ctype in r.headers["content-type"]


def test_static_assets_allowlisted():
    assert client.get("/web/index.html").status_code == 404
    assert client.get("/web/..%2Fmain.py").status_code == 404


def test_dashboard_exempt_from_auth_when_enabled(monkeypatch):
    monkeypatch.setattr(m, "AUTH_REQUIRED", True)
    c = TestClient(m.app)
    assert c.get("/").status_code == 200          # UI loads
    assert c.get("/health").status_code == 200     # health loads
    assert c.get("/audit").status_code == 401      # protected route still gated


def test_dashboard_accessibility_basics():
    body = client.get("/").text
    assert 'class="skip" href="#main"' in body
    # emergency pause is a real button with switch semantics
    assert '<button type="button" id="pauseSw" class="switch" role="switch"' in body
    # every form control has a label
    for field in ["askInput", "memTitle", "memText", "memQuery", "goalTitle", "schedText",
                  "panelText", "pairName", "pairBootstrap", "auditFilter"]:
        assert f'for="{field}"' in body, field
    css = (ROOT / "apps/shadow-node/shadow_node/web/styles.css").read_text()
    assert "prefers-reduced-motion" in css and "prefers-color-scheme" in css


def test_pending_pairings_owner_only(monkeypatch):
    import uuid
    import time
    from agent_core import sign_request_v2
    monkeypatch.setattr(m, "AUTH_REQUIRED", True)
    owner = m.sessions.register("O", f"pk-{uuid.uuid4().hex}", "os", is_owner=True)
    phone = m.sessions.register("P", f"pk-{uuid.uuid4().hex}", "ps")
    c = TestClient(m.app)

    def h(dev, secret):
        ts, n = int(time.time()), uuid.uuid4().hex
        return {"x-shadow-device-id": dev.id, "x-shadow-nonce": n, "x-shadow-timestamp": str(ts),
                "x-shadow-signature-version": "2",
                "x-shadow-signature": sign_request_v2(secret, "GET", "/pair/pending", "", b"", n, ts, dev.id)}
    try:
        pid = c.post("/pair/start", json={"device_name": "Laptop", "public_key": "x", "client_kind": "web"}).json()["pairing_id"]
        r = c.get("/pair/pending", headers=h(owner, "os"))
        assert r.status_code == 200
        assert any(i["pairing_id"] == pid and i["client_kind"] == "web" for i in r.json()["items"])
        assert c.get("/pair/pending", headers=h(phone, "ps")).status_code == 403
    finally:
        m.sessions.devices.pop(owner.id, None)
        m.sessions.devices.pop(phone.id, None)
        m.pairing.pop(pid, None)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_signer_matches_python_vectors():
    out = subprocess.run(["node", str(ROOT / "tests/js/sig_v2_vectors.test.mjs")],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "vectors OK" in out.stdout
