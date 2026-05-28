from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import typer
import yaml
from prompt_toolkit import PromptSession
from rich.console import Console
from rich.table import Table

from project.ai.router import SafeToolRouter
from project.config import config_path, load_config
from project.database.manager import DatabaseBootstrap
from project.doctor import Doctor
from project.logging_utils import get_logger
from project.wallet.exporter import WalletExporter
from project.wallet.generator import WalletGeneratorService
from project.wallet.storage import WalletStorage
from utils.helpers import load_settings
from wallet.balance import BalanceService
from wallet.chains import ChainRegistry
from wallet.database import DatabaseManager
from wallet.tx_sender import TransactionSender

app = typer.Typer(help="Papa local AI wallet orchestration CLI")
networks_app = typer.Typer(help="Network management commands")
config_app = typer.Typer(help="Config management")
app.add_typer(networks_app, name="networks")
app.add_typer(config_app, name="config")
console = Console()
logger = get_logger("cli", "ai.log")


def _legacy_services(db_path: Optional[str] = None) -> tuple[DatabaseManager, ChainRegistry, TransactionSender, BalanceService]:
    db = DatabaseManager(db_path=db_path)
    db.migrate()
    return db, ChainRegistry(db), TransactionSender(db), BalanceService(db)


def _storage(db_path: Optional[str] = None) -> WalletStorage:
    store = WalletStorage(db_path)
    store.ensure_schema()
    return store


@app.command("generate")
def generate_command(
    count: int = typer.Option(1, min=1),
    db: Optional[str] = typer.Option(None),
    encrypt: bool = typer.Option(True, help="Encrypt wallet private keys at rest"),
    migrate_plaintext: bool = typer.Option(False, help="Migrate existing plaintext keys to encrypted form"),
) -> None:
    """Generate wallets with encrypted storage by default."""
    store = _storage(db)
    password = None
    if encrypt:
        password = typer.prompt("Encryption password", hide_input=True, confirmation_prompt=True)

    if migrate_plaintext and password:
        changed = store.migrate_plaintext(**{"password": password})
        console.print(f"[yellow]Migrated {changed} plaintext wallets[/yellow]")

    service = WalletGeneratorService(store)
    created = service.generate_many(count=count, **{"password": password})
    console.print(f"[green]Generated {len(created)} wallets[/green]")


@app.command("export")
def export_command(
    format: str = typer.Option("csv", "--format"),
    output: str = typer.Option("exports/wallets_export.json"),
    db: Optional[str] = typer.Option(None),
    limit: Optional[int] = typer.Option(None),
    offset: int = typer.Option(0),
    unsafe_export: bool = typer.Option(False, help="Allow plaintext private key export"),
) -> None:
    """Export wallets with secure defaults."""
    password = None
    if unsafe_export or format == "keystore":
        password = typer.prompt("Wallet password", hide_input=True)

    exporter = WalletExporter(_storage(db))
    result = exporter.export(
        fmt=format,
        output=output,
        limit=limit,
        offset=offset,
        unsafe_export=unsafe_export,
        **{"password": password},
    )
    console.print(f"[green]Exported {result.exported} wallets to {result.path} ({result.format})[/green]")


@app.command("wallets")
def wallets_command(
    limit: int = typer.Option(20, min=1, max=500),
    tag: Optional[str] = typer.Option(None),
    db: Optional[str] = typer.Option(None),
) -> None:
    """List wallets from the database."""
    dbm, _, _, _ = _legacy_services(db)
    rows = dbm.list_wallets(limit=limit, tag=tag)

    table = Table(title="Wallets")
    table.add_column("ID")
    table.add_column("Address")
    for row in rows:
        table.add_row(str(row["id"]), row["address"])
    console.print(table)


@app.command("doctor")
def doctor_command() -> None:
    """Run local system health checks."""
    checks = Doctor().run()
    table = Table(title="Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    has_failures = False
    for check in checks:
        status = "[green]OK[/green]" if check.ok else "[red]FAIL[/red]"
        if not check.ok:
            has_failures = True
        table.add_row(check.name, status, check.detail)
    console.print(table)
    if has_failures:
        raise typer.Exit(code=1)


def _router(db: Optional[str] = None) -> SafeToolRouter:
    store = _storage(db)

    def generate_wallets(count: int = 1, export: Optional[str] = None) -> dict[str, Any]:
        password = typer.prompt("Encryption password", hide_input=True)
        wallets = WalletGeneratorService(store).generate_many(count=count, **{"password": password})
        payload: dict[str, Any] = {"generated": len(wallets)}
        if export:
            result = WalletExporter(store).export(
                fmt=export,
                output=f"exports/ai_wallets.{export}",
                unsafe_export=False,
                **{"password": None},
            )
            payload["exported"] = result.path
        return payload

    def export_wallets(format: str = "csv", unsafe_export: bool = False) -> dict[str, Any]:
        password = None
        if unsafe_export or format == "keystore":
            password = typer.prompt("Wallet password", hide_input=True)
        result = WalletExporter(store).export(
            fmt=format,
            output=f"exports/ai_export.{format}",
            unsafe_export=unsafe_export,
            **{"password": password},
        )
        return {"path": result.path, "count": result.exported}

    def list_wallets(limit: int = 20) -> dict[str, Any]:
        rows = store.list_wallets(limit=limit)
        return {"wallets": [{"id": row.id, "address": row.address} for row in rows]}

    def doctor() -> dict[str, Any]:
        checks = Doctor().run()
        return {"checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks]}

    def config_get(key: str = "") -> dict[str, Any]:
        cfg = load_config().model_dump()
        if key:
            return {"key": key, "value": cfg.get(key)}
        return cfg

    def config_set(key: str, value: str) -> dict[str, Any]:
        target = config_path()
        cfg = load_config().model_dump()
        cfg[key] = value
        target.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        return {"updated": key, "value": value}

    return SafeToolRouter(
        {
            "generate_wallets": generate_wallets,
            "export_wallets": export_wallets,
            "list_wallets": list_wallets,
            "doctor": doctor,
            "config_get": config_get,
            "config_set": config_set,
        }
    )


@app.command("ai")
def ai_command(db: Optional[str] = typer.Option(None), dry_run: bool = typer.Option(False)) -> None:
    """Interactive AI chat mode with safe tool routing."""
    session = PromptSession("papa-ai> ")
    router = _router(db)
    store = _storage(db)
    console.print("[bold cyan]Papa AI mode. Type 'exit' to quit.[/bold cyan]")
    while True:
        prompt = session.prompt()
        if prompt.strip().lower() in {"exit", "quit"}:
            break
        try:
            parsed = router.parse(prompt, use_llm=True)
            console.print(f"[yellow]Tool:[/yellow] {parsed.tool} [yellow]Args:[/yellow] {parsed.args}")
            result = router.execute(
                parsed,
                dry_run=dry_run,
                confirm=lambda msg: typer.confirm(msg, default=False),
            )
            store.log_command("ai", prompt, parsed.tool, "success")
            console.print_json(json.dumps(result.output, default=str))
        except Exception as exc:
            store.log_command("ai", prompt, None, "failed")
            logger.error("ai_command_failed %s", exc)
            console.print(f"[red]{exc}[/red]")


@app.command("send")
def send_command(
    from_wallet: str = typer.Option(..., "--from", help="Wallet id/address from DB"),
    to: str = typer.Option(..., "--to", help="Destination wallet address"),
    amount: str = typer.Option(..., help="Amount like 1wei, 1gwei, 0.1ether"),
    chain: Optional[str] = typer.Option(None, help="Network key from config"),
    gas_limit: Optional[int] = typer.Option(None),
    gas_price_wei: Optional[int] = typer.Option(None),
    nonce: Optional[int] = typer.Option(None),
    db: Optional[str] = typer.Option(None),
) -> None:
    """Send native token transaction."""
    settings = load_settings()
    selected_chain = chain or settings["default_chain"]

    _, _, tx_sender, _ = _legacy_services(db)
    result = tx_sender.send_native(
        from_wallet=from_wallet,
        to_address=to,
        amount=amount,
        chain_key=selected_chain,
        gas_limit=gas_limit,
        gas_price_wei=gas_price_wei,
        nonce=nonce,
    )

    console.print(f"[green]Transaction sent[/green] {result.tx_hash}")
    console.print(f"Explorer: {result.explorer_url}")


@app.command("balance")
def balance_command(
    wallet: str = typer.Option(..., help="Wallet id/address"),
    chain: Optional[str] = typer.Option(None),
    db: Optional[str] = typer.Option(None),
) -> None:
    """Check native balance for a wallet."""
    settings = load_settings()
    selected_chain = chain or settings["default_chain"]
    _, _, _, balances = _legacy_services(db)
    result = balances.get_wallet_balance(wallet, selected_chain)

    table = Table(title="Balance")
    table.add_column("Wallet ID")
    table.add_column("Address")
    table.add_column("Chain")
    table.add_column("Balance")
    table.add_row(str(result.wallet_id), result.address, result.chain, result.formatted)
    console.print(table)


@app.command("tx-history")
def tx_history_command(
    limit: int = typer.Option(20, min=1, max=500),
    db: Optional[str] = typer.Option(None),
) -> None:
    """Show recent transaction history from SQLite."""
    dbm, _, _, _ = _legacy_services(db)
    rows = dbm.list_transactions(limit=limit)

    table = Table(title="Transaction History")
    table.add_column("Tx Hash")
    table.add_column("From")
    table.add_column("To")
    table.add_column("Amount")
    table.add_column("Chain")
    table.add_column("Status")
    table.add_column("Gas")
    table.add_column("Time")

    for row in rows:
        table.add_row(
            row["tx_hash"],
            row["sender"],
            row["receiver"],
            row["amount_display"],
            row["chain"],
            row["status"],
            str(row["gas_used"] or "-"),
            row["created_at"],
        )
    console.print(table)


@app.command("batch-send")
def batch_send_command(
    count: int = typer.Option(..., min=1, help="Number of transfers"),
    to: str = typer.Option(..., "--to", help="Destination address"),
    amount: str = typer.Option(...),
    chain: Optional[str] = typer.Option(None),
    random_wallet: bool = typer.Option(True, help="Randomly choose sender wallets"),
    tag: Optional[str] = typer.Option(None, help="Filter sender wallets by tag"),
    db: Optional[str] = typer.Option(None),
) -> None:
    """Send repeated transfers across multiple DB wallets."""
    import secrets

    settings = load_settings()
    selected_chain = chain or settings["default_chain"]
    dbm, _, tx_sender, _ = _legacy_services(db)

    fetch_limit = 500 if random_wallet else max(count, 1)
    wallets = dbm.list_wallets(limit=fetch_limit, tag=tag)
    if not wallets:
        raise typer.BadParameter("No wallets available for batch send")

    for i in range(count):
        sender_id = secrets.choice(wallets)["id"] if random_wallet else wallets[i % len(wallets)]["id"]
        result = tx_sender.send_native(
            from_wallet=str(sender_id),
            to_address=to,
            amount=amount,
            chain_key=selected_chain,
        )
        console.print(f"[{i + 1}/{count}] {result.tx_hash} -> {result.explorer_url}")


@networks_app.command("list")
def networks_list(db: Optional[str] = typer.Option(None)) -> None:
    """List active networks."""
    _, chains, _, _ = _legacy_services(db)
    table = Table(title="Networks")
    table.add_column("Key")
    table.add_column("Name")
    table.add_column("RPC")
    table.add_column("Chain ID")
    table.add_column("Token")

    for cfg in chains.list():
        table.add_row(cfg.key, cfg.name, cfg.rpc_url, str(cfg.chain_id), cfg.native_token)
    console.print(table)


@networks_app.command("add")
def networks_add(
    key: str,
    name: str,
    rpc_url: str,
    explorer: str,
    native_token: str,
    decimals: int,
    chain_id: int,
    db: Optional[str] = typer.Option(None),
) -> None:
    """Add or update a network config."""
    _, chains, _, _ = _legacy_services(db)
    chains.add(
        key,
        {
            "name": name,
            "rpc_url": rpc_url,
            "explorer": explorer,
            "native_token": native_token,
            "decimals": decimals,
            "chain_id": chain_id,
        },
    )
    console.print(f"[green]Network '{key}' saved[/green]")


@networks_app.command("remove")
def networks_remove(key: str, db: Optional[str] = typer.Option(None)) -> None:
    """Deactivate a network config."""
    _, chains, _, _ = _legacy_services(db)
    chains.remove(key)
    console.print(f"[yellow]Network '{key}' removed[/yellow]")


@config_app.command("show")
def config_show() -> None:
    console.print_json(json.dumps(load_config().model_dump()))


@config_app.command("get")
def config_get(key: str) -> None:
    cfg = load_config().model_dump()
    console.print_json(json.dumps({key: cfg.get(key)}))


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    cfg_file = config_path()
    existing = load_config().model_dump()
    existing[key] = value
    cfg_file.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
    console.print(f"[green]Updated {key}[/green]")


@app.command("init")
def init_command() -> None:
    """Initialize app database/folders."""
    cfg = load_config()
    Path(cfg.logging.directory).mkdir(parents=True, exist_ok=True)
    Path(cfg.config_dir).mkdir(parents=True, exist_ok=True)
    DatabaseBootstrap().initialize()
    console.print("[green]Initialization complete[/green]")


if __name__ == "__main__":
    app()
