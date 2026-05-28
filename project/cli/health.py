from __future__ import annotations

import importlib
from pathlib import Path

from project.ai.llm import OllamaClient


def run_healthcheck(db_path: str, model: str, host: str) -> dict:
    client = OllamaClient(host=host, model=model)
    checks = {
        "ollama_installed": client.is_installed(),
        "ollama_running": client.is_running(),
        "model_available": client.has_model(),
        "database_path_exists": Path(db_path).parent.exists(),
        "config_exists": Path("config/config.yaml").exists(),
        "logs_exists": Path("logs").exists(),
        "dependencies_installed": all(importlib.util.find_spec(pkg) is not None for pkg in ["typer", "rich", "cryptography", "sqlalchemy"]),
    }
    checks["healthy"] = all(checks.values())
    return checks
