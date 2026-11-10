"""Safe Workspace Agent command-line application."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from action_executor import ActionExecutor, ExecutionResult
from dsl import Action, DSLParseError, format_actions, parse_dsl
from llm_integration import LLMIntegrationError, OllamaLLM
from utils.audit_logger import AuditLogger, configure_logging
from utils.validator import (
    SafetyError,
    requires_confirmation,
    validate_actions,
)


class PlanError(RuntimeError):
    """Raised when the LLM cannot produce a safe executable plan."""


@dataclass(frozen=True)
class AgentPlan:
    """A validated plan waiting for user approval or execution."""

    request: str
    dsl: str
    actions: list[Action]
    context: dict[str, Any]


class WorkspaceAgent:
    """Connect the LLM planner, DSL parser, and action executor."""

    def __init__(
        self,
        llm: Any,
        executor: ActionExecutor,
        audit_logger: AuditLogger,
    ):
        self.llm = llm
        self.executor = executor
        self.audit_logger = audit_logger

    def create_plan(self, user_request: str) -> AgentPlan:
        """Generate, parse, validate, and if necessary repair one plan."""

        request = user_request.strip()
        if not request:
            raise PlanError("Please enter a request.")

        context = self.executor.snapshot()
        self.audit_logger.event("request_received", user_request=request)

        try:
            dsl = self.llm.generate_dsl(request, context)
        except Exception as exc:
            self.audit_logger.event(
                "llm_request_failed",
                user_request=request,
                error=str(exc),
            )
            raise PlanError(str(exc)) from exc

        for attempt in range(2):
            self.audit_logger.event(
                "llm_response_received",
                user_request=request,
                attempt=attempt + 1,
                response=dsl,
            )
            try:
                actions = parse_dsl(dsl)
                validate_actions(actions, self.executor.guard)
            except (DSLParseError, SafetyError) as exc:
                self.audit_logger.event(
                    "plan_rejected",
                    user_request=request,
                    attempt=attempt + 1,
                    error=str(exc),
                    response=dsl,
                )
                if attempt == 1:
                    raise PlanError(
                        f"The model produced an unsafe or invalid plan: {exc}"
                    ) from exc
                try:
                    dsl = self.llm.repair_dsl(
                        request,
                        context,
                        dsl,
                        str(exc),
                    )
                except Exception as repair_exc:
                    raise PlanError(
                        f"The model produced an invalid plan and repair failed: "
                        f"{repair_exc}"
                    ) from repair_exc
                continue

            self.audit_logger.event(
                "plan_created",
                user_request=request,
                action_count=len(actions),
                dsl=dsl,
            )
            return AgentPlan(
                request=request,
                dsl=dsl,
                actions=actions,
                context=context,
            )

        raise PlanError("The agent could not create a plan.")


def seed_demo_workspace(root: Path) -> None:
    """Create harmless sample files for a first demonstration."""

    root.mkdir(parents=True, exist_ok=True)
    samples = {
        "demo_files/report.pdf": "Sample PDF placeholder for the demo.\n",
        "demo_files/notes.txt": "Sample notes for the demo.\n",
        "demo_files/photo.jpg": "Sample image placeholder for the demo.\n",
    }
    for relative_path, content in samples.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="An LLM agent that safely manages a project workspace."
    )
    parser.add_argument(
        "--workspace",
        default="agent_workspace",
        help="Sandbox folder for file actions and the SQLite database.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama model name; defaults to OLLAMA_MODEL or llama3.2:3b.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Ollama OpenAI-compatible URL; defaults to OLLAMA_BASE_URL.",
    )
    parser.add_argument(
        "--once",
        metavar="REQUEST",
        help="Process one request and exit instead of opening the chat loop.",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Add harmless sample files to the workspace before starting.",
    )
    return parser


def _print_results(results: list[ExecutionResult]) -> None:
    for result in results:
        marker = "[OK]" if result.ok else "[ERROR]"
        print(f"{marker} {result.action.display()}")
        for line in result.message.splitlines():
            print(f"      {line}")


def _run_request(
    request: str,
    agent: WorkspaceAgent,
    executor: ActionExecutor,
    audit_logger: AuditLogger,
) -> None:
    try:
        plan = agent.create_plan(request)
    except PlanError as exc:
        print(f"[ERROR] {exc}")
        return

    print("\nGenerated DSL plan:")
    print("-------------------")
    print(plan.dsl)
    print("\nValidated actions:")
    print("------------------")
    print(format_actions(plan.actions))

    approved = True
    if requires_confirmation(plan.actions):
        print("\nThis plan changes the workspace or task database.")
        answer = input("Execute it? [y/N]: ").strip().lower()
        approved = answer in {"y", "yes"}
        if not approved:
            audit_logger.event(
                "plan_cancelled",
                user_request=request,
                dsl=plan.dsl,
            )
            print("[CANCELLED] No actions were executed.")
            return

    try:
        results = executor.execute(
            plan.actions,
            user_request=plan.request,
            dsl_code=plan.dsl,
            confirmed=approved,
        )
    except Exception as exc:
        audit_logger.event(
            "plan_execution_failed",
            user_request=request,
            dsl=plan.dsl,
            error=str(exc),
        )
        print(f"[ERROR] {exc}")
        return

    print("\nExecution results:")
    print("------------------")
    _print_results(results)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = Path(args.workspace).expanduser()
    audit_logger = AuditLogger(Path("logs") / "agent_audit.jsonl")
    configure_logging(Path("logs") / "agent.log")
    executor = ActionExecutor(root, audit_logger)

    if args.seed_demo:
        seed_demo_workspace(executor.workspace_root)
        print(f"Demo files are ready in {executor.workspace_root}.")

    try:
        llm = OllamaLLM(model=args.model, base_url=args.base_url)
    except LLMIntegrationError as exc:
        print(f"[ERROR] {exc}")
        return 1

    agent = WorkspaceAgent(llm, executor, audit_logger)

    print("=" * 64)
    print("SAFE WORKSPACE AGENT")
    print("=" * 64)
    print(f"Workspace: {executor.workspace_root}")
    print(f"Model:     {llm.model}")
    print("Commands:  /help, /quit")
    print("Every change is previewed and requires confirmation.")

    if args.once:
        _run_request(args.once, agent, executor, audit_logger)
        return 0

    while True:
        try:
            request = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0

        if request.lower() in {"/quit", "/exit", "quit", "exit"}:
            print("Goodbye.")
            return 0
        if request.lower() == "/help":
            print(
                "\nTry requests such as:\n"
                "  list the files in the workspace\n"
                "  create a reports folder and move report.pdf into it\n"
                "  add a high-priority task to prepare the demo\n"
                "  show my open tasks\n"
            )
            continue
        if not request:
            continue

        _run_request(request, agent, executor, audit_logger)


if __name__ == "__main__":
    sys.exit(main())
