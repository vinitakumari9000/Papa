from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable


@dataclass(slots=True)
class ToolSpec:
    name: str
    handler: Callable[..., Any]
    dangerous: bool = False
    requires_confirmation: bool = False


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec]):
        self._tools: Dict[str, ToolSpec] = {s.name: s for s in specs}

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise ValueError(f"Unregistered tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools.keys())
