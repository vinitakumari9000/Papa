from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


DEFAULT_CONFIG: Dict[str, Any] = {
    "default_chain": "ethereum",
    "rpc_urls": {
        "ethereum": "https://rpc.ankr.com/eth",
        "polygon": "https://rpc.ankr.com/polygon",
        "arbitrum": "https://rpc.ankr.com/arbitrum",
    },
    "ollama": {"model": "qwen2.5:3b", "host": "http://127.0.0.1:11434"},
    "database": {"path": "wallets.db"},
    "encryption": {"kdf_iterations": 250000, "require_password": True},
    "export": {"default_format": "json", "allow_unsafe": False, "directory": "exports"},
}


def ensure_config(path: Path) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False), encoding="utf-8")
        return DEFAULT_CONFIG.copy()
    return load_config(path)


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return ensure_config(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    merged = DEFAULT_CONFIG.copy()
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def save_config(path: Path, config: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
