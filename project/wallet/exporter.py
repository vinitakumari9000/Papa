from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from project.wallet.storage import WalletStorage


class WalletExporter:
    def __init__(self, storage: WalletStorage, export_dir: str = "exports"):
        self.storage = storage
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export(self, fmt: str, output: Optional[str] = None, limit: Optional[int] = None, offset: int = 0, unsafe_export: bool = False) -> str:
        rows = self.storage.export_rows(limit=limit, offset=offset, unsafe=unsafe_export)
        file_name = output or f"wallets_export.{fmt}"
        path = self.export_dir / file_name

        if fmt == "json":
            path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        elif fmt == "csv":
            with path.open("w", newline="", encoding="utf-8") as f:
                fieldnames = ["id", "address", "encrypted_private_key", "salt", "nonce"]
                if unsafe_export:
                    fieldnames.append("private_key")
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
        elif fmt == "txt":
            with path.open("w", encoding="utf-8") as f:
                for row in rows:
                    private_repr = row.get("private_key", "<encrypted>")
                    f.write(f"{row['id']}|{row['address']}|{private_repr}\n")
        else:
            raise ValueError(f"Unsupported format: {fmt}")
        return str(path)
