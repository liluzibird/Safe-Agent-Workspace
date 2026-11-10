from action_executor import ActionExecutor
from agent import WorkspaceAgent
from utils.audit_logger import AuditLogger


class FakeLLM:
    def generate_dsl(self, user_request, context):
        assert user_request == "show the workspace files"
        assert "workspace" in context
        return 'FILE_LIST "."'

    def repair_dsl(self, user_request, context, invalid_output, validation_error):
        raise AssertionError("Repair should not be needed in this test.")


def test_agent_creates_a_validated_plan(tmp_path):
    audit_logger = AuditLogger(tmp_path / "audit.jsonl")
    executor = ActionExecutor(
        tmp_path / "workspace",
        audit_logger,
        database_path=tmp_path / "tasks.sqlite3",
    )
    agent = WorkspaceAgent(FakeLLM(), executor, audit_logger)

    plan = agent.create_plan("show the workspace files")

    assert plan.actions[0].command == "FILE_LIST"
    assert plan.actions[0].args == (".",)
    results = executor.execute(plan.actions)
    assert results[0].ok
