from __future__ import annotations
import os
from pathlib import Path
from cryptography.fernet import Fernet


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
    key_file.write_bytes(key)
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    return key
