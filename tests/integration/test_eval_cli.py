from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

import pytest

import agent_learn.evaluation as evaluation
from agent_learn.domain import ResearchReport, ResearchRequest, Source
from agent_learn.evaluation import QUALITY_CASES, QualityCase, run_quality_experiment


def passing_report(case: QualityCase) -> ResearchReport:
    urls = [requirement.accepted_urls[0] for requirement in case.source_requirements]
    sources = [
        Source(
            source_id=f"S{index}",
            title=requirement.label,
            url=url,
            retrieved_at=datetime(2026, 7, 21, tzinfo=UTC),
        )
        for index, (requirement, url) in enumerate(
            zip(case.source_requirements, urls, strict=True), start=1
        )
    ]
    citations = " ".join(f"[{source.source_id}]" for source in sources)
    return ResearchReport(answer_markdown=f"Reviewed answer. {citations}", sources=sources)


class PassingService:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def research(self, request: ResearchRequest) -> ResearchReport:
        self.questions.append(request.question)
        case = next(case for case in QUALITY_CASES if case.question == request.question)
        return passing_report(case)


class FirstCaseRaises(PassingService):
    def research(self, request: ResearchRequest) -> ResearchReport:
        self.questions.append(request.question)
        if len(self.questions) == 1:
            raise RuntimeError("synthetic\x1b[2J case failure")
        case = next(case for case in QUALITY_CASES if case.question == request.question)
        return passing_report(case)


class TerminalControlService(PassingService):
    def research(self, request: ResearchRequest) -> ResearchReport:
        report = super().research(request)
        controlled_source = report.sources[0].model_copy(
            update={"title": f"{report.sources[0].title}\x1b]8;;hidden\x07"}
        )
        return report.model_copy(
            update={
                "answer_markdown": f"{report.answer_markdown}\x1b[2J",
                "sources": [controlled_source, *report.sources[1:]],
                "warnings": ["warning\roverwrite"],
            }
        )


def has_terminal_control(value: str) -> bool:
    return any(
        (ord(character) < 32 and character not in "\t\n") or 0x7F <= ord(character) <= 0x9F
        for character in value
    )


def run_with(service: PassingService) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    exit_code = run_quality_experiment(service=service, stdout=stdout, stderr=stderr)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def test_quality_experiment_renders_all_reports_and_passes() -> None:
    service = PassingService()

    exit_code, stdout, stderr = run_with(service)

    assert exit_code == 0
    assert service.questions == [case.question for case in QUALITY_CASES]
    assert stdout.count("Reviewed answer.") == 5
    assert "Automatic result: 5/5 passed" in stdout
    assert stderr == ""


def test_quality_experiment_continues_after_one_case_raises() -> None:
    service = FirstCaseRaises()

    exit_code, stdout, stderr = run_with(service)

    assert exit_code == 2
    assert len(service.questions) == 5
    assert "Automatic result: 4/5 passed" in stdout
    assert has_terminal_control(stderr) is False
    assert "langchain-v1: synthetic[2J case failure" in stderr


def test_quality_experiment_strips_terminal_controls_from_reports() -> None:
    exit_code, stdout, stderr = run_with(TerminalControlService())

    assert exit_code == 0
    assert has_terminal_control(stdout) is False
    assert has_terminal_control(stderr) is False
    assert "Reviewed answer." in stdout
    assert "warningoverwrite" in stderr


def test_eval_entrypoint_keeps_hosted_tracing_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    service = PassingService()

    def build_service(*, trace_enabled: bool) -> PassingService:
        assert trace_enabled is False
        return service

    monkeypatch.setattr(evaluation, "build_research_service", build_service)
    monkeypatch.setattr(evaluation, "run_quality_experiment", lambda **kwargs: 0)
    monkeypatch.setattr(evaluation.sys, "argv", ["agent-learn-eval"])

    with pytest.raises(SystemExit) as exc_info:
        evaluation.main()

    assert exc_info.value.code == 0
