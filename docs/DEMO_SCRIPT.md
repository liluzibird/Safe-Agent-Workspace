# Safe Workspace Agent demo script

Estimated length: 3–5 minutes.

## 1. Introduce the problem

“This project solves a small but common problem: users can describe a file or
task-management request naturally, but raw shell commands are easy to get
wrong. The agent converts the request into a visible command plan, validates
it, asks for permission when it changes data, and records what happened.”

## 2. Start the agent

~~~bash
source .venv/bin/activate
python agent.py --seed-demo
~~~

Explain that the model is running through Ollama, so no paid API is
used and the request does not need to leave the computer.

## 3. Demonstrate a read-only file action

Enter:

    list the files in the workspace

Point out:

- the natural-language request;
- the model's DSL response;
- validation before execution;
- the result shown in the terminal.

## 4. Demonstrate a file change

Enter:

    create a reports folder and move report.pdf into it

Point out the generated commands:

    FILE_MKDIR reports
    FILE_MOVE report.pdf reports/

Before execution, the UI displays the plan and asks for confirmation. Answer
yes, then show that the file moved into the new folder.

## 5. Demonstrate the second domain

Enter:

    add a high-priority task to prepare the final presentation

Approve the plan. Then enter:

    show my open tasks

Explain that these actions use SQLite rather than the file domain. Complete the
task with:

    complete task 1

## 6. Demonstrate safety and errors

Ask:

    inspect /etc/passwd

The plan should be rejected because absolute paths are outside the workspace
policy. The same validator blocks parent traversal such as ../outside.

Also point out that deletion and database changes require confirmation and that
each event is written to logs/agent_audit.jsonl.

## 7. Close with the design point

“The important part is not just the model. The Python runtime owns the
loop, parses and validates the model output, decides whether approval is
needed, executes domain-specific operations, reports results, and logs the
whole process. That is what turns an LLM response into a safer AI agent.”
