from __future__ import annotations

from typing import Any

from project.ai.router import ToolRouter
from project.wallet.exporter import WalletExporter
from project.wallet.generator import generate_wallet
from project.wallet.storage import WalletStorage


def build_router(storage: WalletStorage, exporter: WalletExporter, doctor_handler) -> ToolRouter:
    router = ToolRouter()

    def generate_wallets(count: int = 1) -> dict[str, Any]:
        inserted = 0
        for _ in range(int(count)):
            address, private_key = generate_wallet()
            storage.add_wallet(address, private_key)
            inserted += 1
        return {"generated": inserted, "total": storage.count_wallets()}

    def export_wallets(format: str = "json", unsafe_export: bool = False) -> dict[str, Any]:
        path = exporter.export(fmt=format, unsafe_export=unsafe_export)
        return {"exported_to": path, "unsafe_export": unsafe_export}

    def list_wallets(limit: int = 20, offset: int = 0) -> dict[str, Any]:
        rows = storage.list_wallets(limit=limit, offset=offset)
        return {
            "wallets": [{"id": w.id, "address": w.address} for w in rows],
            "count": len(rows),
        }

    router.register("generate_wallets", generate_wallets)
    router.register("export_wallets", export_wallets, dangerous=True)
    router.register("list_wallets", list_wallets)
    router.register("doctor", lambda: doctor_handler())
    return router
