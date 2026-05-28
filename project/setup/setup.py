from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from project.ai.llm import OllamaClient
from project.cli.health import run_healthcheck
from project.config.settings import ensure_config


ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def detect_os_family() -> str:
    if Path("/etc/debian_version").exists():
        return "debian"
    if Path("/etc/centos-release").exists() or Path("/etc/redhat-release").exists():
        return "centos"
    return platform.system().lower()


def install_ollama() -> None:
    if shutil.which("ollama"):
        return
    run(["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"])


def ensure_venv() -> Path:
    venv_path = ROOT / ".venv"
    if not venv_path.exists():
        run([sys.executable, "-m", "venv", str(venv_path)])
    return venv_path


def install_requirements(venv_path: Path) -> None:
    pip_bin = venv_path / "bin" / "pip"
    run([str(pip_bin), "install", "--upgrade", "pip"])
    run([str(pip_bin), "install", "-r", str(ROOT / "requirements.txt")])


def initialize_runtime() -> None:
    cfg = ensure_config(ROOT / "config" / "config.yaml")
    Path(ROOT / "logs").mkdir(parents=True, exist_ok=True)
    Path(ROOT / cfg["export"]["directory"]).mkdir(parents=True, exist_ok=True)
    db_path = ROOT / cfg["database"]["path"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.touch(exist_ok=True)


def ensure_model() -> None:
    cfg = ensure_config(ROOT / "config" / "config.yaml")
    client = OllamaClient(host=cfg["ollama"]["host"], model=cfg["ollama"]["model"])
    client.ensure_model()


def healthcheck() -> dict:
    cfg = ensure_config(ROOT / "config" / "config.yaml")
    return run_healthcheck(
        db_path=str(ROOT / cfg["database"]["path"]),
        model=cfg["ollama"]["model"],
        host=cfg["ollama"]["host"],
    )


def main() -> None:
    print(f"Detected OS family: {detect_os_family()}")
    install_ollama()
    venv_path = ensure_venv()
    install_requirements(venv_path)
    initialize_runtime()
    ensure_model()
    report = healthcheck()
    print("Health check:", report)


if __name__ == "__main__":
    main()
