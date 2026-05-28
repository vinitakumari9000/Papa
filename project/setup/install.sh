#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ -f /etc/debian_version ]]; then
  echo "Detected Debian/Ubuntu"
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-venv python3-pip curl
elif [[ -f /etc/centos-release || -f /etc/redhat-release ]]; then
  echo "Detected CentOS/RHEL"
  sudo yum install -y python3 python3-pip curl
else
  echo "Unsupported OS for auto-package install; continuing with existing tools"
fi

python3 "$ROOT_DIR/project/setup/setup.py"

echo "alias papa='python3 $ROOT_DIR/project/cli/main.py'" >> "$HOME/.bashrc"

echo "Setup complete. Run: source ~/.bashrc && papa doctor"
