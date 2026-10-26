"""Request signature v2, bootstrap-code enrollment, and device renewal.

v2 binds the query string, a digest of the raw body, and the device id.
v1 keeps working for clients that have never sent v2; once a device has
used v2 it cannot be downgraded. The first owner device on a fresh node
needs the single-use bootstrap code printed to the node's terminal, and
devices in regular use slide forward instead of locking out at 30 days.
"""
import hashlib
import json
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_core import canonical_query, now, sign_request, sign_request_v2

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "sig_v2_vectors.json").read_text())


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_shared_vectors(case):
    assert canonical_query(case["query"]) == case["canonical_query"]
    sig = sign_request_v2(VECTORS["secret"], case["method"], case["path"], case["query"],
                          case["body"], VECTORS["nonce"], VECTORS["timestamp"], VECTORS["device_id"])
    assert sig == case["signature"]


@pytest.fixture
def api(monkeypatch):
    import shadow_node.main as m
    from shadow_node.bootstrap import BootstrapCode
    monkeypatch.setattr(m, "AUTH_REQUIRED", True)
    monkeypatch.setattr(m, "bootstrap", BootstrapCode())
    dev_snap, sec_snap, pair_snap = dict(m.sessions.devices), dict(m.sessions.secrets), dict(m.pairing)
    m.sessions.devices.clear(); m.sessions.secrets.clear(); m.pairing.clear()
    yield TestClient(m.app), m
    m.sessions.devices.clear(); m.sessions.devices.update(dev_snap)
    m.sessions.secrets.clear(); m.sessions.secrets.update(sec_snap)
    m.pairing.clear(); m.pairing.update(pair_snap)


def _v1(dev_id, secret, method, path, body=""):
    ts, nonce = int(time.time()), uuid.uuid4().hex
    return {"x-shadow-device-id": dev_id, "x-shadow-nonce": nonce, "x-shadow-timestamp": str(ts),
            "x-shadow-signature": sign_request(secret, method, path, body, nonce, ts)}


def _v2(dev_id, secret, method, path, query="", body=""):
    ts, nonce = int(time.time()), uuid.uuid4().hex
    return {"x-shadow-device-id": dev_id, "x-shadow-nonce": nonce, "x-shadow-timestamp": str(ts),
            "x-shadow-signature-version": "2",
            "x-shadow-signature": sign_request_v2(secret, method, path, query, body, nonce, ts, dev_id)}


def _owner(m, secret="owner-secret"):
    return m.sessions.register("Owner", f"pub-{uuid.uuid4().hex}", secret, is_owner=True)


# --- signature v2 -----------------------------------------------------------

def test_v1_still_verifies(api):
    client, m = api
    dev = _owner(m)
    assert client.get("/devices", headers=_v1(dev.id, "owner-secret", "GET", "/devices")).status_code == 200


def test_v2_get_with_query(api):
    client, m = api
    dev = _owner(m)
    h = _v2(dev.id, "owner-secret", "GET", "/approvals", "status=pending")
    assert client.get("/approvals?status=pending", headers=h).status_code == 200


def test_v2_query_tamper_rejected(api):
    client, m = api
    dev = _owner(m)
    h = _v2(dev.id, "owner-secret", "GET", "/approvals", "status=pending")
    r = client.get("/approvals?status=approved", headers=h)
    assert r.status_code == 401 and r.json()["detail"] == "invalid_signature"


def test_v2_body_tamper_rejected(api):
    client, m = api
    dev = _owner(m)
    body = json.dumps({"text": "a"})
    h = {**_v2(dev.id, "owner-secret", "POST", "/memory/ingest", body=body), "content-type": "application/json"}
    r = client.post("/memory/ingest", content=json.dumps({"text": "b"}), headers=h)
    assert r.status_code == 401


def test_v2_signature_bound_to_device(api):
    client, m = api
    a = _owner(m, "shared")
    b = m.sessions.register("B", "pub-b", "shared")
    h = _v2(a.id, "shared", "GET", "/devices")
    h["x-shadow-device-id"] = b.id
    assert client.get("/devices", headers=h).status_code == 401


def test_downgrade_after_v2_rejected(api):
    client, m = api
    dev = _owner(m)
    assert client.get("/devices", headers=_v2(dev.id, "owner-secret", "GET", "/devices")).status_code == 200
    assert m.sessions.devices[dev.id].min_sig_version == 2
    r = client.get("/devices", headers=_v1(dev.id, "owner-secret", "GET", "/devices"))
    assert r.status_code == 401 and r.json()["detail"] == "sig_downgrade"


def test_v1_query_gets_deprecation_header(api):
    client, m = api
    dev = _owner(m)
    r = client.get("/approvals?status=pending", headers=_v1(dev.id, "owner-secret", "GET", "/approvals"))
    assert r.status_code == 200 and r.headers.get("deprecation") == "true"


def test_unsupported_version_rejected(api):
    client, m = api
    dev = _owner(m)
    h = {**_v2(dev.id, "owner-secret", "GET", "/devices"), "x-shadow-signature-version": "9"}
    assert client.get("/devices", headers=h).json()["detail"] == "unsupported_signature_version"


def test_session_expires_header(api):
    client, m = api
    dev = _owner(m)
    r = client.get("/devices", headers=_v2(dev.id, "owner-secret", "GET", "/devices"))
    assert r.headers["x-shadow-session-expires"].startswith(str(dev.session_expires_at.year))


# --- bootstrap code ---------------------------------------------------------

def _start(client, kind=None):
    body = {"device_name": "First", "public_key": f"pk-{uuid.uuid4().hex}"}
    if kind:
        body["client_kind"] = kind
    return client.post("/pair/start", json=body).json()


def test_fresh_node_requires_bootstrap_code(api):
    client, m = api
    assert client.get("/health").json()["bootstrap_open"] is True
    p = _start(client)
    assert p["bootstrap_required"] is True
    r = client.post("/pair/confirm", json={"pairing_id": p["pairing_id"]})
    assert r.status_code == 202 and m.sessions.devices == {}


def test_bootstrap_code_mints_owner_once(api, capsys):
    client, m = api
    code = m.bootstrap.ensure() or pytest.fail("code should be issued")
    p = _start(client, kind="web")
    r = client.post("/pair/confirm", json={"pairing_id": p["pairing_id"], "bootstrap_code": code})
    assert r.status_code == 200
    body = r.json()
    assert body["device"]["is_owner"] is True
    assert body["secret"] == body["shared_secret"]
    assert body["device"]["min_sig_version"] == 2  # web clients start on v2
    assert client.get("/health").json()["bootstrap_open"] is False
    # single use: a second device cannot reuse the code
    p2 = _start(client)
    r2 = client.post("/pair/confirm", json={"pairing_id": p2["pairing_id"], "bootstrap_code": code})
    assert r2.status_code == 403
    assert len(m.sessions.devices) == 1


def test_wrong_code_rotates_after_max_failures(api):
    client, m = api
    from shadow_node.bootstrap import MAX_FAILURES
    first = m.bootstrap.ensure()
    p = _start(client)
    for _ in range(MAX_FAILURES):
        r = client.post("/pair/confirm", json={"pairing_id": p["pairing_id"], "bootstrap_code": "0000-0000"})
        assert r.status_code == 403
    # the original code no longer works: it rotated
    r = client.post("/pair/confirm", json={"pairing_id": p["pairing_id"], "bootstrap_code": first})
    assert r.status_code == 403 and m.sessions.devices == {}


def test_expired_owners_reopen_bootstrap(api):
    client, m = api
    owner = _owner(m)
    owner.session_expires_at = now() - timedelta(days=1)
    assert client.get("/health").json()["bootstrap_open"] is True
    code = m.bootstrap.ensure()
    p = _start(client)
    r = client.post("/pair/confirm", json={"pairing_id": p["pairing_id"], "bootstrap_code": code})
    assert r.status_code == 200 and r.json()["device"]["is_owner"] is True


def test_concurrent_confirms_mint_one_device(api):
    client, m = api
    code = m.bootstrap.ensure()
    p = _start(client)
    results = []

    def go():
        results.append(client.post("/pair/confirm",
                                   json={"pairing_id": p["pairing_id"], "bootstrap_code": code}).status_code)

    threads = [threading.Thread(target=go) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(200) == 1
    assert len(m.sessions.devices) == 1


# --- renewal ----------------------------------------------------------------

def test_sliding_renewal_near_expiry(api):
    client, m = api
    dev = _owner(m)
    dev.session_expires_at = now() + timedelta(days=2)
    assert client.get("/devices", headers=_v2(dev.id, "owner-secret", "GET", "/devices")).status_code == 200
    assert dev.session_expires_at - now() > timedelta(days=29)


def test_self_renew_and_owner_required_for_others(api):
    client, m = api
    owner = _owner(m)
    other = m.sessions.register("Phone", "pub-phone", "phone-secret")
    path = f"/devices/{other.id}/renew"
    assert client.post(path, headers=_v2(other.id, "phone-secret", "POST", path)).status_code == 200
    path_owner = f"/devices/{owner.id}/renew"
    assert client.post(path_owner, headers=_v2(other.id, "phone-secret", "POST", path_owner)).status_code == 403
    assert client.post(path_owner, headers=_v2(owner.id, "owner-secret", "POST", path_owner)).status_code == 200


def test_owner_revives_expired_device(api):
    client, m = api
    owner = _owner(m)
    other = m.sessions.register("Phone", "pub-phone", "phone-secret")
    other.session_expires_at = now() - timedelta(days=3)
    path = f"/devices/{other.id}"
    assert client.get("/devices", headers=_v2(other.id, "phone-secret", "GET", "/devices")).json()["detail"] == "session_expired"
    assert client.post(path + "/renew", headers=_v2(owner.id, "owner-secret", "POST", path + "/renew")).status_code == 200
    assert client.get("/devices", headers=_v2(other.id, "phone-secret", "GET", "/devices")).status_code == 200


def test_renewal_and_sig_version_persist(tmp_path):
    from shadow_node.runtime_store import build_runtime, EncryptedRuntimeStore
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    import shadow_node.runtime_store as rs
    db = str(tmp_path / "rt.db")
    store = EncryptedRuntimeStore(db, key=key)
    sessions = rs.PersistentDeviceSessionStore(store)
    dev = sessions.register("P", "pk", "s")
    dev.session_expires_at = now() + timedelta(days=1)
    sessions._persist_device(dev)
    ts, nonce = int(time.time()), "n1"
    sig = sign_request_v2("s", "GET", "/x", "", b"", nonce, ts, dev.id)
    ok, _ = sessions.verify(dev.id, sig, nonce, str(ts), "GET", "/x",
                            hashlib.sha256(b"").hexdigest(), version=2)
    assert ok
    reloaded = rs.PersistentDeviceSessionStore(EncryptedRuntimeStore(db, key=key)).devices[dev.id]
    assert reloaded.min_sig_version == 2
    assert reloaded.session_expires_at - now() > timedelta(days=29)


def test_threaded_nonce_claims_are_safe(tmp_path):
    from shadow_node.runtime_store import EncryptedRuntimeStore, PersistentNonceLedger
    from cryptography.fernet import Fernet
    ledger = PersistentNonceLedger(EncryptedRuntimeStore(str(tmp_path / "n.db"), key=Fernet.generate_key()))
    wins, errors = [], []

    def go(i):
        try:
            # 4 threads race every nonce
            wins.append(ledger.claim("dev", f"n{i // 4}", time.time()))
        except Exception as e:  # pragma: no cover - the bug this guards
            errors.append(e)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(80)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert wins.count(True) == 20


def test_claim_prunes_stale_nonces(tmp_path):
    from shadow_node.runtime_store import EncryptedRuntimeStore, PersistentNonceLedger, _NonceRow
    from cryptography.fernet import Fernet
    store = EncryptedRuntimeStore(str(tmp_path / "n.db"), key=Fernet.generate_key())
    ledger = PersistentNonceLedger(store)
    old = time.time() - 3600
    ledger.claim("dev", "old", old)
    ledger._last_prune = 0
    ledger.claim("dev", "new", time.time())
    ledger._prune_thread.join(timeout=5)  # pruning runs off the request path
    ids = [r.id for r in store.all("nonces", _NonceRow)]
    assert ids == ["dev:new"]


# --- Goldfish review round 1: code fixes -----------------------------------

def test_v2_signs_path_as_sent(api):
    """Browsers and fetch clients sign the encoded path (URL.pathname). The
    node must verify the same bytes: toggling `ambient:feed_digest` from the
    dashboard used to fail with invalid_signature."""
    client, m = api
    dev = _owner(m)
    raw = "/scheduled-tasks/ambient%3Afeed_digest"
    r = client.get(raw, headers=_v2(dev.id, "owner-secret", "GET", raw))
    assert r.status_code == 200, r.text
    # signing the decoded form no longer matches the request as sent
    r = client.get(raw, headers=_v2(dev.id, "owner-secret", "GET", "/scheduled-tasks/ambient:feed_digest"))
    assert r.status_code == 401


def test_v1_still_signs_decoded_path(api):
    client, m = api
    dev = _owner(m)
    raw = "/scheduled-tasks/ambient%3Afeed_digest"
    r = client.get(raw, headers=_v1(dev.id, "owner-secret", "GET", "/scheduled-tasks/ambient:feed_digest"))
    assert r.status_code == 200


def test_nonce_remembered_for_full_skew_window():
    """A timestamp is valid for +/-300 s, so a nonce must be remembered for
    600 s; otherwise a future-stamped request replays after 300 s."""
    from agent_core.security import InMemoryNonceLedger, NONCE_RETENTION_SECONDS, MAX_SKEW_SECONDS
    assert NONCE_RETENTION_SECONDS == 2 * MAX_SKEW_SECONDS
    ledger = InMemoryNonceLedger()
    assert ledger.claim("dev", "n", 1000.0)
    assert ledger.claim("dev", "n", 1450.0) is False   # replay inside the window
    assert ledger.claim("dev", "n", 1000.0 + 601)       # forgotten only after 600 s


def test_persistent_nonce_remembered_for_full_skew_window(tmp_path):
    from cryptography.fernet import Fernet
    from shadow_node.runtime_store import EncryptedRuntimeStore, PersistentNonceLedger
    ledger = PersistentNonceLedger(EncryptedRuntimeStore(str(tmp_path / "n.db"), key=Fernet.generate_key()))
    assert ledger.claim("dev", "n", 1000.0)
    assert ledger.claim("dev", "n", 1450.0) is False


def test_failed_auth_is_rate_limited(api, monkeypatch):
    client, m = api
    from shadow_node.obs import RateLimiter
    monkeypatch.setattr(m, "rate_limiter", RateLimiter(rpm=3))
    dev = _owner(m)
    codes = []
    for _ in range(5):
        h = _v2(dev.id, "wrong-secret", "GET", "/devices")
        codes.append(client.get("/devices", headers=h).status_code)
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]
