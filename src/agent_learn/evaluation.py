"""Local, non-hosted quality experiment for the five approved research cases."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Protocol, TextIO
from urllib.parse import urlsplit

from agent_learn.bootstrap import build_research_service
from agent_learn.cli import strip_terminal_controls
from agent_learn.config import ConfigurationError
from agent_learn.domain import ResearchReport, ResearchRequest


@dataclass(frozen=True, slots=True)
class SourceRequirement:
    label: str
    accepted_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualityCase:
    case_id: str
    question: str
    source_requirements: tuple[SourceRequirement, ...]


@dataclass(frozen=True, slots=True)
class QualityCaseResult:
    grounded_contract: bool
    missing_source_requirements: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.grounded_contract and not self.missing_source_requirements


class Researcher(Protocol):
    def research(self, request: ResearchRequest) -> ResearchReport: ...


_LANGCHAIN_V1 = SourceRequirement(
    "LangChain v1",
    ("https://docs.langchain.com/oss/python/releases/langchain-v1",),
)
_LANGGRAPH = SourceRequirement(
    "LangGraph overview",
    ("https://docs.langchain.com/oss/python/langgraph/overview",),
)
_LANGSMITH_OBSERVABILITY = SourceRequirement(
    "LangSmith observability",
    ("https://docs.langchain.com/langsmith/observability-concepts",),
)
_LANGSMITH_EVALUATION = SourceRequirement(
    "LangSmith evaluation",
    ("https://docs.langchain.com/langsmith/evaluation",),
)
_DEEP_AGENTS = SourceRequirement(
    "Deep Agents overview",
    ("https://docs.langchain.com/oss/python/deepagents/overview",),
)
_DIFY = SourceRequirement(
    "Dify first-party source",
    ("https://docs.dify.ai/en/home", "https://dify.ai/blog/dify-vs-langchain"),
)

QUALITY_CASES = (
    QualityCase(
        "langchain-v1",
        "LangChain v1 的定位和标准 Agent API 是什么？",
        (_LANGCHAIN_V1,),
    ),
    QualityCase(
        "langgraph-selection",
        "什么情况下应从 LangChain create_agent 下沉到 LangGraph？",
        (_LANGCHAIN_V1, _LANGGRAPH),
    ),
    QualityCase(
        "langsmith-trace-eval",
        "LangSmith tracing 与 evaluation 分别解决什么问题？",
        (_LANGSMITH_OBSERVABILITY, _LANGSMITH_EVALUATION),
    ),
    QualityCase(
        "deep-agents-harness",
        "Deep Agents 相比普通 LangChain Agent 增加了哪些 harness 能力？",
        (_LANGCHAIN_V1, _DEEP_AGENTS),
    ),
    QualityCase(
        "dify-positioning",
        "Dify 与 LangChain 的产品定位差异是什么？",
        (_LANGCHAIN_V1, _DIFY),
    ),
)


def evaluate_report(case: QualityCase, report: ResearchReport) -> QualityCaseResult:
    """Apply deterministic structural checks without claiming semantic correctness."""

    cited_source_ids = set(report.cited_source_ids)
    cited_urls = tuple(
        source.url for source in report.sources if source.source_id in cited_source_ids
    )
    missing_requirements = tuple(
        requirement.label
        for requirement in case.source_requirements
        if not any(
            _page_identity(url) == _page_identity(accepted_url)
            for url in cited_urls
            for accepted_url in requirement.accepted_urls
        )
    )
    return QualityCaseResult(
        grounded_contract=report.is_source_grounded,
        missing_source_requirements=missing_requirements,
    )


def _page_identity(url: str) -> tuple[str, str, str]:
    parts = urlsplit(url)
    return parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/"


def run_quality_experiment(*, service: Researcher, stdout: TextIO, stderr: TextIO) -> int:
    """Run every case, isolate failures, and render ephemeral output for human review."""

    passed_count = 0
    for case in QUALITY_CASES:
        stdout.write(f"## {case.case_id}\n\n{case.question}\n\n")
        try:
            report = service.research(ResearchRequest(question=case.question))
        except Exception as exc:
            stdout.write("Automatic checks: FAIL (case execution failed)\n\n")
            stderr.write(strip_terminal_controls(f"error: {case.case_id}: {exc}\n"))
            continue

        result = evaluate_report(case, report)
        stdout.write(strip_terminal_controls(report.answer_markdown.rstrip()) + "\n\n")
        if report.sources:
            stdout.write("Sources\n")
            for source in report.sources:
                stdout.write(
                    strip_terminal_controls(
                        f"- [{source.source_id}] {source.title} — {source.url}\n"
                    )
                )
            stdout.write("\n")

        grounded_status = "PASS" if result.grounded_contract else "FAIL"
        source_status = "PASS"
        if result.missing_source_requirements:
            source_status = (
                "FAIL (missing cited source: " + ", ".join(result.missing_source_requirements) + ")"
            )
        stdout.write(
            f"Automatic checks: grounded contract={grounded_status}; "
            f"required first-party evidence={source_status}\n\n"
        )
        for warning in report.warnings:
            stderr.write(strip_terminal_controls(f"warning: {case.case_id}: {warning}\n"))
        if result.passed:
            passed_count += 1

    stdout.write(f"Automatic result: {passed_count}/{len(QUALITY_CASES)} passed\n")
    stdout.write("Manual review remains required for semantic support and direct usability.\n")
    return 0 if passed_count == len(QUALITY_CASES) else 2


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the five-case local quality experiment without hosted tracing"
    )
    parser.parse_args()
    try:
        service = build_research_service(trace_enabled=False)
    except ConfigurationError as error:
        sys.stderr.write(strip_terminal_controls(f"error: {error}\n"))
        raise SystemExit(2) from None
    raise SystemExit(run_quality_experiment(service=service, stdout=sys.stdout, stderr=sys.stderr))


if __name__ == "__main__":
    main()
