from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from urllib import request


@dataclass
class OllamaStatus:
    installed: bool
    running: bool
    model_available: bool


class OllamaClient:
    def __init__(self, host: str = "http://127.0.0.1:11434", model: str = "qwen2.5:3b"):
        self.host = host.rstrip("/")
        self.model = model

    def is_installed(self) -> bool:
        return shutil.which("ollama") is not None

    def _request(self, path: str, payload: dict | None = None, timeout: int = 10) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.host}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if data is None else "POST",
        )
        with request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            return json.loads(resp.read().decode("utf-8"))

    def is_running(self) -> bool:
        try:
            self._request("/api/tags")
            return True
        except Exception:
            return False

    def has_model(self) -> bool:
        try:
            tags = self._request("/api/tags")
            names = {m.get("name") for m in tags.get("models", [])}
            return self.model in names
        except Exception:
            return False

    def ensure_model(self) -> None:
        if self.has_model():
            return
        subprocess.run(["ollama", "pull", self.model], check=True)

    def generate(self, prompt: str, system_prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json",
        }
        response = self._request("/api/generate", payload=payload, timeout=60)
        return response.get("response", "")

    def status(self) -> OllamaStatus:
        installed = self.is_installed()
        running = self.is_running() if installed else False
        model_available = self.has_model() if running else False
        return OllamaStatus(installed=installed, running=running, model_available=model_available)
