from __future__ import annotations

from pathlib import Path

import yaml

from project.config import config_path, project_root
from project.database.manager import DatabaseBootstrap


def ensure_default_config() -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        payload = {
            "default_chain": "skale_base_sepolia",
            "rpc_urls": {
                "skale_base_sepolia": "https://base-sepolia-testnet.skalenodes.com/v1/jubilant-horrible-ancha"
            },
            "database_path": "wallets.db",
            "config_dir": "config",
            "encryption": {"enabled": True, "pbkdf2_iterations": 390000},
            "ollama": {"host": "http://127.0.0.1:11434", "model": "qwen2.5:3b", "timeout_seconds": 60},
            "export": {"default_format": "csv", "allow_plaintext_private_keys": False},
            "logging": {"directory": "logs", "max_bytes": 10485760, "backup_count": 5},
        }
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def bootstrap() -> None:
    ensure_default_config()
    (project_root() / "logs").mkdir(parents=True, exist_ok=True)
    (project_root() / "config").mkdir(parents=True, exist_ok=True)
    DatabaseBootstrap().initialize()


if __name__ == "__main__":
    bootstrap()
