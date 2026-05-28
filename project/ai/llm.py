from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass

from project.config import load_config


@dataclass(slots=True)
class OllamaStatus:
    installed: bool
    running: bool
    model_available: bool
    detail: str


class OllamaClient:
    def __init__(self):
        self.cfg = load_config()

    def _url(self, path: str) -> str:
        return f"{self.cfg.ollama.host.rstrip('/')}{path}"

    def status(self) -> OllamaStatus:
        installed = shutil.which("ollama") is not None
        if not installed:
            return OllamaStatus(False, False, False, "ollama binary not found")

        try:
            req = urllib.request.Request(self._url("/api/tags"), method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            model_names = {m.get("name") for m in payload.get("models", [])}
            target = self.cfg.ollama.model
            return OllamaStatus(True, True, target in model_names, "ok")
        except Exception as exc:
            return OllamaStatus(True, False, False, str(exc))

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.cfg.ollama.model,
            "prompt": f"{system_prompt}\n\nUser request:\n{user_prompt}",
            "stream": False,
        }
        req = urllib.request.Request(
            self._url("/api/generate"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.ollama.timeout_seconds) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
                return str(parsed.get("response", "")).strip()
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama unavailable: {exc}") from exc
