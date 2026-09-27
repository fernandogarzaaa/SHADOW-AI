"""Adversarial SSRF tests for GHOST http.get (audit P1).

The old implementation validated only the initial host once and then let
httpx follow redirects unchecked, so:
  - a 302 to http://169.254.169.254/ sailed through (redirect SSRF);
  - DNS was checked at guard time but re-resolved at connect time
    (DNS rebinding);
  - only the first resolved address was checked, not all of them;
  - any port was allowed;
  - proxies from the environment were honored.
"""

import socket

import pytest

from ghost_adapter import (
    LocalActionExecutor,
    _ssrf_fetch,
    _validate_http_hop,
    SSRF_MAX_BODY_BYTES,
)

# 93.184.216.34 is example.com: a public literal, so tests never need DNS.
PUBLIC_IP = "93.184.216.34"


class _FakeStream:
    def __init__(self, status=200, headers=None, body=b"", is_redirect=False):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self.is_redirect = is_redirect

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_bytes(self, size):
        for i in range(0, len(self._body), size):
            yield self._body[i:i + size]


class _FakeClient:
    """Records every requested URL; serves a scripted response sequence."""
    def __init__(self, script):
        self.script = list(script)
        self.requested = []

    def stream(self, method, url, **kwargs):
        assert kwargs.get("follow_redirects") is False, \
            "redirects must never be automatic"
        self.requested.append(url)
        status, headers, body = self.script.pop(0)
        return _FakeStream(status=status, headers=headers, body=body,
                           is_redirect=status in (301, 302, 303, 307, 308))


def _ok(body=b"hello"):
    return (200, {"content-type": "text/plain"}, body)


def _redirect_to(location):
    return (302, {"location": location}, b"")


# -- non-public addresses ------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/secret",
    "http://localhost:8787/admin",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://172.16.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://224.0.0.1/",
    "http://[::1]/",
    "http://[fd00::1]/",
    "http://0.0.0.0/",
])
def test_non_public_literal_addresses_blocked(url):
    with pytest.raises(ValueError, match="non-public|missing host|blocked port"):
        _validate_http_hop(url)


def test_localhost_blocked_via_executor():
    ex = LocalActionExecutor()
    for url in ["http://127.0.0.1/secret", "http://localhost:8787/admin"]:
        with pytest.raises(ValueError):
            ex.run("http.get", {"url": url})


# -- scheme / credentials / ports ----------------------------------------------

@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com/",
    "javascript:alert(1)",
])
def test_non_http_schemes_blocked(url):
    with pytest.raises(ValueError, match="only http/https"):
        _validate_http_hop(url)


def test_embedded_credentials_blocked():
    with pytest.raises(ValueError, match="credentials"):
        _validate_http_hop(f"http://user:pass@{PUBLIC_IP}/")


@pytest.mark.parametrize("url", [
    f"http://{PUBLIC_IP}:22/",
    f"http://{PUBLIC_IP}:25/",
    f"http://{PUBLIC_IP}:6379/",
    f"http://{PUBLIC_IP}:8080/",
    f"https://{PUBLIC_IP}:8443/",
])
def test_non_standard_ports_blocked(url):
    with pytest.raises(ValueError, match="only 80/443"):
        _validate_http_hop(url)


def test_standard_ports_allowed():
    # public literal IP: no DNS needed, validation passes
    assert _validate_http_hop(f"http://{PUBLIC_IP}/")
    assert _validate_http_hop(f"https://{PUBLIC_IP}/")
    assert _validate_http_hop(f"http://{PUBLIC_IP}:80/")
    assert _validate_http_hop(f"https://{PUBLIC_IP}:443/")


# -- redirect SSRF ---------------------------------------------------------------

def test_redirect_to_metadata_service_is_blocked():
    client = _FakeClient([_redirect_to("http://169.254.169.254/latest/meta-data/"),
                          _ok(b"never")])
    with pytest.raises(ValueError, match="non-public"):
        _ssrf_fetch(f"http://{PUBLIC_IP}/start", client=client)
    # the second hop was validated BEFORE any request was issued to it
    assert client.requested == [f"http://{PUBLIC_IP}/start"]


def test_redirect_chain_revalidates_every_hop():
    client = _FakeClient([_redirect_to(f"http://{PUBLIC_IP}/two"),
                          _redirect_to("http://127.0.0.1/three"),
                          _ok(b"never")])
    with pytest.raises(ValueError, match="non-public"):
        _ssrf_fetch(f"http://{PUBLIC_IP}/one", client=client)
    assert len(client.requested) == 2


def test_benign_redirect_is_followed():
    client = _FakeClient([_redirect_to(f"http://{PUBLIC_IP}/final"),
                          _ok(b"arrived")])
    body, status, ctype, final = _ssrf_fetch(f"http://{PUBLIC_IP}/start",
                                             client=client)
    assert body == "arrived" and status == 200
    assert final == f"http://{PUBLIC_IP}/final"


def test_relative_redirect_resolves_against_current_hop():
    client = _FakeClient([_redirect_to("/final"), _ok(b"rel")])
    body, _, _, final = _ssrf_fetch(f"http://{PUBLIC_IP}/start", client=client)
    assert body == "rel" and final == f"http://{PUBLIC_IP}/final"


def test_redirect_loop_is_bounded():
    client = _FakeClient([_redirect_to(f"http://{PUBLIC_IP}/a")] * 12)
    with pytest.raises(ValueError, match="too many redirects"):
        _ssrf_fetch(f"http://{PUBLIC_IP}/a", client=client)
    assert len(client.requested) <= 6  # SSRF_MAX_REDIRECTS + 1


def test_redirect_without_location_is_rejected():
    client = _FakeClient([(302, {}, b"")])
    with pytest.raises(ValueError, match="location"):
        _ssrf_fetch(f"http://{PUBLIC_IP}/", client=client)


# -- DNS rebinding -----------------------------------------------------------------

def test_each_hop_is_redns_resolved(monkeypatch):
    """A hostname that resolves public on the first hop and private on the
    second must be caught at the second hop: every hop re-resolves."""
    real_getaddrinfo = socket.getaddrinfo
    calls = {"n": 0}

    def flapping(host, *a, **k):
        calls["n"] += 1
        if host == "flap.example" and calls["n"] > 1:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        return real_getaddrinfo(PUBLIC_IP, *a, **k) if host == "flap.example" \
            else real_getaddrinfo(host, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", flapping)
    client = _FakeClient([_redirect_to("http://flap.example/two"), _ok(b"x")])
    with pytest.raises(ValueError, match="non-public"):
        _ssrf_fetch("http://flap.example/one", client=client)


def test_mixed_public_private_resolution_is_blocked(monkeypatch):
    def mixed(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.9.9.9", 0))]
    monkeypatch.setattr(socket, "getaddrinfo", mixed)
    with pytest.raises(ValueError, match="non-public"):
        _validate_http_hop("http://mixed.example/")


# -- same-hop DNS pinning (TOCTOU between validation and connect) ----------------
# PR #43 re-validated every hop, but httpx resolves the hostname AGAIN when
# it opens the socket. A malicious DNS server could answer the validation
# query with a public IP and the connect-time query with a private one.
# _pinned_dns() narrows connect-time resolution to the validated IPs.

class _ResolvingClient(_FakeClient):
    """Simulates what httpx does at connect time: resolve the hostname
    again inside stream(), and record which addresses were actually used."""

    def __init__(self, script):
        super().__init__(script)
        self.connect_ips = []

    def stream(self, method, url, **kwargs):
        from urllib.parse import urlparse
        host = urlparse(url).hostname
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        self.connect_ips.extend(info[4][0] for info in infos)
        return super().stream(method, url, **kwargs)


def _flap_dns(monkeypatch, connect_answer):
    """Validation-time answer is always PUBLIC_IP; connect-time answer is
    whatever the attacker wants."""
    real_getaddrinfo = socket.getaddrinfo
    state = {"calls": 0}

    def flapping(host, *a, **k):
        if host == "flap2.example":
            state["calls"] += 1
            addrs = [PUBLIC_IP] if state["calls"] == 1 else connect_answer
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in addrs]
        return real_getaddrinfo(host, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", flapping)


def test_connect_time_rebinding_cannot_reach_private_ip(monkeypatch):
    """Connect-time DNS flips to a private IP alongside the validated
    public one: pinning filters the private address out."""
    _flap_dns(monkeypatch, [PUBLIC_IP, "127.0.0.1"])
    client = _ResolvingClient([_ok(b"pinned")])
    body, _, _, _ = _ssrf_fetch("http://flap2.example/", client=client)
    assert body == "pinned"
    assert client.connect_ips == [PUBLIC_IP], \
        f"connect used unvalidated addresses: {client.connect_ips}"


def test_full_rebinding_flip_fails_closed(monkeypatch):
    """Connect-time DNS flips entirely to a private IP: no validated
    address remains, so resolution fails closed and no request goes out."""
    _flap_dns(monkeypatch, ["127.0.0.1"])
    client = _ResolvingClient([_ok(b"never")])
    with pytest.raises(socket.gaierror, match="no longer resolves to a validated address"):
        _ssrf_fetch("http://flap2.example/", client=client)
    assert client.requested == []


def test_pinning_does_not_affect_other_hosts(monkeypatch):
    """While a pinned request is in flight, unrelated hostnames resolve
    normally through the real resolver."""
    _flap_dns(monkeypatch, [PUBLIC_IP])
    from ghost_adapter import _pinned_dns
    with _pinned_dns("flap2.example", [PUBLIC_IP]):
        infos = socket.getaddrinfo(PUBLIC_IP, None, type=socket.SOCK_STREAM)
        assert infos and infos[0][4][0] == PUBLIC_IP


# -- proxy / body limits -------------------------------------------------------------

def test_proxies_are_disabled(monkeypatch):
    seen = {}

    class RecordingClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def close(self):
            pass

    import httpx
    monkeypatch.setattr(httpx, "Client", RecordingClient)
    with pytest.raises(AttributeError):
        # no injected client: must construct its own with trust_env=False
        _ssrf_fetch(f"http://{PUBLIC_IP}/", client=None)
    assert seen.get("trust_env") is False


def test_response_body_is_capped():
    big = b"x" * (SSRF_MAX_BODY_BYTES + 100000)
    client = _FakeClient([_ok(big)])
    body, _, _, _ = _ssrf_fetch(f"http://{PUBLIC_IP}/big", client=client)
    assert len(body.encode("utf-8")) <= SSRF_MAX_BODY_BYTES
