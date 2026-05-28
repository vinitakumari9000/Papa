"""AI router placeholder for future execution orchestration."""

from __future__ import annotations

from typing import Optional

from ai.parser import parse_prompt
from ai.tools import ToolCall
from utils.helpers import setup_rotating_logger
from utils.secrets import redact_text

_AUDIT_LOGGER = setup_rotating_logger("ai_audit", "ai_audit.log")


def route_prompt(prompt: str) -> Optional[ToolCall]:
    """Return parsed tool call for future AI engine routing."""
    _AUDIT_LOGGER.info("ai_prompt_received prompt=%s", redact_text(prompt))
    tool_call = parse_prompt(prompt)
    _AUDIT_LOGGER.info("ai_prompt_routed matched=%s", bool(tool_call))
    return tool_call
