from types import SimpleNamespace

from llm_integration import LLMIntegrationError, OllamaLLM


class FakeCompletions:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error

    def create(self, **kwargs):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content)
                )
            ]
        )


class FakeClient:
    def __init__(self, content=None, error=None):
        self.chat = SimpleNamespace(
            completions=FakeCompletions(content=content, error=error)
        )


def test_llm_client_returns_local_model_text():
    llm = OllamaLLM(
        model="test-model",
        base_url="http://localhost:11434/v1",
        client=FakeClient('FILE_LIST "."'),
    )

    result = llm.generate_dsl("list files", {"workspace": "agent_workspace"})

    assert result == 'FILE_LIST "."'


def test_rate_limit_error_is_reported_without_crashing():
    class RateLimitError(Exception):
        status_code = 429

    llm = OllamaLLM(
        client=FakeClient(error=RateLimitError("too many requests")),
        max_retries=0,
    )

    try:
        llm.generate_dsl("list files", {})
    except LLMIntegrationError as exc:
        assert "rate limit" in str(exc).lower()
    else:
        raise AssertionError("Rate-limit failures should become user-facing errors.")
