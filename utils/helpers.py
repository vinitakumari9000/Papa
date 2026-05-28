"""Shared helpers for config loading, logging, and secret handling."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv
from eth_account import Account
from project.wallet.encryption import decrypt_secret, is_encrypted_payload


DEFAULT_SETTINGS: Dict[str, Any] = {
    "default_chain": "skale_base_sepolia",
    "database_path": "wallets.db",
    "rpc_timeout": 20,
    "retry_count": 3,
    "retry_backoff_seconds": 1.5,
    "gas": {"strategy": "auto", "default_limit": 21000},
}


def project_root() -> Path:
    """Return project root based on this file path."""
    return Path(__file__).resolve().parent.parent


def load_settings(path: str | Path | None = None) -> Dict[str, Any]:
    """Load YAML settings merged with defaults."""
    load_dotenv()
    settings_path = Path(path) if path else project_root() / "config" / "settings.yaml"
    data: Dict[str, Any] = {}
    if settings_path.exists():
        loaded = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded

    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)
    merged["database_path"] = os.getenv("PAPA_DB_PATH", str(merged.get("database_path", "wallets.db")))
    return merged


def setup_rotating_logger(name: str, file_name: str, level: int = logging.INFO) -> logging.Logger:
    """Set up rotating logger under logs/ directory."""
    log_dir = project_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    logger.handlers.clear()

    handler = logging.handlers.RotatingFileHandler(
        log_dir / file_name,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(handler)
    return logger


def secure_private_key(raw_value: str) -> str:
    """Return plaintext private key from plain or optional encrypted JSON keystore."""
    value = raw_value.strip()
    if not value:
        raise ValueError("Empty private key value")

    if is_encrypted_payload(value):
        password = os.getenv("PAPA_WALLET_PASSWORD")
        if not password:
            raise ValueError(
                "Encrypted wallet detected but PAPA_WALLET_PASSWORD is not set. "
                "Set it with: export PAPA_WALLET_PASSWORD='your_password'"
            )
        return decrypt_secret(value, password)

    if value.startswith("{") and value.endswith("}"):
        password = os.getenv("PAPA_WALLET_PASSWORD")
        if not password:
            raise ValueError(
                "Encrypted keystore detected but PAPA_WALLET_PASSWORD is not set. "
                "Set it with: export PAPA_WALLET_PASSWORD='your_password'"
            )
        key_json = json.loads(value)
        key_bytes = Account.decrypt(key_json, password)
        return f"0x{key_bytes.hex()}"

    return value
