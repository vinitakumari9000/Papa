from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from project.ai.llm import OllamaClient
from project.ai.parser import ParsedToolCall, parse_prompt_or_json
from project.ai.prompts import SYSTEM_PROMPT
from project.ai.tools import ToolRegistry, ToolSpec
from project.logging_utils import audit_event, get_logger


@dataclass(slots=True)
class RouteResult:
    tool: str
    args: Dict[str, Any]
    output: Any


class SafeToolRouter:
    def __init__(self, handlers: Dict[str, Callable[..., Any]]):
        self.logger = get_logger("ai_router", "ai.log")
        self.ollama = OllamaClient()
        self.registry = ToolRegistry(
            ToolSpec(name=name, handler=handler, dangerous=name in {"config_set"}, requires_confirmation=name in {"config_set"})
            for name, handler in handlers.items()
        )

    def parse(self, prompt: str, use_llm: bool = True) -> ParsedToolCall:
        audit_event(self.logger, "ai_prompt_received", prompt=prompt)
        parsed = None
        if use_llm:
            try:
                raw = self.ollama.generate(SYSTEM_PROMPT, prompt)
                parsed = parse_prompt_or_json(raw)
            except Exception:
                parsed = parse_prompt_or_json(prompt)
        else:
            parsed = parse_prompt_or_json(prompt)
        audit_event(self.logger, "ai_prompt_parsed", tool=parsed.tool, args=parsed.args)
        return parsed

    def execute(
        self,
        parsed: ParsedToolCall,
        dry_run: bool = False,
        confirm: Optional[Callable[[str], bool]] = None,
    ) -> RouteResult:
        tool = self.registry.get(parsed.tool)
        if dry_run:
            audit_event(self.logger, "ai_dry_run", tool=tool.name, args=parsed.args)
            return RouteResult(tool=tool.name, args=parsed.args, output={"dry_run": True})

        if tool.requires_confirmation:
            allowed = confirm(f"Confirm execution of {tool.name}?") if confirm else False
            if not allowed:
                audit_event(self.logger, "ai_confirm_denied", tool=tool.name)
                raise PermissionError(f"Execution denied for {tool.name}")
            audit_event(self.logger, "ai_confirm_granted", tool=tool.name)

        result = tool.handler(**parsed.args)
        audit_event(self.logger, "ai_execute_success", tool=tool.name)
        return RouteResult(tool=tool.name, args=parsed.args, output=result)
