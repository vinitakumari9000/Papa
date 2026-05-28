from __future__ import annotations

import json
import logging
import logging.handlers
from typing import Any, Dict

from project.config import load_config, project_root


def get_logger(name: str, file_name: str) -> logging.Logger:
    cfg = load_config()
    log_dir = project_root() / cfg.logging.directory
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    handler = logging.handlers.RotatingFileHandler(
        log_dir / file_name,
        maxBytes=cfg.logging.max_bytes,
        backupCount=cfg.logging.backup_count,
    )
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    return logger


def audit_event(logger: logging.Logger, event: str, **data: Dict[str, Any]) -> None:
    logger.info("audit=%s payload=%s", event, json.dumps(data, default=str))
