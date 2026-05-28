#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

OS_ID="unknown"
if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  OS_ID="${ID:-unknown}"
fi

echo "Detected OS: $OS_ID"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p logs config exports
python -m project.setup.setup

if ! command -v ollama >/dev/null 2>&1; then
  if command -v curl >/dev/null 2>&1; then
    echo "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
  else
    echo "curl not available; install Ollama manually from https://ollama.com/download"
  fi
fi

if command -v ollama >/dev/null 2>&1; then
  echo "Ensuring Ollama model qwen2.5:3b"
  ollama pull qwen2.5:3b || true
fi

python papa.py doctor || true

echo "Setup complete. Activate with: source .venv/bin/activate"
