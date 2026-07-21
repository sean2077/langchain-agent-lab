import json
from datetime import UTC, datetime
from io import StringIO

import pytest

import agent_learn.cli as cli
from agent_learn.cli import run_cli
from agent_learn.config import ConfigurationError
from agent_learn.domain import ResearchOutcome, ResearchReport, ResearchRequest, Source


class SuccessfulService:
    def research(self, request: ResearchRequest) -> ResearchReport:
        assert request.question == "What is LangChain?"
        return ResearchReport(
            answer_markdown="A source-backed answer. [S1]",
            sources=[
                Source(
                    source_id="S1",
                    title="Official docs",
                    url="https://example.com/docs",
                    retrieved_at=datetime.now(UTC),
                )
            ],
        )


class FailedService:
    def research(self, request: ResearchRequest) -> ResearchReport:
        return ResearchReport(
            answer_markdown="无法生成有来源支持的研究报告。",
            outcome=ResearchOutcome.INSUFFICIENT_EVIDENCE,
            warnings=["Search failed"],
        )


class TerminalControlService:
    def research(self, request: ResearchRequest) -> ResearchReport:
        return ResearchReport(
            answer_markdown="Visible answer\x1b[2J. [S1]",
            sources=[
                Source(
                    source_id="S1",
                    title="Official\x1b]8;;https://attacker.example\x07 docs",
                    url="https://example.com/\x9b31m",
                    retrieved_at=datetime.now(UTC),
                )
            ],
            warnings=["Visible\rwarning"],
        )


class TrackingService:
    def __init__(self) -> None:
        self.called = False

    def research(self, request: ResearchRequest) -> ResearchReport:
        self.called = True
        raise AssertionError("invalid input must not call research")


def has_terminal_control(value: str) -> bool:
    return any(
        (ord(character) < 32 and character not in "\t\n") or 0x7F <= ord(character) <= 0x9F
        for character in value
    )


def test_cli_prints_markdown_and_sources() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_cli(
        ["What is LangChain?"], service=SuccessfulService(), stdout=stdout, stderr=stderr
    )

    assert exit_code == 0
    assert "A source-backed answer. [S1]" in stdout.getvalue()
    assert "[S1] Official docs — https://example.com/docs" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_returns_nonzero_for_fail_closed_report() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_cli(
        ["What is LangChain?"], service=FailedService(), stdout=stdout, stderr=stderr
    )

    assert exit_code == 2
    assert "Search failed" in stderr.getvalue()


@pytest.mark.parametrize("question", ["   ", "x" * 4_001])
def test_cli_rejects_invalid_question_without_calling_service(question: str) -> None:
    service = TrackingService()
    stderr = StringIO()

    exit_code = run_cli([question], service=service, stdout=StringIO(), stderr=stderr)

    assert exit_code == 2
    assert service.called is False
    assert stderr.getvalue() == (
        "error: question must contain between 1 and 4000 non-whitespace characters\n"
    )


def test_cli_help_does_not_initialize_default_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_called = False

    def build_service(*, trace_enabled: bool) -> SuccessfulService:
        nonlocal build_called
        build_called = True
        raise AssertionError("help must not initialize the service")

    monkeypatch.setattr(cli, "build_research_service", build_service)

    with pytest.raises(SystemExit) as exc_info:
        run_cli(["--help"], stdout=StringIO(), stderr=StringIO())

    assert exc_info.value.code == 0
    assert build_called is False


def test_cli_initializes_default_service_after_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_count = 0

    def build_service(*, trace_enabled: bool) -> SuccessfulService:
        nonlocal build_count
        assert trace_enabled is False
        build_count += 1
        return SuccessfulService()

    monkeypatch.setattr(cli, "build_research_service", build_service)

    exit_code = run_cli(["What is LangChain?"], stdout=StringIO(), stderr=StringIO())

    assert exit_code == 0
    assert build_count == 1


def test_cli_reports_invalid_runtime_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def build_service(*, trace_enabled: bool) -> SuccessfulService:
        assert trace_enabled is False
        raise ConfigurationError("OLLAMA_BASE_URL must target a loopback address")

    monkeypatch.setattr(cli, "build_research_service", build_service)
    stderr = StringIO()

    exit_code = run_cli(["question"], stdout=StringIO(), stderr=stderr)

    assert exit_code == 2
    assert stderr.getvalue() == "error: OLLAMA_BASE_URL must target a loopback address\n"


def test_cli_strips_terminal_controls_from_runtime_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def build_service(*, trace_enabled: bool) -> SuccessfulService:
        assert trace_enabled is False
        raise ConfigurationError("invalid\x1b[2J runtime configuration")

    monkeypatch.setattr(cli, "build_research_service", build_service)
    stderr = StringIO()

    exit_code = run_cli(["question"], stdout=StringIO(), stderr=stderr)

    assert exit_code == 2
    assert stderr.getvalue() == "error: invalid[2J runtime configuration\n"
    assert has_terminal_control(stderr.getvalue()) is False


def test_cli_does_not_hide_unrelated_builder_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def build_service(*, trace_enabled: bool) -> SuccessfulService:
        assert trace_enabled is False
        raise ValueError("programming defect")

    monkeypatch.setattr(cli, "build_research_service", build_service)

    with pytest.raises(ValueError, match="programming defect"):
        run_cli(["question"], stdout=StringIO(), stderr=StringIO())


def test_cli_json_serializes_failure_outcome() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_cli(
        ["--json", "question"], service=FailedService(), stdout=stdout, stderr=stderr
    )

    assert exit_code == 2
    assert json.loads(stdout.getvalue())["outcome"] == "insufficient_evidence"


def test_cli_strips_terminal_controls_from_plain_output() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_cli(
        ["question"], service=TerminalControlService(), stdout=stdout, stderr=stderr
    )

    assert exit_code == 0
    assert has_terminal_control(stdout.getvalue()) is False
    assert has_terminal_control(stderr.getvalue()) is False
    assert "Visible answer[2J" in stdout.getvalue()
    assert "Official]8;;https://attacker.example docs" in stdout.getvalue()
    assert "Visiblewarning" in stderr.getvalue()


def test_cli_json_escapes_terminal_controls() -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_cli(
        ["--json", "question"],
        service=TerminalControlService(),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert has_terminal_control(stdout.getvalue()) is False
    assert "\\u001b" in stdout.getvalue()
    assert "\\u009b" in stdout.getvalue()
    decoded = json.loads(stdout.getvalue())
    assert decoded["outcome"] == "source_grounded"
    assert decoded["answer_markdown"] == "Visible answer\x1b[2J. [S1]"
    assert decoded["sources"][0]["url"] == "https://example.com/\x9b31m"
