import json

from action_executor import ActionExecutor, ConfirmationRequired
from dsl import parse_dsl
from utils.audit_logger import AuditLogger


def make_executor(tmp_path):
    audit_path = tmp_path / "logs" / "audit.jsonl"
    return ActionExecutor(
        tmp_path / "workspace",
        AuditLogger(audit_path),
        database_path=tmp_path / "tasks.sqlite3",
    ), audit_path


def test_file_plan_is_executed_inside_workspace(tmp_path):
    executor, audit_path = make_executor(tmp_path)
    source = executor.workspace_root / "report.pdf"
    source.write_text("demo", encoding="utf-8")

    actions = parse_dsl(
        """
        FILE_MKDIR reports
        FILE_MOVE report.pdf reports/
        """
    )
    results = executor.execute(actions, confirmed=True)

    assert all(result.ok for result in results)
    assert (executor.workspace_root / "reports" / "report.pdf").exists()
    assert not source.exists()
    audit_lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any(
        json.loads(line)["event"] == "action_succeeded"
        for line in audit_lines
    )


def test_mutating_plan_requires_confirmation(tmp_path):
    executor, _ = make_executor(tmp_path)
    actions = parse_dsl("FILE_MKDIR new_folder")

    try:
        executor.execute(actions)
    except ConfirmationRequired:
        pass
    else:
        raise AssertionError("Mutating actions require confirmation.")

    assert not (executor.workspace_root / "new_folder").exists()


def test_task_crud_actions_work(tmp_path):
    executor, _ = make_executor(tmp_path)

    add_results = executor.execute(
        parse_dsl('TASK_ADD "Prepare the demo" high'),
        confirmed=True,
    )
    assert add_results[0].ok
    assert add_results[0].data["priority"] == "high"

    list_results = executor.execute(parse_dsl("TASK_LIST open"))
    assert len(list_results[0].data) == 1
    task_id = list_results[0].data[0]["id"]

    done_results = executor.execute(
        parse_dsl(f"TASK_DONE {task_id}"),
        confirmed=True,
    )
    assert done_results[0].ok

    final_results = executor.execute(parse_dsl("TASK_LIST done"))
    assert final_results[0].data[0]["status"] == "done"
