from agent_learn.config import Settings


def test_settings_use_string_defaults(monkeypatch) -> None:
    for name in ("OLLAMA_BASE_URL", "OLLAMA_MODEL", "LANGSMITH_PROJECT"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_model == "qwen3.5:9b"
    assert settings.langsmith_project == "agent-learn-synthetic"


def test_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("LANGSMITH_PROJECT", "test-project")

    settings = Settings.from_env()

    assert settings.ollama_base_url == "http://ollama.test:11434"
    assert settings.ollama_model == "test-model"
    assert settings.langsmith_project == "test-project"
