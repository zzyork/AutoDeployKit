import hashlib
import hmac
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet


def create_key_file(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("Encryption key path must be absolute")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o640), "wb") as key_file:
        key_file.write(Fernet.generate_key())


def hash_password(password):
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"scrypt:{salt.hex()}:{digest.hex()}"


def verify_password(password, encoded):
    try:
        algorithm, salt, digest = encoded.split(":")
        if algorithm != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt), n=16384, r=8, p=1
        )
        return hmac.compare_digest(candidate, bytes.fromhex(digest))
    except (AttributeError, TypeError, ValueError):
        return False
