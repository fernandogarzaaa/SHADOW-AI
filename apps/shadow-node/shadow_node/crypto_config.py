from __future__ import annotations
import os
from pathlib import Path
from cryptography.fernet import Fernet


def data_dir() -> Path:
    """Root for node state: ``SHADOW_DATA_DIR`` (``/data`` in the Docker
    image, so keys live on the volume) or ``data`` relative to the CWD."""
    return Path(os.getenv("SHADOW_DATA_DIR", "data"))


def key_path(name: str) -> str:
    return str(data_dir() / "keys" / name)


def write_secret_file(path: Path | str, data: bytes) -> None:
    """Write secret material so it is never readable by other users, not
    even briefly: the file is created 0600 (write-then-chmod left a window
    where it had umask permissions) and atomically renamed into place."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_fernet_key(env_name: str, file_env_name: str, default_path: str) -> bytes:
    """Load or create a stable local Fernet key without logging secret material.

    Resolution order:
      1. An explicit key passed via ``env_name`` (urlsafe base64 Fernet key).
      2. A key file path from ``file_env_name`` (defaults to ``default_path``).
      3. A freshly generated key, persisted to the file path with 0600 perms.

    This makes encrypted memory survive process restarts instead of being lost
    behind an ephemeral in-memory key.
    """
    explicit = os.getenv(env_name)
    if explicit:
        return explicit.encode()
    key_file = Path(os.getenv(file_env_name, default_path))
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        return key_file.read_bytes().strip()
    key = Fernet.generate_key()
    write_secret_file(key_file, key)
    return key
