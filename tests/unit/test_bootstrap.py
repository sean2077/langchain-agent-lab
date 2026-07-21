import pytest

from agent_learn import bootstrap


def test_build_service_disables_environment_proxy_for_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_kwargs: dict[str, object] = {}

    class FakeChatOllama:
        def __init__(self, **kwargs: object) -> None:
            model_kwargs.update(kwargs)

    monkeypatch.setattr(bootstrap, "ChatOllama", FakeChatOllama)

    bootstrap.build_research_service()

    assert model_kwargs["client_kwargs"] == {"trust_env": False}
