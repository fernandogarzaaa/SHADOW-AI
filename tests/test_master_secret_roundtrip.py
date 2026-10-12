"""The node master secret must be identical across restarts (regression for a
flaky CI failure in test_paired_device_persists_across_restart)."""
import shadow_node.device_credentials as dc


def test_master_secret_with_whitespace_edges_survives_restart(monkeypatch, tmp_path):
    key = tmp_path / "master.key"
    monkeypatch.delenv("SHADOW_MASTER_SECRET", raising=False)
    monkeypatch.setenv("SHADOW_MASTER_SECRET_FILE", str(key))
    raw = b"\n" + bytes(range(1, 31)) + b" "  # 32 bytes, whitespace at both ends
    monkeypatch.setattr(dc.secrets, "token_bytes", lambda n: raw)
    first = dc.load_master_secret()
    second = dc.load_master_secret()
    assert first == raw
    assert second == first


def test_legacy_raw_master_file_still_loads(monkeypatch, tmp_path):
    key = tmp_path / "master.key"
    legacy = bytes(range(100, 132))  # 32 raw bytes, no whitespace edges
    key.write_bytes(legacy)
    monkeypatch.delenv("SHADOW_MASTER_SECRET", raising=False)
    monkeypatch.setenv("SHADOW_MASTER_SECRET_FILE", str(key))
    assert dc.load_master_secret() == legacy
