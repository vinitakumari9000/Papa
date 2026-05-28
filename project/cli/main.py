from __future__ import annotations

import getpass
import json
from pathlib import Path
from typing import Optional

import typer
from prompt_toolkit import prompt
from rich import print
from rich.table import Table

from project.ai.llm import OllamaClient
from project.ai.parser import parse_tool_call
from project.ai.prompts import SYSTEM_PROMPT
from project.ai.tools import build_router
from project.cli.health import run_healthcheck
from project.config.settings import ensure_config, load_config
from project.wallet.exporter import WalletExporter
from project.wallet.generator import generate_wallet
from project.wallet.storage import WalletStorage

app = typer.Typer(help="Papa local AI-powered wallet orchestration CLI")


def _build_components(password: Optional[str] = None):
    cfg = load_config(Path("config/config.yaml"))
    resolved_password = password or getpass.getpass("Encryption password: ")
    storage = WalletStorage(
        cfg["database"]["path"],
        resolved_password,
        iterations=int(cfg["encryption"]["kdf_iterations"]),
    )
    storage.initialize()
    exporter = WalletExporter(storage, cfg["export"]["directory"])
    router = build_router(
        storage,
        exporter,
        doctor_handler=lambda: run_healthcheck(
            db_path=cfg["database"]["path"],
            model=cfg["ollama"]["model"],
            host=cfg["ollama"]["host"],
        ),
    )
    return cfg, storage, exporter, router


@app.command("generate")
def generate_cmd(
    count: int = typer.Option(1, "--count", min=1),
    password: Optional[str] = typer.Option(None, "--password", help="Encryption password"),
):
    _, storage, _, _ = _build_components(password)
    for _ in range(count):
        address, private_key = generate_wallet()
        storage.add_wallet(address, private_key)
    print(f"[green]Generated {count} wallets[/green]")


@app.command("export")
def export_cmd(
    format: str = typer.Option("json", "--format"),
    output: Optional[str] = typer.Option(None, "--output"),
    unsafe_export: bool = typer.Option(False, "--unsafe-export", help="Export plaintext private keys"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirm dangerous operation"),
    password: Optional[str] = typer.Option(None, "--password"),
):
    cfg, _, exporter, router = _build_components(password)
    if unsafe_export and not cfg["export"].get("allow_unsafe", False) and not confirm:
        raise typer.BadParameter("Unsafe export disabled by config. Use --confirm.")
    result = router.execute(
        "export_wallets",
        {"format": format, "unsafe_export": unsafe_export},
        confirm=confirm,
    )
    if output:
        src = Path(result["exported_to"])
        src.rename(src.parent / output)
        result["exported_to"] = str(src.parent / output)
    print(json.dumps(result, indent=2))


@app.command("wallets")
def wallets_cmd(
    limit: int = typer.Option(20, "--limit", min=1),
    offset: int = typer.Option(0, "--offset", min=0),
    password: Optional[str] = typer.Option(None, "--password"),
):
    _, _, _, router = _build_components(password)
    result = router.execute("list_wallets", {"limit": limit, "offset": offset})
    table = Table(title="Wallets")
    table.add_column("ID")
    table.add_column("Address")
    for row in result["wallets"]:
        table.add_row(str(row["id"]), row["address"])
    print(table)


@app.command("doctor")
def doctor_cmd():
    cfg = ensure_config(Path("config/config.yaml"))
    report = run_healthcheck(
        db_path=cfg["database"]["path"], model=cfg["ollama"]["model"], host=cfg["ollama"]["host"]
    )
    print(json.dumps(report, indent=2))


@app.command("config")
def config_cmd(show: bool = typer.Option(True, "--show")):
    cfg = ensure_config(Path("config/config.yaml"))
    if show:
        print(json.dumps(cfg, indent=2))


@app.command("ai")
def ai_cmd(
    instruction: Optional[str] = typer.Argument(None),
    dry_run: bool = typer.Option(False, "--dry-run"),
    confirm: bool = typer.Option(False, "--confirm"),
    password: Optional[str] = typer.Option(None, "--password"),
):
    cfg, _, _, router = _build_components(password)
    client = OllamaClient(host=cfg["ollama"]["host"], model=cfg["ollama"]["model"])

    def _run_once(text: str):
        raw = client.generate(prompt=text, system_prompt=SYSTEM_PROMPT)
        tool_call = parse_tool_call(raw)
        result = router.execute(tool_call.tool, tool_call.args, dry_run=dry_run, confirm=confirm)
        print(json.dumps({"tool_call": tool_call.__dict__, "result": result}, indent=2))

    if instruction:
        _run_once(instruction)
        return

    print("[bold cyan]Papa AI chat mode[/bold cyan] (type 'exit' to quit)")
    while True:
        text = prompt("papa> ").strip()
        if text.lower() in {"exit", "quit"}:
            break
        _run_once(text)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
