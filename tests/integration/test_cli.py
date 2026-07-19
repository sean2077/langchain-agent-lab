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
