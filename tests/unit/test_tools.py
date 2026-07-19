import json
from datetime import UTC, datetime

from agent_learn.runtime import Page, PageReader, SearchHit, SearchProvider
from agent_learn.tools import ResearchTools


class DuplicateSearch(SearchProvider):
    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        return [
            SearchHit("First", "https://example.com/a", "one"),
            SearchHit("Duplicate", "https://example.com/a", "same URL"),
            SearchHit("Second", "https://example.com/b", "two"),
        ]


class Reader(PageReader):
    def read(self, url: str) -> Page:
        return Page("Fetched", url, "Readable page text", datetime.now(UTC))


def test_search_assigns_stable_ids_and_deduplicates_urls() -> None:
    tools = ResearchTools(DuplicateSearch(), Reader(), url_validator=lambda url: url)

    payload = json.loads(tools.search_web("query"))

    assert [item["source_id"] for item in payload["sources"]] == ["S1", "S2"]
    assert [source.source_id for source in tools.sources] == ["S1", "S2"]


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
