from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from project.config import load_config


def _b64e(value: bytes) -> str:
    return base64.b64encode(value).decode("utf-8")


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("utf-8"))


def _derive_key(password: str, salt: bytes) -> bytes:
    cfg = load_config()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=cfg.encryption.pbkdf2_iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_secret(plaintext: str, password: str) -> str:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(password, salt)
    aes = AESGCM(key)
    ciphertext = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = {
        "v": 1,
        "alg": "aesgcm",
        "salt": _b64e(salt),
        "nonce": _b64e(nonce),
        "ct": _b64e(ciphertext),
    }
    return json.dumps(payload, separators=(",", ":"))


def is_encrypted_payload(value: str) -> bool:
    try:
        payload = json.loads(value)
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("alg") == "aesgcm" and payload.get("v") == 1


def decrypt_secret(value: str, password: str) -> str:
    payload = json.loads(value)
    salt = _b64d(payload["salt"])
    nonce = _b64d(payload["nonce"])
    ciphertext = _b64d(payload["ct"])
    key = _derive_key(password, salt)
    aes = AESGCM(key)
    return aes.decrypt(nonce, ciphertext, None).decode("utf-8")
