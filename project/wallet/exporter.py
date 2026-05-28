from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from eth_account import Account

from project.logging_utils import get_logger
from project.wallet.storage import WalletStorage


@dataclass(slots=True)
class ExportResult:
    path: str
    exported: int
    format: str


class WalletExporter:
    SUPPORTED_FORMATS = {"csv", "json", "txt", "keystore"}

    def __init__(self, storage: Optional[WalletStorage] = None):
        self.storage = storage or WalletStorage()
        self.logger = get_logger("wallet_exporter", "export.log")

    def export(
        self,
        fmt: str,
        output: str,
        limit: Optional[int] = None,
        offset: int = 0,
        unsafe_export: bool = False,
        password: Optional[str] = None,
    ) -> ExportResult:
        fmt = fmt.lower()
        if fmt not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {fmt}")

        rows = self.storage.export_rows(limit=limit, offset=offset)
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)

        if fmt in {"csv", "json", "txt"} and not unsafe_export:
            rows_payload = [{"id": r.id, "address": r.address} for r in rows]
        else:
            if fmt != "keystore":
                if not password:
                    raise ValueError("Password required when exporting private keys")
            rows_payload = []
            for row in rows:
                private_key = self.storage.resolve_private_key(row, **{"password": password})
                record = {"id": row.id, "address": row.address, "private_key": private_key}
                rows_payload.append(record)

        if fmt == "csv":
            with out.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows_payload[0].keys()) if rows_payload else ["id", "address"])
                writer.writeheader()
                writer.writerows(rows_payload)
        elif fmt == "json":
            out.write_text(json.dumps(rows_payload, indent=2), encoding="utf-8")
        elif fmt == "txt":
            lines = []
            if rows_payload and "private_key" in rows_payload[0]:
                lines = [f"{row['id']}|{row['address']}|{row['private_key']}" for row in rows_payload]
            else:
                lines = [f"{row['id']}|{row['address']}" for row in rows_payload]
            out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        elif fmt == "keystore":
            if not password:
                raise ValueError("Password required for keystore export")
            payload = []
            for row in rows:
                private_key = self.storage.resolve_private_key(row, **{"password": password})
                encrypted = Account.encrypt(private_key, password)
                payload.append({"id": row.id, "address": row.address, "keystore": encrypted})
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        self.logger.info("export_complete format=%s rows=%s output=%s unsafe=%s", fmt, len(rows), output, unsafe_export)
        return ExportResult(path=str(out), exported=len(rows), format=fmt)
