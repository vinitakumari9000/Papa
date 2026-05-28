"""Centralized secret redaction, confirmations, and optional encryption utilities."""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


_RE_HEX_PRIVATE_KEY = re.compile(r"0x[a-fA-F0-9]{64}|(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])")


@dataclass(frozen=True)
class EncryptionSettings:
    key_material_env: str = "PAPA_SECRET_KEY_MATERIAL"
    salt_env: str = "PAPA_SECRET_SALT"
    iterations_env: str = "PAPA_SECRET_KDF_ITERATIONS"
    default_iterations: int = 390000


def mask_secret(value: str, visible_prefix: int = 6, visible_suffix: int = 4) -> str:
    value = value or ""
    if len(value) <= visible_prefix + visible_suffix:
        return "***"
    return f"{value[:visible_prefix]}***{value[-visible_suffix:]}"


def redact_text(text: Any) -> str:
    raw = str(text)
    return _RE_HEX_PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", raw)


def require_export_permission(explicit_permission: bool) -> None:
    if not explicit_permission:
        raise PermissionError(
            "Private-key export is blocked by default. Re-run with --allow-private-key-export to proceed."
        )


def require_interactive_confirmation(prompt: str = "Type YES to confirm private-key export: ") -> None:
    answer = input(prompt).strip()
    if answer != "YES":
        raise PermissionError("Private-key export cancelled by user confirmation policy")


def _build_fernet(settings: EncryptionSettings = EncryptionSettings()) -> Fernet:
    key_material = os.getenv(settings.key_material_env)
    salt_text = os.getenv(settings.salt_env)
    iterations = int(os.getenv(settings.iterations_env, str(settings.default_iterations)))

    if not key_material or not salt_text:
        raise ValueError(
            f"Encryption requires env vars {settings.key_material_env} and {settings.salt_env}."
        )

    salt = salt_text.encode("utf-8")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    key = base64.urlsafe_b64encode(kdf.derive(key_material.encode("utf-8")))
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    token = _build_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"enc:v1:{token}"


def decrypt_secret(value: str) -> str:
    if not value.startswith("enc:v1:"):
        return value
    token = value.split("enc:v1:", 1)[1]
    return _build_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
