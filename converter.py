#!/usr/bin/env python3
"""Backward-compatible export wrapper."""

import argparse
from getpass import getpass

from project.config.settings import ensure_config
from project.wallet.exporter import WalletExporter
from project.wallet.storage import WalletStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export wallet data")
    parser.add_argument("--db", type=str, default="wallets.db")
    parser.add_argument("--format", type=str, default="json", choices=["txt", "json", "csv"])
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--unsafe-export", action="store_true")
    parser.add_argument("--password", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = ensure_config(__import__("pathlib").Path("config/config.yaml"))
    password = args.password or getpass("Encryption password: ")

    storage = WalletStorage(args.db, password, iterations=int(cfg["encryption"]["kdf_iterations"]))
    storage.initialize()
    exporter = WalletExporter(storage, cfg["export"]["directory"])

    path = exporter.export(
        fmt=args.format,
        output=args.output,
        limit=args.limit,
        offset=args.offset,
        unsafe_export=args.unsafe_export,
    )
    if not args.quiet:
        print(f"Exported wallets to {path}")


if __name__ == "__main__":
    main()
