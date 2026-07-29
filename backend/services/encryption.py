"""
Symmetric encryption for at-rest secrets (Hudl connection credentials, report
summaries).

Supports grace-window key rotation via MultiFernet: encryption always uses the
PRIMARY key (settings.FERNET_KEY); decryption tries the primary first, then each
key in settings.FERNET_KEYS_PREVIOUS (comma-separated). So when you rotate, set
the new key as FERNET_KEY and move the old one into FERNET_KEYS_PREVIOUS, and
already-encrypted data still reads. Drop the old key once everything is
re-encrypted. See CREDENTIAL_ROTATION_SCHEDULE.md.
"""
from cryptography.fernet import Fernet, MultiFernet
import json
from backend.config import settings


def _keys() -> list:
    """Primary key first, then any previous keys; de-duped, blanks dropped."""
    raw = [settings.FERNET_KEY] + [k.strip() for k in (settings.FERNET_KEYS_PREVIOUS or "").split(",")]
    seen, out = set(), []
    for k in raw:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def get_fernet() -> MultiFernet:
    """MultiFernet over [primary, *previous]. encrypt() uses the first (primary);
    decrypt() tries each in order, so rotation never orphans encrypted data."""
    return MultiFernet([Fernet(k.encode()) for k in _keys()])


def encrypt_json(data: dict) -> bytes:
    return get_fernet().encrypt(json.dumps(data).encode())


def decrypt_json(data: bytes) -> dict:
    return json.loads(get_fernet().decrypt(data).decode())
