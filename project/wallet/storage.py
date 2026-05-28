from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from project.database.models import Base, Wallet
from project.wallet.encryption import decrypt_private_key, encrypt_private_key


@dataclass
class WalletRecord:
    id: int
    address: str
    encrypted_private_key: str | None
    salt: str | None
    nonce: str | None


class WalletStorage:
    def __init__(self, db_path: str, password: str, iterations: int = 250000):
        self.db_path = Path(db_path)
        self.password = password
        self.iterations = iterations
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.session_factory = sessionmaker(bind=self.engine)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        self._ensure_columns()
        self._migrate_legacy_private_keys()

    def _ensure_columns(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(wallets)")
        columns = {row[1] for row in cur.fetchall()}
        if "encrypted_private_key" not in columns:
            cur.execute("ALTER TABLE wallets ADD COLUMN encrypted_private_key TEXT")
        if "salt" not in columns:
            cur.execute("ALTER TABLE wallets ADD COLUMN salt TEXT")
        if "nonce" not in columns:
            cur.execute("ALTER TABLE wallets ADD COLUMN nonce TEXT")
        if "private_key" not in columns:
            cur.execute("ALTER TABLE wallets ADD COLUMN private_key TEXT")
        if "created_at" not in columns:
            cur.execute("ALTER TABLE wallets ADD COLUMN created_at TEXT")
        conn.commit()
        conn.close()

    def _migrate_legacy_private_keys(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, private_key FROM wallets WHERE private_key IS NOT NULL AND (encrypted_private_key IS NULL OR encrypted_private_key='')"
        )
        rows = cur.fetchall()
        for wallet_id, plain_private_key in rows:
            payload = encrypt_private_key(plain_private_key, self.password, self.iterations)
            cur.execute(
                "UPDATE wallets SET encrypted_private_key=?, salt=?, nonce=?, private_key=NULL WHERE id=?",
                (payload.ciphertext, payload.salt, payload.nonce, wallet_id),
            )
        conn.commit()
        conn.close()

    def add_wallet(self, address: str, private_key: str) -> int:
        payload = encrypt_private_key(private_key, self.password, self.iterations)
        with self.session_factory() as session:
            wallet = Wallet(
                address=address,
                encrypted_private_key=payload.ciphertext,
                salt=payload.salt,
                nonce=payload.nonce,
                private_key=None,
            )
            session.add(wallet)
            session.commit()
            session.refresh(wallet)
            return wallet.id

    def list_wallets(self, limit: int = 20, offset: int = 0) -> List[WalletRecord]:
        with self.session_factory() as session:
            rows = session.scalars(select(Wallet).order_by(Wallet.id).limit(limit).offset(offset)).all()
            return [
                WalletRecord(
                    id=row.id,
                    address=row.address,
                    encrypted_private_key=row.encrypted_private_key,
                    salt=row.salt,
                    nonce=row.nonce,
                )
                for row in rows
            ]

    def count_wallets(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wallets")
            return int(cur.fetchone()[0])

    def export_rows(self, limit: Optional[int] = None, offset: int = 0, unsafe: bool = False) -> list[dict]:
        with self.session_factory() as session:
            query = select(Wallet).order_by(Wallet.id).offset(offset)
            if limit is not None:
                query = query.limit(limit)
            rows = session.scalars(query).all()
            out: list[dict] = []
            for row in rows:
                payload = {
                    "id": row.id,
                    "address": row.address,
                    "encrypted_private_key": row.encrypted_private_key,
                    "salt": row.salt,
                    "nonce": row.nonce,
                }
                if unsafe and row.encrypted_private_key and row.salt and row.nonce:
                    payload["private_key"] = decrypt_private_key(
                        row.encrypted_private_key,
                        row.salt,
                        row.nonce,
                        self.password,
                        self.iterations,
                    )
                out.append(payload)
            return out
