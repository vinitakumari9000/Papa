#!/usr/bin/env python3
"""Backward-compatible wallet generation wrapper."""

import argparse
from getpass import getpass

from project.config.settings import ensure_config
from project.wallet.generator import generate_wallet
from project.wallet.storage import WalletStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate wallets and store them in SQLite")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=0)
    parser.add_argument("--db", type=str, default="wallets.db")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--password", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = ensure_config(__import__("pathlib").Path("config/config.yaml"))
    password = args.password or getpass("Encryption password: ")
    storage = WalletStorage(args.db, password, iterations=int(cfg["encryption"]["kdf_iterations"]))
    storage.initialize()

    for _ in range(args.count):
        address, private_key = generate_wallet()
        storage.add_wallet(address, private_key)

    if not args.quiet:
        print(f"Generated {args.count} wallets. Total in DB: {storage.count_wallets()}")


if __name__ == "__main__":
    main()
