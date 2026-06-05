from cryptography.fernet import Fernet
import json
from backend.config import settings

def get_fernet() -> Fernet:
    return Fernet(settings.FERNET_KEY.encode())

def encrypt_json(data: dict) -> bytes:
    return get_fernet().encrypt(json.dumps(data).encode())

def decrypt_json(data: bytes) -> dict:
    return json.loads(get_fernet().decrypt(data).decode())
