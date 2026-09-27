"""Artifacts, voice, media (final parity phase): CRUD, versions, caps, provider routing."""
import base64
import hashlib
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

from agent_core import sign_request
from agent_core.models import Device

from shadow_node.main import app
import shadow_node.main as main
from shadow_node.artifacts import ArtifactStore, ArtifactCreate, ArtifactUpdate
from shadow_node import voice as voice_mod
from shadow_node import media as media_mod
from shadow_node.runtime_store import EncryptedRuntimeStore


@pytest.fixture()
def client():
    main.AUTH_REQUIRED = False
    return TestClient(app)


# --- Artifacts API ---

def test_artifacts_crud_and_versions(client):
    r = client.post("/artifacts", json={"title": "Plan", "kind": "markdown",
                                        "content": "# v1", "tags": ["work"]})
    assert r.status_code == 201, r.text
    art = r.json()
    assert art["version"] == 1 and art["title"] == "Plan"
    aid = art["id"]

    r = client.get("/artifacts")
    assert r.json()["total"] >= 1
    assert all("content" not in a for a in r.json()["artifacts"])  # list is meta-only

    r = client.get(f"/artifacts/{aid}")
    assert r.json()["content"] == "# v1"

    r = client.patch(f"/artifacts/{aid}", json={"content": "# v2"})
    assert r.json()["version"] == 2

    r = client.get(f"/artifacts/{aid}/versions")
    versions = r.json()["versions"]
    assert [v["version"] for v in versions] == [1, 2]

    r = client.get(f"/artifacts/{aid}/versions/1")
    assert r.json()["content"] == "# v1"

    r = client.delete(f"/artifacts/{aid}")
    assert r.json()["deleted_artifact"] == aid
    assert client.get(f"/artifacts/{aid}").status_code == 404


def test_artifacts_validation(client):
    assert client.post("/artifacts", json={"title": "", "content": "x"}).status_code == 422
    assert client.post("/artifacts", json={"title": "T", "kind": "pdf"}).status_code == 422
    assert client.post("/artifacts", json={"title": "T", "content": "x" * (1024 * 1024 + 1)}).status_code == 422
    assert client.get("/artifacts", params={"kind": "pdf"}).status_code == 422
    assert client.get("/artifacts/nope").status_code == 404
    assert client.patch("/artifacts/nope", json={"content": "x"}).status_code == 404


def test_artifacts_persist_across_restart():
    path = tempfile.NamedTemporaryFile().name
    key = EncryptedRuntimeStore(path, key=None).key
    s1 = ArtifactStore(EncryptedRuntimeStore(path, key=key))
    a = s1.create(ArtifactCreate(title="Keep", content="data"))
    s1.update(a.id, ArtifactUpdate(content="data2"))
    s2 = ArtifactStore(EncryptedRuntimeStore(path, key=key))
    assert s2.get(a.id).version == 2
    assert len(s2.versions(a.id)) == 2
    assert s2.get_version(a.id, 1).content == "data"


def test_artifact_store_caps():
    s = ArtifactStore(None)
    for i in range(5):
        a = s.create(ArtifactCreate(title=f"T{i}", content="x"))
        for _ in range(3):
            s.update(a.id, ArtifactUpdate(content="y"))
    assert len(s.versions(a.id)) <= 50


# --- Voice ---

def test_voice_capabilities_unconfigured(client):
    body = client.get("/voice/capabilities").json()
    assert body["tts"]["available"] is False
    assert body["stt"]["available"] is False
    assert "SHADOW_TTS_ENDPOINT" in body["tts"]["note"]


def test_voice_speak_503_when_unconfigured(client):
    r = client.post("/voice/speak", json={"text": "hello"})
    assert r.status_code == 503, r.text


def test_voice_transcribe_503_when_unconfigured(client):
    r = client.post("/voice/transcribe", files={"audio": ("r.m4a", b"data", "audio/mp4")})
    assert r.status_code == 503, r.text


class _FakeResp:
    def __init__(self, content=b"", json_body=None):
        self.content = content
        self._json = json_body
    def raise_for_status(self):
        pass
    def json(self):
        return self._json


def test_voice_speak_success_via_provider(monkeypatch, client):
    monkeypatch.setenv("SHADOW_TTS_ENDPOINT", "https://tts.example/v1")
    monkeypatch.setattr(voice_mod.httpx, "post",
                        lambda *a, **k: _FakeResp(content=b"MP3DATA"))
    r = client.post("/voice/speak", json={"text": "hello there"})
    assert r.status_code == 200, r.text
    assert r.content == b"MP3DATA"
    assert r.headers["content-type"] == "audio/mpeg"


def test_voice_transcribe_success_via_provider(monkeypatch, client):
    monkeypatch.setenv("SHADOW_STT_ENDPOINT", "https://stt.example/v1")
    monkeypatch.setattr(voice_mod.httpx, "post",
                        lambda *a, **k: _FakeResp(json_body={"text": "hello world", "language": "en"}))
    r = client.post("/voice/transcribe", files={"audio": ("r.m4a", b"data", "audio/mp4")})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hello world"


def test_voice_provider_failure_maps_to_502(monkeypatch, client):
    import httpx as _httpx
    monkeypatch.setenv("SHADOW_TTS_ENDPOINT", "https://tts.example/v1")
    def boom(*a, **k):
        raise _httpx.ConnectError("down")
    monkeypatch.setattr(voice_mod.httpx, "post", boom)
    assert client.post("/voice/speak", json={"text": "hi"}).status_code == 502


# --- Transcribe: binary-safe auth and JSON upload path ---

@pytest.fixture()
def authed_client(monkeypatch):
    """TestClient with HMAC auth enforced and one trusted device registered."""
    import shadow_node.main as m
    monkeypatch.setattr(m, "AUTH_REQUIRED", True)
    dev_snap = dict(m.sessions.devices)
    sec_snap = dict(m.sessions.secrets)
    m.sessions.devices.clear()
    m.sessions.secrets.clear()
    secret = "t3stsecret" * 4
    m.sessions.devices["dev_test"] = Device(
        id="dev_test", name="Test", public_key="pk", fingerprint="fp", trusted=True)
    m.sessions.secrets["dev_test"] = secret
    yield TestClient(m.app), secret
    m.sessions.devices.clear(); m.sessions.devices.update(dev_snap)
    m.sessions.secrets.clear(); m.sessions.secrets.update(sec_snap)


def _auth_headers(secret, method, path, body, nonce):
    ts = int(time.time())
    return {"x-shadow-device-id": "dev_test",
            "x-shadow-signature": sign_request(secret, method, path, body, nonce, ts),
            "x-shadow-nonce": nonce, "x-shadow-timestamp": str(ts)}


def test_transcribe_binary_multipart_passes_auth(authed_client):
    """Real AAC-like bytes are not valid UTF-8. The middleware must not
    crash; multipart bodies are signed by SHA-256 digest (see
    _canonical_body). 503 here means auth passed and only the unconfigured
    STT provider refused."""
    client, secret = authed_client
    boundary = "----testboundary"
    audio = bytes(range(256)) * 4  # deliberately not valid UTF-8
    raw = (f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; '
           f'filename="r.m4a"\r\nContent-Type: audio/mp4\r\n\r\n').encode() + audio + \
        f'\r\n--{boundary}--\r\n'.encode()
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    headers = _auth_headers(secret, "POST", "/voice/transcribe", digest, "mp1")
    headers["content-type"] = f"multipart/form-data; boundary={boundary}"
    r = client.post("/voice/transcribe", content=raw, headers=headers)
    assert r.status_code == 503, r.text  # not 401 (bad sig) and not 500 (decode crash)


def test_transcribe_binary_multipart_wrong_digest_rejected(authed_client):
    client, secret = authed_client
    boundary = "----testboundary"
    raw = b"--" + boundary.encode() + b"--\r\n"
    headers = _auth_headers(secret, "POST", "/voice/transcribe", "sha256:deadbeef", "mp2")
    headers["content-type"] = f"multipart/form-data; boundary={boundary}"
    assert client.post("/voice/transcribe", content=raw, headers=headers).status_code == 401


def test_transcribe_json_binary_audio(monkeypatch, client):
    """JSON {audio_base64} path: binary audio never touches the multipart
    digest rule and signs as ordinary JSON text."""
    monkeypatch.setenv("SHADOW_STT_ENDPOINT", "https://stt.example/v1")
    monkeypatch.setattr(voice_mod.httpx, "post",
                        lambda *a, **k: _FakeResp(json_body={"text": "hi", "language": "en"}))
    audio = bytes(range(256)) * 100
    r = client.post("/voice/transcribe",
                    json={"audio_base64": base64.b64encode(audio).decode(),
                          "filename": "r.m4a", "mime_type": "audio/mp4"})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hi"


def test_transcribe_json_validation(client):
    assert client.post("/voice/transcribe", json={}).status_code == 422
    r = client.post("/voice/transcribe", json={"audio_base64": "!!!not-base64!!!"})
    assert r.status_code == 422


# --- Media ---

def test_media_capabilities_unconfigured(client):
    body = client.get("/media/capabilities").json()
    assert body["generate"]["available"] is False


def test_media_generate_503_when_unconfigured(client):
    r = client.post("/media/generate", json={"prompt": "a cat"})
    assert r.status_code == 503, r.text


def test_media_generate_list_serve_delete(monkeypatch, client):
    monkeypatch.setenv("SHADOW_IMAGE_ENDPOINT", "https://img.example/v1")
    png = b"\x89PNG" + b"0" * 64
    payload = {"data": [{"b64_json": base64.b64encode(png).decode()}]}
    monkeypatch.setattr(media_mod.httpx, "post", lambda *a, **k: _FakeResp(json_body=payload))
    r = client.post("/media/generate", json={"prompt": "a cat", "size": "1024x1024"})
    assert r.status_code == 201, r.text
    item = r.json()
    mid = item["id"]
    assert item["bytes"] == len(png)

    r = client.get("/media")
    assert r.json()["total"] >= 1

    r = client.get(f"/media/{mid}/content")
    assert r.status_code == 200
    assert r.content == png
    assert r.headers["content-type"] == "image/png"

    assert client.delete(f"/media/{mid}").json()["deleted_media"] == mid
    assert client.get(f"/media/{mid}/content").status_code == 404


def test_media_generate_validation(client):
    assert client.post("/media/generate", json={"prompt": ""}).status_code == 422
    assert client.post("/media/generate", json={"prompt": "x", "size": "1x1"}).status_code == 422


def test_media_store_cap():
    s = media_mod.MediaStore(None)
    for i in range(media_mod.MEDIA_CAP + 5):
        s.add(f"p{i}", "1024x1024", b"1" * 16)
    items, total = s.list(limit=500)
    assert total == media_mod.MEDIA_CAP


# --- Agent tools ---

def test_agent_artifact_tools_registered():
    assert {"artifact_create", "artifact_update", "artifact_read"} <= set(main.core.tools.names())
    # Exercise the registered handlers directly, as the agent loop would.
    create = main.core.tools._tools["artifact_create"]
    out = create({"title": "Agent note", "content": "hello"})
    assert out["id"].startswith("art_")
    assert out["reference"] == f"artifact:{out['id']}"
    out2 = main.core.tools._tools["artifact_read"]({"id": out["id"]})
    assert out2["content"] == "hello"
    out3 = main.core.tools._tools["artifact_update"]({"id": out["id"], "content": "hello v2"})
    assert out3["version"] == 2
