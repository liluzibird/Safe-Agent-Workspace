"""Ollama integration through its OpenAI-compatible API."""

from __future__ import annotations

import json
import os
import time
from typing import Any


class LLMIntegrationError(RuntimeError):
    """Raised when the model cannot produce a usable response."""


SYSTEM_PROMPT = """
You are SafeWorkspace, the planning component of a Linux terminal agent.
You do not execute commands yourself. You translate the user's request into a
small, reviewable DSL plan for a Python executor.

Safety and scope rules:
1. Use only the commands listed below.
2. Use paths relative to the agent workspace. Never use absolute paths, '..',
   shell commands, Python code, URLs, or commands that are not listed.
3. Never delete anything unless the user explicitly asked for deletion.
4. Use the fewest commands needed. Do not invent files, task IDs, or results.
5. Return only DSL commands and optional comments beginning with '#'. Do not
   return Markdown fences, JSON, explanations, or a conversational response.
6. Paths and task titles containing spaces must be quoted.

Available DSL commands:
FILE_LIST <relative_folder>
FILE_INFO <relative_path>
FILE_MKDIR <relative_folder>
FILE_MOVE <relative_source> <relative_destination>
FILE_RENAME <relative_path> <new_name>
FILE_DELETE <relative_file>
TASK_ADD <title> [low|normal|high]
TASK_LIST [all|open|done]
TASK_DONE <positive_integer_id>
TASK_DELETE <positive_integer_id>

The file destination in FILE_MOVE may be an existing folder or a new file
path. FILE_RENAME's second argument must be only a new name. FILE_DELETE is
for files only. Use comments to describe a plan if helpful.

Examples:
User: list the files in the workspace
FILE_LIST "."

User: create a reports folder and move report.pdf into it
FILE_MKDIR "reports"
FILE_MOVE "report.pdf" "reports/"

User: remember that I need to submit the demo, with high priority
TASK_ADD "Submit the demo" high

User: show my open tasks
TASK_LIST open
"""


class OllamaLLM:
    """Call a Ollama model with retry handling."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        client: Any | None = None,
    ):
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.base_url = (
            base_url
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        ).rstrip("/")
        self.timeout = timeout or float(os.getenv("OLLAMA_TIMEOUT", "90"))
        self.max_retries = (
            max_retries
            if max_retries is not None
            else int(os.getenv("OLLAMA_MAX_RETRIES", "3"))
        )

        if client is not None:
            self.client = client
            return

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMIntegrationError(
                "The openai package is not installed. Run: pip install -r requirements.txt"
            ) from exc

        self.client = OpenAI(
            base_url=f"{self.base_url}/",
            api_key="ollama",
            timeout=self.timeout,
            max_retries=0,
        )

    def generate_dsl(self, user_request: str, context: dict[str, Any]) -> str:
        """Ask the model for a plan based on the request and current state."""

        prompt = (
            "Current agent state:\n"
            f"{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
            f"User request:\n{user_request}\n\n"
            "Return only the DSL plan."
        )
        return self._complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )

    def repair_dsl(
        self,
        user_request: str,
        context: dict[str, Any],
        invalid_output: str,
        validation_error: str,
    ) -> str:
        """Give the model one constrained opportunity to repair bad output."""

        prompt = (
            "The previous plan was rejected before execution.\n"
            f"Validation error: {validation_error}\n"
            f"Previous output:\n{invalid_output}\n\n"
            "Original request:\n"
            f"{user_request}\n\n"
            "Current agent state:\n"
            f"{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
            "Return a corrected plan using only the documented DSL. "
            "Return commands only."
        )
        return self._complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )

    def _complete(self, messages: list[dict[str, str]]) -> str:
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=600,
                )
                content = response.choices[0].message.content
                if not content or not content.strip():
                    raise LLMIntegrationError("The model returned no text.")
                return content.strip()
            except Exception as exc:  # OpenAI SDK uses several error classes.
                last_error = exc
                if attempt >= self.max_retries or not self._retryable(exc):
                    break
                time.sleep(min(2**attempt, 8))

        raise LLMIntegrationError(self._friendly_error(last_error)) from last_error

    @staticmethod
    def _retryable(error: Exception) -> bool:
        """Identify temporary connection, rate, and server failures."""

        name = error.__class__.__name__
        status_code = getattr(error, "status_code", None)
        if status_code is None:
            response = getattr(error, "response", None)
            status_code = getattr(response, "status_code", None)
        return (
            name in {"APIConnectionError", "APITimeoutError", "RateLimitError"}
            or status_code in {429, 500, 502, 503, 504}
        )

    def _friendly_error(self, error: Exception | None) -> str:
        if error is None:
            return "The model did not return a response."

        name = error.__class__.__name__
        status_code = getattr(error, "status_code", None)
        if name in {"APIConnectionError", "APITimeoutError"}:
            return (
                "Could not reach Ollama at "
                f"{self.base_url}. Start Ollama and verify that "
                f"the model '{self.model}' is installed."
            )
        if name == "RateLimitError" or status_code == 429:
            return "Ollama reported a rate limit. Wait briefly and try again."
        if status_code is not None and int(status_code) >= 500:
            return f"Ollama returned a temporary server error ({status_code})."
        return f"LLM request failed: {error}"
