from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


class RouterError(Exception):
    pass


@dataclass
class ToolSpec:
    handler: Callable[..., Any]
    dangerous: bool = False


class ToolRouter:
    def __init__(self):
        self.registry: Dict[str, ToolSpec] = {}

    def register(self, name: str, handler: Callable[..., Any], dangerous: bool = False) -> None:
        self.registry[name] = ToolSpec(handler=handler, dangerous=dangerous)

    def validate(self, tool: str, args: dict) -> None:
        if tool not in self.registry:
            raise RouterError(f"Tool not allowed: {tool}")
        if not isinstance(args, dict):
            raise RouterError("Tool args must be JSON object")

    def execute(self, tool: str, args: dict, *, dry_run: bool = False, confirm: bool = False) -> Any:
        self.validate(tool, args)
        spec = self.registry[tool]
        if spec.dangerous and not (dry_run or confirm):
            raise RouterError("Dangerous tool requires --confirm or --dry-run")
        if dry_run:
            return {"dry_run": True, "tool": tool, "args": args}
        return spec.handler(**args)
