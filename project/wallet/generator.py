from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import List, Optional

from eth_account import Account

from project.logging_utils import get_logger
from project.wallet.storage import WalletStorage


@dataclass(slots=True)
class GeneratedWallet:
    id: int
    address: str


class WalletGeneratorService:
    def __init__(self, storage: Optional[WalletStorage] = None):
        self.storage = storage or WalletStorage()
        self.logger = get_logger("wallet_generator_service", "wallet.log")

    def generate_one(self, password: Optional[str] = None) -> GeneratedWallet:
        random_bytes = secrets.token_bytes(32)
        account = Account.from_key(random_bytes)
        wallet_id = self.storage.insert_wallet(account.address, account.key.hex(), password)
        self.logger.info("generated_wallet address=%s", account.address)
        return GeneratedWallet(id=wallet_id, address=account.address)

    def generate_many(self, count: int, password: Optional[str] = None) -> List[GeneratedWallet]:
        if count <= 0:
            raise ValueError("count must be > 0")
        return [self.generate_one(**{"password": password}) for _ in range(count)]
