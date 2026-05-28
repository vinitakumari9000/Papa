from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


@dataclass
class EncryptedPrivateKey:
    ciphertext: str
    salt: str
    nonce: str


def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(password.encode("utf-8"))


def encrypt_private_key(private_key: str, password: str, iterations: int = 250000) -> EncryptedPrivateKey:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(password, salt, iterations)
    aes = AESGCM(key)
    ciphertext = aes.encrypt(nonce, private_key.encode("utf-8"), None)
    return EncryptedPrivateKey(
        ciphertext=base64.b64encode(ciphertext).decode("utf-8"),
        salt=base64.b64encode(salt).decode("utf-8"),
        nonce=base64.b64encode(nonce).decode("utf-8"),
    )


def decrypt_private_key(ciphertext: str, salt: str, nonce: str, password: str, iterations: int = 250000) -> str:
    salt_bytes = base64.b64decode(salt)
    nonce_bytes = base64.b64decode(nonce)
    encrypted_bytes = base64.b64decode(ciphertext)
    key = _derive_key(password, salt_bytes, iterations)
    aes = AESGCM(key)
    plain = aes.decrypt(nonce_bytes, encrypted_bytes, None)
    return plain.decode("utf-8")
