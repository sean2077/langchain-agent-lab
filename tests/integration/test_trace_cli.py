from __future__ import annotations

import pytest

import agent_learn.trace_demo as trace_demo
from agent_learn.config import ConfigurationError


def test_trace_entrypoint_checks_key_before_building_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def build_service(**_kwargs: object) -> object:
        raise AssertionError("service must not be built")

    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setattr(trace_demo, "build_research_service", build_service)

    exit_code = trace_demo.run_trace_demo(["--case", "langchain-overview"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "LANGSMITH_API_KEY is required for the synthetic trace demo.\n"


def test_trace_entrypoint_reports_invalid_runtime_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def build_service(*, trace_enabled: bool) -> object:
        assert trace_enabled is True
        raise ConfigurationError("invalid\x1b[2J runtime configuration")

    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setattr(trace_demo, "build_research_service", build_service)

    exit_code = trace_demo.run_trace_demo(["--case", "langchain-overview"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "error: invalid[2J runtime configuration\n"
