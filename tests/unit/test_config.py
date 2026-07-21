import pytest

from agent_learn.config import Settings


def test_settings_use_defaults(monkeypatch) -> None:
    for name in (
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "OLLAMA_TIMEOUT_SECONDS",
        "LANGSMITH_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_model == "qwen3.5:9b"
    assert settings.ollama_timeout_seconds == 300.0
    assert settings.langsmith_project == "agent-learn-synthetic"


def test_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.2:11434/ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "45.5")
    monkeypatch.setenv("LANGSMITH_PROJECT", "test-project")

    settings = Settings.from_env()

    assert settings.ollama_base_url == "http://127.0.0.2:11434/ollama"
    assert settings.ollama_model == "test-model"
    assert settings.ollama_timeout_seconds == 45.5
    assert settings.langsmith_project == "test-project"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:11434",
        "https://127.0.0.1:11434/ollama",
        "http://[::1]:11434",
    ],
)
def test_settings_accept_loopback_ollama_base_url(monkeypatch, base_url: str) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", base_url)

    assert Settings.from_env().ollama_base_url == base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "https://model.example.invalid",
        "http://192.168.1.20:11434",
        "http://user:secret@localhost:11434",
        "ftp://localhost:11434",
        "localhost:11434",
        "",
        "http://localhost:99999",
        "http://localhost:11434?mode=remote",
        "http://localhost:11434#remote",
    ],
)
def test_settings_reject_nonlocal_or_ambiguous_ollama_base_url(monkeypatch, base_url: str) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", base_url)

    with pytest.raises(ValueError, match="OLLAMA_BASE_URL"):
        Settings.from_env()


@pytest.mark.parametrize(
    "timeout",
    ["", "0", "-1", "nan", "inf", "-inf", "five minutes"],
)
def test_settings_reject_invalid_ollama_timeout(monkeypatch, timeout: str) -> None:
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValueError, match="OLLAMA_TIMEOUT_SECONDS"):
        Settings.from_env()
