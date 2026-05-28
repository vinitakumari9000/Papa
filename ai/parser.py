"""Compatibility shim for AI parser."""

from project.ai.parser import ParsedToolCall, parse_prompt_or_json as parse_prompt

__all__ = ["ParsedToolCall", "parse_prompt"]
