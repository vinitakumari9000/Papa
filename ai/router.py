"""AI router and guarded execution path."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from ai.parser import parse_prompt
from ai.permissions import PermissionDecision, evaluate_permission
from ai.tools import ToolCall

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RouterExecutionResult:
    """Structured response returned from tool execution attempts."""

    ok: bool
    status: str
    tool: str | None
    payload: dict[str, Any]


def route_prompt(prompt: str) -> Optional[ToolCall]:
    """Return parsed tool call for future AI engine routing."""
    return parse_prompt(prompt)


def execute_tool_call(
    tool_call: ToolCall,
    *,
    confirmation_token: str | None = None,
) -> RouterExecutionResult:
    """Validate a parsed tool call with policy checks before execution."""
    decision = evaluate_permission(
        tool_call.tool,
        tool_call.args,
        confirmation_token=confirmation_token,
    )
    _audit_permission(tool_call, decision)

    if not decision.allowed:
        return _denied_response(tool_call, decision)

    # Placeholder execution for future engine integration.
    return RouterExecutionResult(
        ok=True,
        status="allowed",
        tool=tool_call.tool,
        payload={
            "tool": tool_call.tool,
            "args": tool_call.args,
            "permission": decision.to_payload(),
            "message": "Tool call authorized for execution",
        },
    )


def _denied_response(tool_call: ToolCall, decision: PermissionDecision) -> RouterExecutionResult:
    status = "needs_confirmation" if decision.requires_confirmation else "denied"
    logger.warning(
        "tool_call_blocked tool=%s action=%s status=%s",
        tool_call.tool,
        decision.action,
        status,
    )
    return RouterExecutionResult(
        ok=False,
        status=status,
        tool=tool_call.tool,
        payload={
            "error": "permission_denied",
            "tool": tool_call.tool,
            "args": tool_call.args,
            "permission": decision.to_payload(),
        },
    )


def _audit_permission(tool_call: ToolCall, decision: PermissionDecision) -> None:
    """Write security audit logs for permission flow (without sensitive values)."""
    arg_keys = sorted(tool_call.args.keys())
    logger.info(
        "audit_permission_decision tool=%s action=%s allowed=%s level=%s arg_keys=%s",
        tool_call.tool,
        decision.action,
        decision.allowed,
        decision.level.value,
        ",".join(arg_keys),
    )
