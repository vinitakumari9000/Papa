"""Database migration helpers for legacy/plaintext wallet schemas."""

from project.wallet.storage import WalletStorage


def run_migrations(storage: WalletStorage) -> None:
    storage.initialize()
