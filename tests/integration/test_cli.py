import json
from datetime import UTC, datetime
from io import StringIO

from agent_learn.cli import run_cli
from agent_learn.domain import ResearchReport, ResearchRequest, Source


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
    assert decoded["answer_markdown"] == "Visible answer\x1b[2J. [S1]"
    assert decoded["sources"][0]["url"] == "https://example.com/\x9b31m"
