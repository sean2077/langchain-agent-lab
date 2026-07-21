import pytest

from agent_learn import bootstrap
from agent_learn.config import Settings


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


def test_build_service_uses_one_settings_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        ollama_base_url="http://127.0.0.2:11434",
        ollama_model="snapshot-model",
        ollama_timeout_seconds=12.5,
        langsmith_project="snapshot-project",
    )
    settings_reads = 0
    model_kwargs: dict[str, object] = {}
    backend_kwargs: dict[str, object] = {}

    def read_settings() -> Settings:
        nonlocal settings_reads
        settings_reads += 1
        return settings

    class FakeChatOllama:
        def __init__(self, **kwargs: object) -> None:
            model_kwargs.update(kwargs)

    class FakeAgentBackend:
        def __init__(self, model: object, **kwargs: object) -> None:
            backend_kwargs.update(model=model, **kwargs)

    monkeypatch.setattr(bootstrap.Settings, "from_env", read_settings)
    monkeypatch.setattr(bootstrap, "ChatOllama", FakeChatOllama)
    monkeypatch.setattr(bootstrap, "LangChainAgentBackend", FakeAgentBackend)

    bootstrap.build_research_service(trace_enabled=True)

    assert settings_reads == 1
    assert model_kwargs == {
        "model": "snapshot-model",
        "base_url": "http://127.0.0.2:11434",
        "temperature": 0,
        "num_ctx": 16_384,
        "num_predict": 2_048,
        "client_kwargs": {"trust_env": False, "timeout": 12.5},
    }
    assert backend_kwargs["trace_enabled"] is True
    assert backend_kwargs["trace_project"] == "snapshot-project"
