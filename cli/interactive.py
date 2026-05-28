"""Interactive AI session hooks with optional prompt-toolkit input and Rich rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from rich.console import Console
from rich.panel import Panel

from ai.router import route_prompt


@dataclass(slots=True)
class InteractiveHooks:
    """Runtime hooks for extensible interactive session behavior."""

    render_response: Callable[[str], None]
    on_prompt: Callable[[str], Optional[str]]


def _default_prompt() -> str:
    try:
        from prompt_toolkit import prompt

        return prompt("papa ai> ")
    except Exception:
        return input("papa ai> ")


def _default_hooks(console: Console) -> InteractiveHooks:
    def render_response(message: str) -> None:
        console.print(Panel(message, title="AI", border_style="cyan"))

    def on_prompt(raw: str) -> Optional[str]:
        text = raw.strip()
        return text or None

    return InteractiveHooks(render_response=render_response, on_prompt=on_prompt)


def run_interactive_session(console: Console, hooks: InteractiveHooks | None = None) -> None:
    """Run persistent AI loop; exits on quit/exit."""
    session_hooks = hooks or _default_hooks(console)
    console.print("[bold cyan]Papa AI interactive session[/bold cyan] (type 'exit' to quit)")

    while True:
        raw = _default_prompt()
        prompt = session_hooks.on_prompt(raw)
        if prompt is None:
            continue
        if prompt.lower() in {"exit", "quit"}:
            console.print("[yellow]Exiting AI session[/yellow]")
            break

        tool_call = route_prompt(prompt)
        if tool_call is None:
            session_hooks.render_response("I couldn't map that request to a supported tool yet.")
            continue

        session_hooks.render_response(f"Tool: {tool_call.tool}\nArgs: {tool_call.args}")
