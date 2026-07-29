"""
Grace-window key rotation for the app-owned crypto keys.

SECRET_KEY: a token signed with the PREVIOUS key still verifies during a rotation
(so no forced logout); an unknown-key token is rejected; expiry still wins.
FERNET_KEY: data encrypted under an OLD key still decrypts after the new key
becomes primary (so rotation never orphans encrypted data); new writes use the
primary. monkeypatch swaps the singleton settings and auto-restores.
"""
from datetime import datetime, timedelta

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from backend.config import settings
from backend.services.auth import decode_token
from backend.services import encryption


def _tok(key: str, **claims) -> str:
    payload = {"sub": "u1", "type": "access",
               "exp": datetime.utcnow() + timedelta(minutes=5)}
    payload.update(claims)
    return jwt.encode(payload, key, algorithm="HS256")


# ── SECRET_KEY rotation ──────────────────────────────────────────────────────
def test_token_signed_with_previous_key_still_verifies(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "new-key")
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "old-key")
    assert decode_token(_tok("old-key"))["sub"] == "u1"


def test_token_signed_with_current_key_verifies(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "new-key")
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "old-key")
    assert decode_token(_tok("new-key"))["sub"] == "u1"


def test_token_signed_with_unknown_key_rejected(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "new-key")
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "old-key")
    with pytest.raises(HTTPException) as exc:
        decode_token(_tok("attacker-key"))
    assert exc.value.status_code == 401


def test_no_previous_key_configured_still_works(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "only-key")
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "")
    assert decode_token(_tok("only-key"))["sub"] == "u1"
    with pytest.raises(HTTPException):
        decode_token(_tok("wrong-key"))


def test_expired_token_rejected_even_during_rotation(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "new-key")
    monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", "old-key")
    expired = jwt.encode(
        {"sub": "u1", "type": "access", "exp": datetime.utcnow() - timedelta(minutes=1)},
        "old-key", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        decode_token(expired)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


# ── FERNET_KEY rotation ──────────────────────────────────────────────────────
def test_fernet_decrypts_data_written_under_previous_key(monkeypatch):
    k_old = Fernet.generate_key().decode()
    k_new = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "FERNET_KEY", k_new)
    monkeypatch.setattr(settings, "FERNET_KEYS_PREVIOUS", k_old)
    # A blob encrypted with the OLD key before rotation must still read.
    blob = Fernet(k_old.encode()).encrypt(b'{"hudl": "cookie"}')
    assert encryption.decrypt_json(blob) == {"hudl": "cookie"}


def test_fernet_encrypts_with_primary_key(monkeypatch):
    k_old = Fernet.generate_key().decode()
    k_new = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "FERNET_KEY", k_new)
    monkeypatch.setattr(settings, "FERNET_KEYS_PREVIOUS", k_old)
    blob = encryption.encrypt_json({"a": 1})
    # The new primary alone can read a fresh write; the service round-trips too.
    assert Fernet(k_new.encode()).decrypt(blob) == b'{"a": 1}'
    assert encryption.decrypt_json(blob) == {"a": 1}
