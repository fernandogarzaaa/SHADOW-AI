from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest


ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH_ENTRIES = [
    ROOT / "apps" / "shadow-node",
    ROOT / "packages" / "agent-core",
    ROOT / "packages" / "memory-engine",
    ROOT / "packages" / "axiom-adapter",
    ROOT / "packages" / "ghost-adapter",
]


class Response:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self._body = body

    def json(self):
        return json.loads(self._body.decode() or "{}")


def request(method: str, url: str, headers: dict[str, str] | None = None, body: str | None = None) -> Response:
    data = body.encode() if body is not None else None
    req = urlrequest.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlrequest.urlopen(req, timeout=5) as res:
            return Response(res.status, res.read())
    except urlerror.HTTPError as exc:
        return Response(exc.code, exc.read())


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def sign_request(secret: str, method: str, path: str, body: str, nonce: str, timestamp: int) -> str:
    msg = "\n".join([method.upper(), path, body or "", nonce, str(timestamp)]).encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def signed_headers(creds: dict[str, str], method: str, path: str, body: str = "") -> dict[str, str]:
    nonce = uuid.uuid4().hex
    timestamp = int(time.time())
    signed_path = path.split("?", 1)[0]
    return {
        "x-shadow-device-id": creds["device_id"],
        "x-shadow-signature": sign_request(creds["secret"], method, signed_path, body, nonce, timestamp),
        "x-shadow-nonce": nonce,
        "x-shadow-timestamp": str(timestamp),
    }


def start_shadow_node(port: int, tmp_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    pythonpath = os.pathsep.join(str(p) for p in PYTHONPATH_ENTRIES)
    if env.get("PYTHONPATH"):
        pythonpath = pythonpath + os.pathsep + env["PYTHONPATH"]
    env.update(
        {
            "PYTHONPATH": pythonpath,
            "SHADOW_AUTH_REQUIRED": "true",
            "SHADOW_MEMORY_DB": str(tmp_path / "memory.db"),
        }
    )
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "shadow_node.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_health(proc: subprocess.Popen, base_url: str) -> None:
    deadline = time.time() + 15
    last_error: Exception | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=1)
            raise AssertionError(f"shadow node exited early\nstdout:\n{stdout}\nstderr:\n{stderr}")
        try:
            response = request("GET", f"{base_url}/health")
            if response.status_code == 200:
                return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(0.25)
    raise AssertionError(f"shadow node did not become healthy: {last_error}")


def authed_request(
    base_url: str,
    creds: dict[str, str],
    method: str,
    path: str,
    payload: dict | None = None,
) -> Response:
    body = json.dumps(payload, separators=(",", ":")) if payload is not None else ""
    headers = {"Content-Type": "application/json", **signed_headers(creds, method, path, body)}
    return request(method, f"{base_url}{path}", headers=headers, body=body if body else None)


def pair_device(base_url: str) -> dict[str, str]:
    start = request("POST", f"{base_url}/pair/start", headers={"Content-Type": "application/json"}, body="{}")
    assert start.status_code == 200
    public_key = f"pytest-{uuid.uuid4().hex}"
    confirm = request(
        "POST",
        f"{base_url}/pair/confirm",
        headers={"Content-Type": "application/json"},
        body=json.dumps(
            {
                "pairing_id": start.json()["pairing_id"],
                "device_name": "pytest new user",
                "public_key": public_key,
            },
            separators=(",", ":"),
        ),
    )
    assert confirm.status_code == 200
    paired = confirm.json()
    return {"device_id": paired["device"]["id"], "secret": paired["shared_secret"]}


def test_new_user_journey_against_uvicorn_subprocess(tmp_path):
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    proc = start_shadow_node(port, tmp_path)

    try:
        wait_for_health(proc, base_url)
        health = request("GET", f"{base_url}/health")
        assert health.json()["auth_required"] is True

        unsigned = request("GET", f"{base_url}/audit")
        assert unsigned.status_code == 401

        creds = pair_device(base_url)
        assert authed_request(base_url, creds, "GET", "/audit").status_code == 200

        ingest = authed_request(
            base_url,
            creds,
            "POST",
            "/memory/ingest",
            {
                "text": "Project Aurora ships in March; lead is Dana.",
                "source_title": "New-user E2E note",
            },
        )
        assert ingest.status_code == 200
        assert len(ingest.json()["items"]) > 0

        ask = authed_request(
            base_url,
            creds,
            "POST",
            "/agent/ask",
            {"prompt": "When does Aurora ship and who leads it?"},
        )
        assert ask.status_code == 200
        assert ask.json()["answer"]

        approval = authed_request(
            base_url,
            creds,
            "POST",
            "/approvals",
            {
                "action": {
                    "tool_name": "answer_question",
                    "description": "Confirm Aurora launch details",
                    "params": {},
                    "requires_approval": True,
                },
                "reason": "new-user e2e",
            },
        )
        assert approval.status_code == 200
        approval_id = approval.json()["id"]

        approved = authed_request(base_url, creds, "POST", f"/approvals/{approval_id}/approve")
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        audit = authed_request(base_url, creds, "GET", "/audit")
        assert audit.status_code == 200
        event_types = {event["event_type"] for event in audit.json()}
        assert {"device_paired", "memory_ingest", "agent_ask", "approval_approved"} <= event_types
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
