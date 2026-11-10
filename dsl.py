"""Parser for the agent command language."""

from __future__ import annotations

from dataclasses import dataclass
import re
import shlex


class DSLParseError(ValueError):
    """Raised when an LLM response is not valid agent DSL."""


@dataclass(frozen=True)
class Action:
    """One parsed command from the agent's plan."""

    command: str
    args: tuple[str, ...]
    line_number: int
    raw: str

    def display(self) -> str:
        """Return a readable representation for the terminal UI."""

        return shlex.join((self.command, *self.args))


_NON_ACTION_COMMANDS = {"END", "DONE", "PLAN", "REASON", "SUMMARY"}


def _clean_response(text: str) -> str:
    """Remove common model wrappers without changing command contents."""

    cleaned = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    lines = [
        line
        for line in cleaned.splitlines()
        if not line.strip().startswith(chr(96) * 3)
    ]
    return "\n".join(lines).strip()


def parse_dsl(text: str) -> list[Action]:
    """Parse an LLM response into actions.

    Comments and blank lines are ignored. Commands are case-insensitive,
    while arguments preserve their original case.
    """

    if not isinstance(text, str) or not text.strip():
        raise DSLParseError("The LLM returned an empty plan.")

    actions: list[Action] = []
    cleaned = _clean_response(text)

    for line_number, raw_line in enumerate(cleaned.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            parts = shlex.split(line, comments=True, posix=True)
        except ValueError as exc:
            raise DSLParseError(
                f"Line {line_number} has invalid quoting: {exc}"
            ) from exc

        if not parts:
            continue

        command = parts[0].upper()
        if command in _NON_ACTION_COMMANDS:
            continue

        actions.append(
            Action(
                command=command,
                args=tuple(parts[1:]),
                line_number=line_number,
                raw=raw_line,
            )
        )

    if not actions:
        raise DSLParseError(
            "The response contained no executable commands. "
            "Use the documented DSL or ask the user for clarification."
        )

    return actions


def format_actions(actions: list[Action]) -> str:
    """Format parsed actions for the approval preview."""

    return "\n".join(
        f"{index}. {action.display()}"
        for index, action in enumerate(actions, start=1)
    )
