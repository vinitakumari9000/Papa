from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ToolCall:
    tool: str
    args: Dict[str, Any]


def parse_tool_call(raw: str) -> ToolCall:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("Tool call must be a JSON object")

    tool = payload.get("tool")
    args = payload.get("args", {})

    if not isinstance(tool, str) or not tool:
        raise ValueError("Missing tool in LLM response")
    if not isinstance(args, dict):
        raise ValueError("Tool args must be an object")

    return ToolCall(tool=tool, args=args)
