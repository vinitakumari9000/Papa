from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from eth_account import Account

from project.config import load_config
from project.logging_utils import get_logger
from project.wallet.encryption import decrypt_secret, encrypt_secret, is_encrypted_payload


@dataclass(slots=True)
class WalletRow:
    id: int
    address: str
    private_key: str


class WalletStorage:
    def __init__(self, db_path: Optional[str] = None):
        cfg = load_config()
        self.db_path = Path(db_path or cfg.database_path)
        self.logger = get_logger("wallet_storage", "wallet.log")

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS wallets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    address TEXT NOT NULL UNIQUE,
                    private_key TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS command_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    command_text TEXT NOT NULL,
                    tool_name TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS balance_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet_id INTEGER NOT NULL,
                    chain_key TEXT NOT NULL,
                    balance_wei TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(wallet_id) REFERENCES wallets(id)
                )
                """
            )
            conn.commit()

    def insert_wallet(self, address: str, private_key: str, password: Optional[str] = None) -> int:
        value = private_key
        if password:
            value = encrypt_secret(private_key, password)
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO wallets(address, private_key) VALUES(?, ?)",
                (address, value),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_wallets(self, limit: int = 50) -> List[WalletRow]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, address, private_key FROM wallets ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [WalletRow(id=row["id"], address=row["address"], private_key=row["private_key"]) for row in rows]

    def total_wallets(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) as c FROM wallets").fetchone()
            return int(row["c"])

    def _maybe_decrypt_keystore(self, value: str, password: Optional[str]) -> str:
        stripped = value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            payload = json.loads(stripped)
            if payload.get("crypto") and password:
                key_bytes = Account.decrypt(payload, password)
                return f"0x{key_bytes.hex()}"
        return value

    def resolve_private_key(self, row: WalletRow, password: Optional[str]) -> str:
        value = row.private_key.strip()
        if is_encrypted_payload(value):
            if not password:
                raise ValueError("Wallet is encrypted; provide password")
            return decrypt_secret(value, password)
        return self._maybe_decrypt_keystore(value, password)

    def migrate_plaintext(self, password: str, limit: int = 1000) -> int:
        changed = 0
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, private_key FROM wallets ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            for row in rows:
                current = row["private_key"]
                if is_encrypted_payload(current):
                    continue
                if current.strip().startswith("{"):
                    continue
                encrypted = encrypt_secret(current, password)
                conn.execute("UPDATE wallets SET private_key = ? WHERE id = ?", (encrypted, row["id"]))
                changed += 1
            conn.commit()
        return changed

    def export_rows(self, limit: Optional[int] = None, offset: int = 0) -> List[WalletRow]:
        sql = "SELECT id, address, private_key FROM wallets ORDER BY id ASC LIMIT ? OFFSET ?"
        limit_value = limit if limit is not None else 10**12
        with self.connect() as conn:
            rows = conn.execute(sql, (limit_value, offset)).fetchall()
        return [WalletRow(id=row["id"], address=row["address"], private_key=row["private_key"]) for row in rows]

    def log_command(self, source: str, command_text: str, tool_name: Optional[str], status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO command_history(source, command_text, tool_name, status) VALUES (?, ?, ?, ?)",
                (source, command_text, tool_name, status),
            )
            conn.commit()
