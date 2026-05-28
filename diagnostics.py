"""Diagnostics checks for `papa doctor`."""

from __future__ import annotations

import importlib
import json
import shutil
import socket
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import yaml
from rich.table import Table

from utils.helpers import load_settings, project_root
from wallet.database import DatabaseManager


@dataclass
class DiagnosticResult:
    name: str
    status: str
    message: str
    details: dict[str, Any] | None = None


REQUIRED_PYTHON_MODULES = [
    "typer",
    "rich",
    "yaml",
    "sqlalchemy",
    "dotenv",
    "eth_account",
    "web3",
    "aiohttp",
]


class Doctor:
    def run(self) -> list[DiagnosticResult]:
        return [
            self.check_ollama_binary(),
            self.check_ollama_daemon(),
            self.check_ollama_model("qwen2.5:3b"),
            self.check_db_connectivity_and_migrations(),
            self.check_default_chain_rpc(),
            self.check_settings_schema(),
            self.check_networks_schema(),
            self.check_python_dependencies(),
        ]

    def check_ollama_binary(self) -> DiagnosticResult:
        ollama_path = shutil.which("ollama")
        if not ollama_path:
            return DiagnosticResult("ollama_binary", "fail", "Ollama binary not found in PATH")
        return DiagnosticResult("ollama_binary", "pass", f"Found ollama binary at {ollama_path}")

    def check_ollama_daemon(self) -> DiagnosticResult:
        host = "127.0.0.1"
        port = 11434
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        try:
            sock.connect((host, port))
        except OSError as exc:
            return DiagnosticResult("ollama_daemon", "fail", f"Ollama daemon not reachable at {host}:{port} ({exc})")
        finally:
            sock.close()

        try:
            with urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as response:  # nosec B310
                if response.status != 200:
                    return DiagnosticResult("ollama_daemon", "warn", f"Port open but /api/tags returned HTTP {response.status}")
        except URLError as exc:
            return DiagnosticResult("ollama_daemon", "warn", f"Port open but API probe failed: {exc}")

        return DiagnosticResult("ollama_daemon", "pass", "Ollama daemon is reachable and responsive")

    def check_ollama_model(self, model_name: str) -> DiagnosticResult:
        try:
            with urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as response:  # nosec B310
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return DiagnosticResult("ollama_model", "warn", f"Could not query Ollama model list: {exc}", {"model": model_name})

        models = {m.get("name", "") for m in payload.get("models", [])}
        if model_name in models:
            return DiagnosticResult("ollama_model", "pass", f"Model '{model_name}' is installed locally")

        return DiagnosticResult("ollama_model", "fail", f"Model '{model_name}' is not installed", {"detected_models": sorted(models)})

    def check_db_connectivity_and_migrations(self) -> DiagnosticResult:
        try:
            db = DatabaseManager()
            db.migrate()
            wallets = db.list_wallets(limit=1)
            return DiagnosticResult(
                "database",
                "pass",
                "Database connectivity and migrations OK",
                {"db_path": db.db_path, "wallet_rows_preview": len(wallets)},
            )
        except Exception as exc:  # noqa: BLE001
            return DiagnosticResult("database", "fail", f"Database check failed: {exc}")

    def check_default_chain_rpc(self) -> DiagnosticResult:
        settings = load_settings()
        default_chain = settings.get("default_chain")
        networks = self._load_networks_raw()

        cfg = networks.get(default_chain)
        if not isinstance(cfg, dict):
            return DiagnosticResult("rpc_probe", "fail", f"Default chain '{default_chain}' missing in networks.json")

        rpc_url = cfg.get("rpc_url")
        if not isinstance(rpc_url, str) or not rpc_url:
            return DiagnosticResult("rpc_probe", "fail", f"Default chain '{default_chain}' has invalid rpc_url")

        try:
            from web3 import Web3

            web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": int(settings.get("rpc_timeout", 20))}))
            chain_id = web3.eth.chain_id
            block_number = web3.eth.block_number
            return DiagnosticResult(
                "rpc_probe",
                "pass",
                f"RPC reachable for '{default_chain}'",
                {"rpc_url": rpc_url, "chain_id": chain_id, "latest_block": block_number},
            )
        except Exception as exc:  # noqa: BLE001
            return DiagnosticResult("rpc_probe", "fail", f"RPC probe failed for '{default_chain}': {exc}", {"rpc_url": rpc_url})

    def check_settings_schema(self) -> DiagnosticResult:
        path = project_root() / "config" / "settings.yaml"
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return DiagnosticResult("settings_schema", "fail", f"Could not read settings.yaml: {exc}")

        required = {
            "default_chain": str,
            "database_path": str,
            "rpc_timeout": int,
            "retry_count": int,
            "retry_backoff_seconds": (int, float),
            "gas": dict,
        }
        err = self._validate_required_fields(data, required)
        if err:
            return DiagnosticResult("settings_schema", "fail", err)

        gas_required = {"strategy": str, "default_limit": int}
        gas_err = self._validate_required_fields(data["gas"], gas_required, prefix="gas")
        if gas_err:
            return DiagnosticResult("settings_schema", "fail", gas_err)

        return DiagnosticResult("settings_schema", "pass", "settings.yaml schema is valid")

    def check_networks_schema(self) -> DiagnosticResult:
        try:
            data = self._load_networks_raw()
        except Exception as exc:  # noqa: BLE001
            return DiagnosticResult("networks_schema", "fail", f"Could not read networks.json: {exc}")

        if not isinstance(data, dict) or not data:
            return DiagnosticResult("networks_schema", "fail", "networks.json must be a non-empty object")

        net_required = {
            "name": str,
            "rpc_url": str,
            "explorer": str,
            "native_token": str,
            "decimals": int,
            "chain_id": int,
        }

        for key, cfg in data.items():
            if not isinstance(cfg, dict):
                return DiagnosticResult("networks_schema", "fail", f"Network '{key}' must map to an object")
            err = self._validate_required_fields(cfg, net_required, prefix=f"network:{key}")
            if err:
                return DiagnosticResult("networks_schema", "fail", err)

        return DiagnosticResult("networks_schema", "pass", "networks.json schema is valid")

    def check_python_dependencies(self) -> DiagnosticResult:
        missing: list[str] = []
        for module in REQUIRED_PYTHON_MODULES:
            try:
                importlib.import_module(module)
            except Exception:  # noqa: BLE001
                missing.append(module)

        if missing:
            return DiagnosticResult(
                "python_deps",
                "fail",
                "Missing required Python modules",
                {"missing": missing},
            )
        return DiagnosticResult("python_deps", "pass", "All required Python modules import successfully")

    def _load_networks_raw(self) -> dict[str, Any]:
        path = project_root() / "config" / "networks.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _validate_required_fields(
        self,
        data: Any,
        required: dict[str, type | tuple[type, ...]],
        prefix: str | None = None,
    ) -> str | None:
        if not isinstance(data, dict):
            return f"{prefix or 'object'} must be a mapping"
        for key, expected_type in required.items():
            if key not in data:
                return f"Missing required field: {prefix + '.' if prefix else ''}{key}"
            if not isinstance(data[key], expected_type):
                return (
                    f"Invalid field type for {prefix + '.' if prefix else ''}{key}: "
                    f"expected {expected_type}, got {type(data[key]).__name__}"
                )
        return None


def render_rich_table(results: list[DiagnosticResult]) -> Table:
    table = Table(title="Papa Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Message")

    color = {"pass": "green", "warn": "yellow", "fail": "red"}
    for result in results:
        table.add_row(result.name, f"[{color.get(result.status, 'white')}]{result.status}[/]", result.message)
    return table


def render_json(results: list[DiagnosticResult]) -> dict[str, Any]:
    summary = {
        "pass": sum(1 for r in results if r.status == "pass"),
        "warn": sum(1 for r in results if r.status == "warn"),
        "fail": sum(1 for r in results if r.status == "fail"),
    }
    return {"summary": summary, "checks": [asdict(r) for r in results]}
