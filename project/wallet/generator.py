from __future__ import annotations

import secrets
from typing import Tuple

from eth_account import Account


def generate_wallet() -> Tuple[str, str]:
    random_bytes = secrets.token_bytes(32)
    account = Account.from_key(random_bytes)
    return account.address, account.key.hex()
