from dsl import DSLParseError, parse_dsl
from utils.validator import SafetyError, WorkspaceGuard, validate_actions


def test_parser_supports_comments_quotes_and_markdown_wrappers():
    wrapped = "\n".join(
        [
            chr(96) * 3 + "dsl",
            "# organize one file",
            'FILE_MKDIR "project reports"',
            'FILE_MOVE "report one.pdf" "project reports/"',
            "END",
            chr(96) * 3,
        ]
    )
    actions = parse_dsl(wrapped)

    assert [action.command for action in actions] == ["FILE_MKDIR", "FILE_MOVE"]
    assert actions[0].args == ("project reports",)
    assert actions[1].args == ("report one.pdf", "project reports/")


def test_empty_plan_is_rejected():
    try:
        parse_dsl("# explanation only")
    except DSLParseError as exc:
        assert "no executable" in str(exc)
    else:
        raise AssertionError("An empty plan should be rejected.")


def test_path_traversal_is_rejected(tmp_path):
    actions = parse_dsl('FILE_LIST "../outside"')
    try:
        validate_actions(actions, WorkspaceGuard(tmp_path / "workspace"))
    except SafetyError as exc:
        assert "Parent-directory" in str(exc)
    else:
        raise AssertionError("Path traversal should be rejected.")


def test_absolute_paths_are_rejected(tmp_path):
    actions = parse_dsl('FILE_INFO "/etc/passwd"')
    try:
        validate_actions(actions, WorkspaceGuard(tmp_path / "workspace"))
    except SafetyError as exc:
        assert "Absolute paths" in str(exc)
    else:
        raise AssertionError("Absolute paths should be rejected.")
