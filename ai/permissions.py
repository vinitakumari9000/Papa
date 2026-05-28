"""Permission policy enforcement for AI-routed tool actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class PermissionLevel(str, Enum):
    """Permission requirements for tool actions."""

    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """Result of evaluating a tool action against the permission policy."""

    allowed: bool
    level: PermissionLevel
    action: str
    reason: str
    requires_confirmation: bool = False

    def to_payload(self) -> dict[str, Any]:
        """Return a structured payload suitable for router responses."""
        return {
            "allowed": self.allowed,
            "level": self.level.value,
            "action": self.action,
            "reason": self.reason,
            "requires_confirmation": self.requires_confirmation,
        }


# Tool/action policy table. Key format: "<tool>:<action>".
POLICY_BY_ACTION: dict[str, PermissionLevel] = {
    # High-risk confirmations.
    "send_transaction:send_tx": PermissionLevel.CONFIRM,
    "wallet_export:export_keys": PermissionLevel.CONFIRM,
    "database:insert": PermissionLevel.CONFIRM,
    "database:update": PermissionLevel.CONFIRM,
    "database:delete": PermissionLevel.CONFIRM,
    "file:overwrite": PermissionLevel.CONFIRM,
    # Explicitly blocked arbitrary code execution categories.
    "shell:exec": PermissionLevel.DENY,
    "shell:subprocess": PermissionLevel.DENY,
    "shell:arbitrary_command": PermissionLevel.DENY,
}


def resolve_action(tool: str, args: Mapping[str, Any]) -> str:
    """Resolve a normalized action key from tool name and arguments."""
    if tool == "send_transaction":
        return "send_tx"

    action = str(args.get("action", "")).strip().lower().replace(" ", "_")
    if action:
        return action

    if tool == "file" and bool(args.get("overwrite")):
        return "overwrite"

    return "default"


def evaluate_permission(
    tool: str,
    args: Mapping[str, Any],
    *,
    confirmation_token: str | None = None,
) -> PermissionDecision:
    """Evaluate whether a tool invocation should be allowed."""
    action = resolve_action(tool, args)
    policy_key = f"{tool}:{action}"
    level = POLICY_BY_ACTION.get(policy_key, PermissionLevel.ALLOW)

    if level == PermissionLevel.DENY:
        reason = f"Action '{policy_key}' is blocked by policy"
        logger.warning("permission_denied tool=%s action=%s", tool, action)
        return PermissionDecision(False, level, action, reason, requires_confirmation=False)

    if level == PermissionLevel.CONFIRM:
        is_confirmed = bool(confirmation_token and confirmation_token.strip())
        logger.info(
            "permission_confirmation tool=%s action=%s confirmed=%s",
            tool,
            action,
            is_confirmed,
        )
        if not is_confirmed:
            return PermissionDecision(
                False,
                level,
                action,
                f"Action '{policy_key}' requires a confirmation token",
                requires_confirmation=True,
            )

    logger.info("permission_allowed tool=%s action=%s level=%s", tool, action, level.value)
    return PermissionDecision(True, level, action, "Allowed by policy", requires_confirmation=False)
