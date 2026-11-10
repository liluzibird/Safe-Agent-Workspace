"""Safety and schema validation for agent actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dsl import Action


class SafetyError(ValueError):
    """Raised when a proposed action is unsafe or malformed."""


@dataclass(frozen=True)
class CommandSpec:
    """Schema and risk classification for one DSL command."""

    minimum_args: int
    maximum_args: int
    risk: str
    description: str


COMMAND_SPECS: dict[str, CommandSpec] = {
    "FILE_LIST": CommandSpec(1, 1, "read", "List workspace entries"),
    "FILE_INFO": CommandSpec(1, 1, "read", "Inspect one workspace path"),
    "FILE_MKDIR": CommandSpec(1, 1, "modify", "Create a workspace folder"),
    "FILE_MOVE": CommandSpec(2, 2, "modify", "Move a workspace path"),
    "FILE_RENAME": CommandSpec(2, 2, "modify", "Rename a workspace path"),
    "FILE_DELETE": CommandSpec(1, 1, "destructive", "Delete one workspace file"),
    "TASK_ADD": CommandSpec(1, 2, "modify", "Add a task to SQLite"),
    "TASK_LIST": CommandSpec(0, 1, "read", "List SQLite tasks"),
    "TASK_DONE": CommandSpec(1, 1, "modify", "Complete one SQLite task"),
    "TASK_DELETE": CommandSpec(1, 1, "destructive", "Delete one SQLite task"),
}

_FILE_PATH_ARGUMENTS = {
    "FILE_LIST": (0,),
    "FILE_INFO": (0,),
    "FILE_MKDIR": (0,),
    "FILE_MOVE": (0, 1),
    "FILE_RENAME": (0,),
    "FILE_DELETE": (0,),
}


class WorkspaceGuard:
    """Resolve only relative paths that remain inside the workspace root."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, user_value: str) -> Path:
        """Return a safe absolute path for a DSL path argument."""

        if not user_value or "\x00" in user_value:
            raise SafetyError("Workspace paths must be non-empty and cannot contain NUL bytes.")

        candidate = Path(user_value)
        if candidate.is_absolute():
            raise SafetyError(
                f"Absolute paths are blocked. Use a path relative to {self.root.name}/."
            )
        if ".." in candidate.parts:
            raise SafetyError("Parent-directory paths ('..') are blocked.")

        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise SafetyError("The path would leave the workspace sandbox.") from exc
        return resolved

    def relative(self, path: Path) -> str:
        """Return a workspace-relative display path."""

        return str(path.resolve().relative_to(self.root))


def _validate_new_name(value: str) -> None:
    if not value or value in {".", ".."}:
        raise SafetyError("A new name must be a non-empty file or folder name.")
    if "/" in value or "\\" in value or "\x00" in value:
        raise SafetyError("A rename target must be one name, not another path.")


def _validate_task_id(value: str) -> None:
    try:
        task_id = int(value)
    except ValueError as exc:
        raise SafetyError("Task IDs must be positive integers.") from exc
    if task_id <= 0:
        raise SafetyError("Task IDs must be positive integers.")


def validate_actions(actions: list[Action], guard: WorkspaceGuard) -> None:
    """Validate every action before the executor performs any action."""

    if not actions:
        raise SafetyError("The plan contains no actions.")
    if len(actions) > 20:
        raise SafetyError("A single plan may contain at most 20 actions.")

    for action in actions:
        spec = COMMAND_SPECS.get(action.command)
        if spec is None:
            raise SafetyError(
                f"Unknown command {action.command!r} on DSL line {action.line_number}."
            )

        argument_count = len(action.args)
        if not spec.minimum_args <= argument_count <= spec.maximum_args:
            expected = (
                str(spec.minimum_args)
                if spec.minimum_args == spec.maximum_args
                else f"{spec.minimum_args}-{spec.maximum_args}"
            )
            raise SafetyError(
                f"{action.command} expects {expected} argument(s), "
                f"but received {argument_count} on line {action.line_number}."
            )

        for argument_index in _FILE_PATH_ARGUMENTS.get(action.command, ()):
            guard.path(action.args[argument_index])

        if action.command == "FILE_RENAME":
            _validate_new_name(action.args[1])

        if action.command == "TASK_ADD":
            title = action.args[0].strip()
            if not title or len(title) > 200:
                raise SafetyError("Task titles must contain 1–200 characters.")
            if len(action.args) == 2 and action.args[1].lower() not in {
                "low",
                "normal",
                "high",
            }:
                raise SafetyError("Task priority must be low, normal, or high.")

        if action.command == "TASK_LIST" and action.args:
            if action.args[0].lower() not in {"all", "open", "done"}:
                raise SafetyError("Task status must be all, open, or done.")

        if action.command in {"TASK_DONE", "TASK_DELETE"}:
            _validate_task_id(action.args[0])


def requires_confirmation(actions: list[Action]) -> bool:
    """Return whether the plan changes state and needs user approval."""

    return any(COMMAND_SPECS[action.command].risk != "read" for action in actions)


def action_risk(action: Action) -> str:
    """Return the validated risk class for display and audit logs."""

    return COMMAND_SPECS[action.command].risk
