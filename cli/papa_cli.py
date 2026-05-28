#!/usr/bin/env python3
"""Typer CLI for modular multi-chain wallet orchestration."""

from __future__ import annotations

import secrets
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from utils.helpers import load_settings
from wallet.balance import BalanceService
from wallet.chains import ChainRegistry
from wallet.database import DatabaseManager
from wallet.tx_sender import TransactionSender

app = typer.Typer(help="Papa multi-chain wallet CLI")
networks_app = typer.Typer(help="Network management commands")
app.add_typer(networks_app, name="networks")
console = Console()


def _services(db_path: Optional[str] = None) -> tuple[DatabaseManager, ChainRegistry, TransactionSender, BalanceService]:
    db = DatabaseManager(db_path=db_path)
    db.migrate()
    return db, ChainRegistry(db), TransactionSender(db), BalanceService(db)


@app.command("wallets")
def wallets_command(
    limit: int = typer.Option(20, min=1, max=500),
    tag: Optional[str] = typer.Option(None),
    db: Optional[str] = typer.Option(None),
) -> None:
    """List wallets from the database."""
    dbm, _, _, _ = _services(db)
    rows = dbm.list_wallets(limit=limit, tag=tag)

    table = Table(title="Wallets")
    table.add_column("ID")
    table.add_column("Address")
    for row in rows:
        table.add_row(str(row["id"]), row["address"])
    console.print(table)


@app.command("send")
def send_command(
    from_wallet: str = typer.Option(..., "--from", help="Wallet ref: id, address, or tag:<name>"),
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

    _, _, tx_sender, _ = _services(db)
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
    wallet: str = typer.Option(..., help="Wallet ref: id, address, or tag:<name>"),
    chain: Optional[str] = typer.Option(None),
    db: Optional[str] = typer.Option(None),
) -> None:
    """Check native balance for a wallet."""
    settings = load_settings()
    selected_chain = chain or settings["default_chain"]
    _, _, _, balances = _services(db)
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
    dbm, _, _, _ = _services(db)
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
    settings = load_settings()
    selected_chain = chain or settings["default_chain"]
    dbm, _, tx_sender, _ = _services(db)

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
    _, chains, _, _ = _services(db)
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
    _, chains, _, _ = _services(db)
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
    _, chains, _, _ = _services(db)
    chains.remove(key)
    console.print(f"[yellow]Network '{key}' removed[/yellow]")


if __name__ == "__main__":
    app()
