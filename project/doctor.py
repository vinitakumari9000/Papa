from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import List

from project.ai.llm import OllamaClient
from project.config import load_config, project_root
from project.database.manager import DatabaseBootstrap


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


class Doctor:
    REQUIRED_PACKAGES = ["typer", "rich", "prompt_toolkit", "cryptography", "pydantic", "sqlalchemy", "ollama"]

    def run(self) -> List[CheckResult]:
        results: List[CheckResult] = []
        cfg = load_config()

        cfg_path = project_root() / "config" / "config.yaml"
        results.append(CheckResult("config_file", cfg_path.exists(), str(cfg_path)))

        for folder in [project_root() / "logs", project_root() / "config"]:
            folder.mkdir(parents=True, exist_ok=True)
            results.append(CheckResult(f"folder:{folder.name}", folder.exists(), str(folder)))

        db = DatabaseBootstrap()
        db_health = db.health()
        results.append(CheckResult("database", db_health.connected, db_health.message))

        oc = OllamaClient().status()
        results.append(CheckResult("ollama_installed", oc.installed, oc.detail))
        results.append(CheckResult("ollama_running", oc.running, oc.detail))
        results.append(CheckResult("ollama_model", oc.model_available, cfg.ollama.model))

        for name in self.REQUIRED_PACKAGES:
            try:
                importlib.import_module(name)
                results.append(CheckResult(f"dependency:{name}", True, "installed"))
            except Exception as exc:
                results.append(CheckResult(f"dependency:{name}", False, str(exc)))

        return results
