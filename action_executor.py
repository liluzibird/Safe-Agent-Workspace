"""Validate and execute the agent's domain actions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from domains.file_operations import FileOperations
from domains.task_database import TaskDatabase
from dsl import Action
from utils.audit_logger import AuditLogger
from utils.validator import (
    WorkspaceGuard,
    action_risk,
    requires_confirmation,
    validate_actions,
)


class ConfirmationRequired(RuntimeError):
    """Raised when a plan changes state without explicit approval."""

    def __init__(self, actions: list[Action]):
        self.actions = actions
        super().__init__("The plan requires user confirmation before execution.")


@dataclass
class ExecutionResult:
    """Result of one attempted action."""

    action: Action
    ok: bool
    message: str
    data: Any = None


class ActionExecutor:
    """Dispatch validated DSL commands to the appropriate domain module."""

    def __init__(
        self,
        workspace_root: str | Path,
        audit_logger: AuditLogger,
        database_path: str | Path | None = None,
    ):
        self.guard = WorkspaceGuard(workspace_root)
        self.audit_logger = audit_logger
        self.files = FileOperations(self.guard)
        self.database = TaskDatabase(
            database_path or Path("logs") / "agent_tasks.sqlite3"
        )

    @property
    def workspace_root(self) -> Path:
        return self.guard.root

    def snapshot(self) -> dict[str, Any]:
        """Return small current-state context for the LLM."""

        try:
            entries = self.files.list_entries(".")
        except Exception as exc:
            entries = [{"error": str(exc)}]
        try:
            tasks = self.database.list_tasks("all")
        except Exception as exc:
            tasks = [{"error": str(exc)}]
        return {
            "workspace": self.guard.root.name,
            "top_level_entries": entries[:50],
            "tasks": tasks[:50],
        }

    def execute(
        self,
        actions: list[Action],
        *,
        user_request: str = "",
        dsl_code: str = "",
        confirmed: bool = False,
    ) -> list[ExecutionResult]:
        """Validate and execute a complete plan, stopping on the first error."""

        validate_actions(actions, self.guard)
        if requires_confirmation(actions) and not confirmed:
            raise ConfirmationRequired(actions)

        self.audit_logger.event(
            "plan_execution_started",
            user_request=user_request,
            dsl=dsl_code,
            action_count=len(actions),
        )

        results: list[ExecutionResult] = []
        for action in actions:
            risk = action_risk(action)
            self.audit_logger.event(
                "action_started",
                command=action.command,
                args=list(action.args),
                risk=risk,
                user_request=user_request,
            )
            try:
                data = self._dispatch(action)
                result = ExecutionResult(
                    action=action,
                    ok=True,
                    message=self._success_message(action, data),
                    data=data,
                )
                self.audit_logger.event(
                    "action_succeeded",
                    command=action.command,
                    args=list(action.args),
                    risk=risk,
                    result=data,
                )
            except Exception as exc:
                result = ExecutionResult(
                    action=action,
                    ok=False,
                    message=str(exc),
                )
                self.audit_logger.event(
                    "action_failed",
                    command=action.command,
                    args=list(action.args),
                    risk=risk,
                    error=str(exc),
                )
                results.append(result)
                break

            results.append(result)

        self.audit_logger.event(
            "plan_execution_finished",
            user_request=user_request,
            succeeded=sum(result.ok for result in results),
            failed=sum(not result.ok for result in results),
        )
        return results

    def _dispatch(self, action: Action) -> Any:
        command = action.command
        args = action.args

        if command == "FILE_LIST":
            return self.files.list_entries(args[0])
        if command == "FILE_INFO":
            return self.files.info(args[0])
        if command == "FILE_MKDIR":
            return self.files.make_directory(args[0])
        if command == "FILE_MOVE":
            return self.files.move(args[0], args[1])
        if command == "FILE_RENAME":
            return self.files.rename(args[0], args[1])
        if command == "FILE_DELETE":
            return self.files.delete_file(args[0])
        if command == "TASK_ADD":
            priority = args[1] if len(args) == 2 else "normal"
            return self.database.add(args[0], priority)
        if command == "TASK_LIST":
            status = args[0] if args else "all"
            return self.database.list_tasks(status)
        if command == "TASK_DONE":
            return self.database.complete(int(args[0]))
        if command == "TASK_DELETE":
            return self.database.delete(int(args[0]))

        # validate_actions should make this unreachable.
        raise ValueError(f"Unsupported command: {command}")

    @staticmethod
    def _success_message(action: Action, data: Any) -> str:
        if action.command == "FILE_LIST":
            if not data:
                return "The folder is empty."
            lines = [
                f"- {entry['name']} ({entry['kind']}, {entry['size']} bytes)"
                for entry in data
            ]
            return "Found:\n" + "\n".join(lines)
        if action.command == "TASK_LIST":
            if not data:
                return "No matching tasks."
            return json.dumps(data, indent=2, ensure_ascii=False)
        if isinstance(data, (dict, list)):
            return json.dumps(data, indent=2, ensure_ascii=False)
        return str(data)
