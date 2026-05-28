#!/usr/bin/env python3
from __future__ import annotations

import importlib
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

from cli.commands_existing import app, balance_command
from cli.interactive import run_interactive_session
from utils.helpers import project_root
from wallet.chains import ChainRegistry
from wallet.database import DatabaseManager

console = Console()


@app.command("ai")
def ai_command() -> None:
    run_interactive_session(console)


@app.command("generate")
def generate_command() -> None:
    console.print("[yellow]Use wallet_gen.py workflows; generate command wired for compatibility.[/yellow]")


@app.command("export")
def export_command() -> None:
    console.print("[yellow]Use converter.py workflows; export command wired for compatibility.[/yellow]")


@app.command("logs")
def logs_command(lines: int = typer.Option(50, min=1, max=1000)) -> None:
    log_files = sorted((project_root() / "logs").glob("*.log"))
    if not log_files:
        console.print("[yellow]No log files found[/yellow]")
        return
    for path in log_files:
        console.print(f"[bold]{path.name}[/bold]")
        for line in path.read_text(encoding='utf-8', errors='ignore').splitlines()[-lines:]:
            console.print(line)


@app.command("doctor")
def doctor_command(db: Optional[str] = typer.Option(None)) -> None:
    checks=[]
    ollama_bin = shutil.which("ollama")
    checks.append(("Ollama installed", ollama_bin is not None, ollama_bin or "ollama binary not found"))
    if ollama_bin:
        proc = subprocess.run([ollama_bin, "list"], capture_output=True, text=True)
        checks.append(("Ollama running", proc.returncode == 0, (proc.stderr or proc.stdout).strip() or "ok"))
        has_model = "NAME" in proc.stdout and len(proc.stdout.splitlines()) > 1
        checks.append(("Ollama model presence", has_model, "Model(s) available" if has_model else "No models listed"))
    else:
        checks += [("Ollama running", False, "skipped"), ("Ollama model presence", False, "skipped")]

    try:
        dbm = DatabaseManager(db_path=db)
        dbm.migrate()
        dbm.list_wallets(limit=1)
        checks.append(("DB access", True, dbm.db_path))
        chains = ChainRegistry(dbm).list()
        rpc_ok = False
        detail = "no active networks"
        if chains:
            from web3 import HTTPProvider, Web3

            rpc = chains[0].rpc_url
            rpc_ok = Web3(HTTPProvider(rpc, request_kwargs={"timeout": 5})).is_connected()
            detail = rpc
        checks.append(("RPC reachability", bool(rpc_ok), detail))
    except Exception as exc:
        checks.append(("DB access", False, str(exc)))
        checks.append(("RPC reachability", False, "skipped"))

    try:
        settings_path = project_root()/"config"/"settings.yaml"
        loaded = yaml.safe_load(settings_path.read_text()) if settings_path.exists() else {}
        checks.append(("Config validity", isinstance(loaded, dict), str(settings_path)))
    except Exception as exc:
        checks.append(("Config validity", False, str(exc)))

    dep_errors=[]
    for dep in ["typer","rich","sqlalchemy","web3","yaml","eth_account","aiohttp"]:
        try: importlib.import_module(dep)
        except Exception as exc: dep_errors.append(f"{dep}: {exc}")
    checks.append(("Dependency imports", not dep_errors, "; ".join(dep_errors) if dep_errors else "all imports ok"))

    table=Table(title="Doctor Health Checks")
    table.add_column("Check"); table.add_column("Status"); table.add_column("Details")
    for n,ok,d in checks:
        table.add_row(n, "[green]PASS[/green]" if ok else "[red]FAIL[/red]", d)
    console.print(table)


app.command("balances")(balance_command)

if __name__ == "__main__":
    app()
