from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_learn.domain import (
    ResearchReport,
    ResearchRequest,
    Source,
    count_uncited_content_blocks,
    extract_citation_ids,
    normalize_citation_markers,
    remove_markdown_link_targets,
)


def make_source(source_id: str = "S1") -> Source:
    return Source(
        source_id=source_id,
        title="LangChain v1",
        url="https://docs.langchain.com/oss/python/releases/langchain-v1",
        retrieved_at=datetime.now(UTC),
    )


def test_research_request_strips_question() -> None:
    request = ResearchRequest(question="  What is LangChain?  ")

    assert request.question == "What is LangChain?"


@pytest.mark.parametrize("question", ["", "   "])
def test_research_request_rejects_blank_question(question: str) -> None:
    with pytest.raises(ValidationError):
        ResearchRequest(question=question)


def test_extract_citation_ids_preserves_first_seen_order() -> None:
    assert extract_citation_ids("One [S2], two [S1], repeat [S2].") == ["S2", "S1"]


def test_count_uncited_content_blocks_checks_prose_and_list_items() -> None:
    markdown = """# Summary

Grounded paragraph. [S1]

Ungrounded paragraph.

- Grounded item. [S1]
  Continuation of the grounded item.
- Ungrounded item.
  Continuation of the ungrounded item.

Code example
------------

```python
print("fenced code does not need a citation")
```
"""

    assert count_uncited_content_blocks(markdown) == 2


def test_count_uncited_content_blocks_checks_table_data_rows() -> None:
    markdown = """| Claim | Result |
| :--- | ---: |
| Grounded | Yes [S1] |
| Ungrounded | No |
"""

    assert count_uncited_content_blocks(markdown) == 1


def test_count_uncited_content_blocks_checks_nested_list_items() -> None:
    markdown = """- Grounded parent. [S1]
    - Ungrounded nested item.
"""

    assert count_uncited_content_blocks(markdown) == 1


def test_thematic_break_does_not_exempt_preceding_list_item() -> None:
    markdown = """- Ungrounded item.
---

Grounded paragraph. [S1]
"""

    assert count_uncited_content_blocks(markdown) == 1


def test_table_separator_does_not_exempt_preceding_list_item() -> None:
    markdown = """- Ungrounded item | detail
| --- | --- |

Grounded paragraph. [S1]
"""

    assert count_uncited_content_blocks(markdown) == 1


def test_normalize_citation_markers_canonicalizes_common_model_variants() -> None:
    normalized, count = normalize_citation_markers(
        "First fact S1。 Second fact [ S2 ]. Canonical [S3]."
    )

    assert normalized == "First fact [S1]。 Second fact [S2]. Canonical [S3]."
    assert count == 2


def test_remove_markdown_link_targets_preserves_citation_label() -> None:
    sanitized, count = remove_markdown_link_targets(
        "Supported claim [S1](https://example.com/source)."
    )

    assert sanitized == "Supported claim [S1]."
    assert count == 1


def test_report_accepts_known_citations() -> None:
    report = ResearchReport(
        answer_markdown="LangChain v1 uses `create_agent`. [S1]",
        sources=[make_source()],
    )

    assert report.cited_source_ids == ["S1"]


def test_report_rejects_unknown_citation() -> None:
    with pytest.raises(ValidationError, match="unknown source ids: S2"):
        ResearchReport(
            answer_markdown="Unsupported claim. [S2]",
            sources=[make_source()],
        )


def test_report_rejects_uncited_content_block_when_citations_are_present() -> None:
    with pytest.raises(ValidationError, match="uncited content block"):
        ResearchReport(
            answer_markdown="Unsupported claim.\n\nSupported claim. [S1]",
            sources=[make_source()],
        )


def test_report_rejects_citations_only_in_structural_blocks() -> None:
    with pytest.raises(ValidationError, match="no citable content block"):
        ResearchReport(
            answer_markdown="# Summary [S1]\n\n```text\n[S1]\n```",
            sources=[make_source()],
        )


def test_report_rejects_model_generated_markdown_link_target() -> None:
    with pytest.raises(ValidationError, match="Markdown link targets are not allowed"):
        ResearchReport(
            answer_markdown="Use [create_agent](https://example.com/api). [S1]",
            sources=[make_source()],
        )


def test_report_rejects_noncanonical_citation_marker() -> None:
    with pytest.raises(ValidationError, match="citation markers must use canonical"):
        ResearchReport(
            answer_markdown="LangChain is an agent framework S1.",
            sources=[make_source()],
        )


def test_report_rejects_duplicate_source_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate source ids: S1"):
        ResearchReport(
            answer_markdown="Answer [S1]",
            sources=[make_source(), make_source()],
        )


def test_fail_closed_report_can_have_no_sources() -> None:
    report = ResearchReport(
        answer_markdown="No source-backed answer is available.",
        warnings=["Search failed"],
    )

    assert report.sources == []
    assert report.cited_source_ids == []
