from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from project.wallet.storage import WalletStorage


@dataclass(slots=True)
class DatabaseHealth:
    connected: bool
    message: str


class DatabaseBootstrap:
    def __init__(self):
        self.storage = WalletStorage()

    def initialize(self) -> None:
        self.storage.ensure_schema()

    def health(self) -> DatabaseHealth:
        try:
            self.storage.ensure_schema()
            _ = self.storage.total_wallets()
            return DatabaseHealth(True, "database ok")
        except Exception as exc:
            return DatabaseHealth(False, str(exc))

    def stats(self) -> Dict[str, int]:
        self.storage.ensure_schema()
        return {"wallets": self.storage.total_wallets()}
