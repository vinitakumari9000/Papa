from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class ParsedToolCall:
    tool: str
    args: Dict[str, Any]


_ALLOWED_TOOLS = {
    "generate_wallets",
    "export_wallets",
    "list_wallets",
    "doctor",
    "config_get",
    "config_set",
}


def _heuristic_parse(prompt: str) -> ParsedToolCall | None:
    low = prompt.lower()
    m = re.search(r"generate\s+(\d+)\s+wallet", low)
    if m:
        count = int(m.group(1))
        export = "csv" if "csv" in low else ("json" if "json" in low else None)
        return ParsedToolCall(tool="generate_wallets", args={"count": count, "export": export})

    if "list" in low and "wallet" in low:
        return ParsedToolCall(tool="list_wallets", args={"limit": 20})

    if "doctor" in low or "health" in low:
        return ParsedToolCall(tool="doctor", args={})

    if "export" in low:
        fmt = "csv" if "csv" in low else "json"
        return ParsedToolCall(tool="export_wallets", args={"format": fmt})

    return None


def parse_tool_json(text: str) -> ParsedToolCall:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("LLM output must be JSON object")
    tool = parsed.get("tool")
    args = parsed.get("args", {})
    if tool not in _ALLOWED_TOOLS:
        raise ValueError(f"tool '{tool}' is not allowed")
    if not isinstance(args, dict):
        raise ValueError("args must be an object")
    return ParsedToolCall(tool=tool, args=args)


def parse_prompt_or_json(text: str) -> ParsedToolCall:
    text = text.strip()
    if text.startswith("{"):
        return parse_tool_json(text)
    parsed = _heuristic_parse(text)
    if parsed:
        return parsed
    raise ValueError("Could not parse request safely")
