import json
from datetime import UTC, datetime

import pytest

from agent_learn.runtime import Page, PageReader, SearchHit, SearchProvider
from agent_learn.tools import ResearchTools


class DuplicateSearch(SearchProvider):
    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        return [
            SearchHit("First", "https://example.com/a", "one"),
            SearchHit("Duplicate", "https://example.com/a", "same URL"),
            SearchHit("Second", "https://example.com/b", "two"),
        ]


class OverReturningSearch(SearchProvider):
    def __init__(self) -> None:
        self.requested_limits: list[int] = []

    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        self.requested_limits.append(max_results)
        return [
            SearchHit(f"Result {index}", f"https://example.com/{index}", "snippet")
            for index in range(1, 9)
        ]


class OverlongFieldSearch(SearchProvider):
    long_url = "https://example.com/" + "u" * 600

    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        return [
            SearchHit("  " + "T" * 600 + "  ", "https://example.com/a", "S" * 2_500),
            SearchHit("   ", self.long_url, "short snippet"),
        ]


class Reader(PageReader):
    def read(self, url: str) -> Page:
        return Page("Fetched", url, "Readable page text", datetime.now(UTC))


class RedirectingReader(PageReader):
    retrieved_at = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)

    def read(self, url: str) -> Page:
        return Page(
            "Final page title",
            "https://docs.example.com/final",
            "Redirected page text",
            self.retrieved_at,
        )


class MetadataReader(PageReader):
    def __init__(self, title: str, final_url: str) -> None:
        self.title = title
        self.final_url = final_url

    def read(self, url: str) -> Page:
        return Page(
            self.title,
            self.final_url,
            "Readable page text",
            datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
        )


def test_search_assigns_stable_ids_and_deduplicates_urls() -> None:
    tools = ResearchTools(DuplicateSearch(), Reader(), url_validator=lambda url: url)

    payload = json.loads(tools.search_web("query"))

    assert [item["source_id"] for item in payload["sources"]] == ["S1", "S2"]
    assert tools.registered_source_ids == {"S1", "S2"}


def test_search_enforces_result_limit_when_provider_over_returns() -> None:
    provider = OverReturningSearch()
    tools = ResearchTools(provider, Reader(), url_validator=lambda url: url)

    payload = json.loads(tools.search_web("query"))

    assert provider.requested_limits == [5]
    assert [item["source_id"] for item in payload["sources"]] == [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
    ]
    assert tools.registered_source_ids == {"S1", "S2", "S3", "S4", "S5"}


def test_search_bounds_model_visible_title_and_snippet_fields() -> None:
    tools = ResearchTools(OverlongFieldSearch(), Reader(), url_validator=lambda url: url)

    payload = json.loads(tools.search_web("query"))

    assert payload["sources"][0]["title"] == "T" * 500
    assert payload["sources"][0]["snippet"] == "S" * 2_000
    assert payload["sources"][1]["url"] == OverlongFieldSearch.long_url
    assert payload["sources"][1]["title"] == OverlongFieldSearch.long_url[:500]


def test_register_sources_seeds_candidates_before_web_search() -> None:
    tools = ResearchTools(DuplicateSearch(), Reader(), url_validator=lambda url: url)

    seeded = json.loads(
        tools.register_sources(
            [SearchHit("Official", "https://example.com/official", "primary source")]
        )
    )
    searched = json.loads(tools.search_web("query"))

    assert seeded["sources"][0]["source_id"] == "S1"
    assert [item["source_id"] for item in searched["sources"]] == ["S2", "S3"]


def test_read_source_only_accepts_registered_id() -> None:
    tools = ResearchTools(DuplicateSearch(), Reader(), url_validator=lambda url: url)

    result = json.loads(tools.read_source("S7"))

    assert result == {"error": "unknown source id: S7"}
    assert tools.warnings == ["unknown source id: S7"]


def test_read_source_returns_page_without_exposing_new_url_input() -> None:
    tools = ResearchTools(DuplicateSearch(), Reader(), url_validator=lambda url: url)
    tools.search_web("query")

    result = json.loads(tools.read_source("S1"))

    assert result["source_id"] == "S1"
    assert result["text"] == "Readable page text"
    assert tools.read_source_ids == {"S1"}


def test_read_source_records_validated_final_page_as_evidence() -> None:
    tools = ResearchTools(DuplicateSearch(), RedirectingReader(), url_validator=lambda url: url)
    tools.search_web("query")

    result = json.loads(tools.read_source("S1"))

    assert result["title"] == "Final page title"
    assert result["url"] == "https://docs.example.com/final"
    assert json.loads(tools.search_web("query"))["sources"][0]["url"] == "https://example.com/a"
    assert [source.model_dump(mode="json") for source in tools.read_sources] == [
        {
            "source_id": "S1",
            "title": "Final page title",
            "url": "https://docs.example.com/final",
            "retrieved_at": "2026-07-21T12:00:00Z",
        }
    ]


@pytest.mark.parametrize(
    ("page_title", "final_url", "expected_title"),
    [
        (
            "T" * 600,
            "https://docs.example.com/final",
            "T" * 500,
        ),
        (
            "   ",
            "https://docs.example.com/" + "u" * 600,
            ("https://docs.example.com/" + "u" * 600)[:500],
        ),
    ],
)
def test_read_source_adapts_external_title_to_domain_limit(
    page_title: str,
    final_url: str,
    expected_title: str,
) -> None:
    tools = ResearchTools(
        DuplicateSearch(),
        MetadataReader(page_title, final_url),
        url_validator=lambda url: url,
    )
    tools.search_web("query")

    result = json.loads(tools.read_source("S1"))

    assert result["title"] == expected_title
    assert result["url"] == final_url
    assert result["text"] == "Readable page text"
    assert result["retrieved_at"] == "2026-07-21T12:00:00+00:00"
    assert tools.read_source_ids == {"S1"}


def test_read_source_rejects_unvalidated_final_page_url() -> None:
    def reject_final_url(url: str) -> str:
        if url == "https://docs.example.com/final":
            raise ValueError("final URL is not public")
        return url

    tools = ResearchTools(DuplicateSearch(), RedirectingReader(), url_validator=reject_final_url)
    tools.search_web("query")

    result = json.loads(tools.read_source("S1"))

    assert result == {
        "error": "failed to read S1: final URL is not public",
        "source_id": "S1",
    }
    assert tools.read_source_ids == set()
    assert tools.read_sources == []
