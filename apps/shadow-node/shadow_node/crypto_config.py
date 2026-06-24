from __future__ import annotations
import os
from pathlib import Path
from cryptography.fernet import Fernet


def load_fernet_key(env_name: str, file_env_name: str, default_path: str) -> bytes:
    """Load or create a stable local Fernet key without logging secret material."""
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
