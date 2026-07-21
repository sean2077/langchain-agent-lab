from datetime import UTC, datetime

from agent_learn.domain import ResearchReport, Source
from agent_learn.evaluation import QUALITY_CASES, evaluate_report


def make_report(*urls: str, cited_source_ids: tuple[str, ...] | None = None) -> ResearchReport:
    sources = [
        Source(
            source_id=f"S{index}",
            title=f"Source {index}",
            url=url,
            retrieved_at=datetime(2026, 7, 21, tzinfo=UTC),
        )
        for index, url in enumerate(urls, start=1)
    ]
    citations = cited_source_ids or tuple(source.source_id for source in sources)
    return ResearchReport(
        answer_markdown=f"Grounded answer. {' '.join(f'[{source_id}]' for source_id in citations)}",
        sources=sources,
    )


def test_quality_dataset_contains_the_five_approved_cases() -> None:
    assert [case.case_id for case in QUALITY_CASES] == [
        "langchain-v1",
        "langgraph-selection",
        "langsmith-trace-eval",
        "deep-agents-harness",
        "dify-positioning",
    ]


def test_code_evaluator_passes_grounded_report_with_required_cited_sources() -> None:
    case = QUALITY_CASES[1]
    report = make_report(
        "https://docs.langchain.com/oss/python/releases/langchain-v1",
        "https://docs.langchain.com/oss/python/langgraph/overview",
    )

    result = evaluate_report(case, report)

    assert result.grounded_contract is True
    assert result.missing_source_requirements == ()
    assert result.passed is True


def test_code_evaluator_does_not_count_uncited_required_source() -> None:
    case = QUALITY_CASES[1]
    report = make_report(
        "https://docs.langchain.com/oss/python/releases/langchain-v1",
        "https://docs.langchain.com/oss/python/langgraph/overview",
        cited_source_ids=("S1",),
    )

    result = evaluate_report(case, report)

    assert result.grounded_contract is True
    assert result.missing_source_requirements == ("LangGraph overview",)
    assert result.passed is False


def test_code_evaluator_rejects_a_different_page_with_matching_path_prefix() -> None:
    case = QUALITY_CASES[1]
    report = make_report(
        "https://docs.langchain.com/oss/python/releases/langchain-v1",
        "https://docs.langchain.com/oss/python/langgraph/overview-other",
    )

    result = evaluate_report(case, report)

    assert result.missing_source_requirements == ("LangGraph overview",)
    assert result.passed is False


def test_code_evaluator_rejects_fail_closed_report() -> None:
    result = evaluate_report(
        QUALITY_CASES[0],
        ResearchReport(answer_markdown="无法生成有来源支持的研究报告。"),
    )

    assert result.grounded_contract is False
    assert result.passed is False
