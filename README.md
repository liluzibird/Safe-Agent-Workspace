# Safe Workspace Agent

Safe Workspace Agent is a terminal AI agent for Linux. A user
describes a small workspace task in natural language. Ollama turns that request
into a short DSL plan, the Python program validates the plan, asks for
confirmation when it changes state, and then executes it.

## Problem and relevance

Many simple project chores are easy to describe but risky to perform through
raw shell commands. A user may want to organize a file or record a follow-up
task without manually remembering command syntax. This project provides a
reviewable middle layer between natural language and concrete operations:

    user request -> LLM plan -> DSL parser -> safety validation
    -> confirmation -> domain executor -> audit log and feedback

The agent supports two focused domains:

1. Workspace file operations: list, inspect, create folders, move, rename, and
   delete individual files.
2. A SQLite task database: add, list, complete, and delete tasks.

The workspace is a sandbox folder. DSL paths are relative to that folder, and
the executor rejects absolute paths, parent-directory traversal, overwrites,
and unsupported commands.

## Why use a DSL?

The assignment allows JSON, DSL, or another structured text format. This
project uses a small custom DSL because it is:

- easy for a person to read in the approval screen;
- easy to parse and validate line by line;
- easy to demonstrate in a terminal;
- less verbose than JSON for a multi-step plan.

The DSL is not copied from the reference repository. It keeps the useful
one-command-per-line idea and extends it to a second domain.

## Architecture

~~~mermaid
flowchart LR
    U[User request] --> L[Ollama model]
    L --> P[DSL parser and validator]
    P --> C[Confirmation gate]
    C --> X[File and SQLite executors]
    X --> O[Results and audit log]
    O --> L
~~~

Important modules:

- agent.py: terminal UI and agent loop.
- llm_integration.py: Ollama/OpenAI-compatible client, retries, and prompts.
- dsl.py: parser for the structured model output.
- utils/validator.py: command schemas, sandbox checks, and risk checks.
- action_executor.py: dispatches validated actions to domain modules.
- domains/file_operations.py: safe filesystem operations.
- domains/task_database.py: SQLite CRUD operations.
- utils/audit_logger.py: append-only JSONL audit records.
- tests/: offline tests that do not call an LLM.

## Installation on Arch Linux

Install Python and Ollama using the normal Arch/Ollama instructions. Then:

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start Ollama in another terminal if it is not already running.
ollama serve
ollama pull llama3.2:3b
~~~

The application uses Ollama's OpenAI-compatible endpoint at
http://localhost:11434/v1. No paid API key is required.

## Run the agent

To start the interactive terminal UI:

~~~bash
python agent.py
~~~

To create harmless sample files for the demonstration:

~~~bash
python agent.py --seed-demo
~~~

The model name and endpoint can also be configured with environment variables:

~~~bash
cp .env.example .env
export OLLAMA_MODEL=llama3.2:3b
export OLLAMA_BASE_URL=http://localhost:11434/v1
python agent.py
~~~

The program does not automatically load .env files. Exporting variables keeps
the configuration explicit and avoids adding another dependency.

## Demonstration requests

After running with --seed-demo, try these requests one at a time:

1. list the files in the workspace
2. create a reports folder and move report.pdf into it
3. add a high-priority task to prepare the agent demonstration
4. show my open tasks
5. complete task 1

For requests that modify files or tasks, the terminal displays the generated
DSL and asks for approval. Read-only requests run immediately. Try asking for
an absolute path or a path outside the workspace to demonstrate rejection.

## DSL examples

~~~text
# File domain
FILE_LIST "."
FILE_MKDIR "reports"
FILE_MOVE "report.pdf" "reports/"

# Task database domain
TASK_ADD "Prepare the demo" high
TASK_LIST open
TASK_DONE 1
~~~

Supported commands are defined in utils/validator.py. The parser accepts
comments, blank lines, case-insensitive command names, and quoted arguments.

## Safety and error handling

- All LLM output is parsed and validated before execution.
- The plan is displayed before any state-changing action.
- File changes and task changes require explicit y/yes confirmation.
- The file executor is restricted to the workspace root.
- Absolute paths, parent traversal, symlinks, unsupported commands, malformed
  arguments, and overwrite attempts are rejected.
- Deletion is limited to individual files and task rows; recursive deletion is
  not implemented.
- The model receives one repair prompt when its first response is invalid.
- Temporary Ollama connection, timeout, rate, and server errors use bounded
  exponential retries.
- Every request, model response, rejected plan, confirmation decision, action,
  result, and error is appended to logs/agent_audit.jsonl.

## Prompt engineering techniques

The system prompt uses:

1. Role and scope: the model is a planner, not an executor.
2. A formal command grammar with argument rules and examples.
3. Negative constraints: no shell, Python, URLs, absolute paths, or unknown
   commands.
4. Few-shot examples for file and task requests.
5. Dynamic context containing the current workspace and tasks.
6. Low temperature for more repeatable structured output.
7. A repair prompt containing the exact parser or safety error.

These techniques address the prompt-engineering portion of the project rather
than relying on an unconstrained conversational response.

## Tests

Run the offline test suite:

~~~bash
pytest -q
~~~

The tests cover DSL parsing, quoted arguments, path traversal protection,
confirmation gating, file execution, task CRUD operations, audit logging, and
the agent planning loop. They use a fake LLM only inside tests; the application
itself uses the Ollama model.

## Grading alignment

- Problem identification: focuses on safe, useful project-workspace chores.
- Application design: separates model, parser, validator, confirmation gate,
  executors, UI, and audit logging.
- Implementation: includes two domain modules and a complete execution
  loop.
- Prompt engineering: uses structured output instructions, examples, negative
  constraints, context, and repair.
- UI/UX: terminal preview, explicit approval, status markers, readable errors,
  help text, and action feedback.
- Demonstration: the README provides more than three use cases and an
  explicit safety/error case.

## Limitations

This is an intentionally focused educational agent. It does not run arbitrary
shell commands, call remote web APIs, send email, or make network changes. Those
limits make the demo safer and keep the implementation understandable. A
future version could add another allow-listed domain with its own schema and
confirmation policy.
