"""Python installer wrapper for environment bootstrap."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_install_script() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    script = repo_root / "install.sh"
    return subprocess.call(["bash", str(script)], cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(run_install_script())
