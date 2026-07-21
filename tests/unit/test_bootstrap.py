import pytest

from agent_learn import bootstrap


def test_build_service_configures_ollama_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_kwargs: dict[str, object] = {}

    class FakeChatOllama:
        def __init__(self, **kwargs: object) -> None:
            model_kwargs.update(kwargs)

    monkeypatch.setattr(bootstrap, "ChatOllama", FakeChatOllama)
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "45.5")

    bootstrap.build_research_service()

    assert model_kwargs["client_kwargs"] == {"trust_env": False, "timeout": 45.5}
