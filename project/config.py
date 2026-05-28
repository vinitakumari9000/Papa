from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field


class EncryptionConfig(BaseModel):
    enabled: bool = True
    pbkdf2_iterations: int = 390000


class OllamaConfig(BaseModel):
    host: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b"
    timeout_seconds: int = 60


class ExportConfig(BaseModel):
    default_format: str = "csv"
    allow_plaintext_private_keys: bool = False


class LoggingConfig(BaseModel):
    directory: str = "logs"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


class AppConfig(BaseModel):
    default_chain: str = "skale_base_sepolia"
    rpc_urls: Dict[str, str] = Field(default_factory=dict)
    database_path: str = "wallets.db"
    config_dir: str = "config"
    encryption: EncryptionConfig = Field(default_factory=EncryptionConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return project_root() / "config" / "config.yaml"


def load_config(path: Optional[str | Path] = None) -> AppConfig:
    target = Path(path) if path else config_path()
    payload: Dict[str, Any] = {}
    if target.exists():
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            payload = data

    if os.getenv("PAPA_DB_PATH"):
        payload["database_path"] = os.getenv("PAPA_DB_PATH")

    ollama_payload = payload.setdefault("ollama", {})
    if os.getenv("PAPA_OLLAMA_MODEL"):
        ollama_payload["model"] = os.getenv("PAPA_OLLAMA_MODEL")
    if os.getenv("PAPA_OLLAMA_HOST"):
        ollama_payload["host"] = os.getenv("PAPA_OLLAMA_HOST")

    return AppConfig.model_validate(payload)
