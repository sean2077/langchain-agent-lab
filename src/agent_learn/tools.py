"""Per-request, read-only tools exposed to the agent."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from agent_learn.domain import SOURCE_TITLE_MAX_CHARACTERS, Source
from agent_learn.runtime import PageReader, SearchHit, SearchProvider
from agent_learn.security import UnsafeUrlError, validate_public_http_url

UrlValidator = Callable[[str], str]

_MAX_CANDIDATE_SNIPPET_CHARACTERS = 2_000


@dataclass(frozen=True, slots=True)
class _RegisteredSource:
    source_id: str
    title: str
    url: str


def _bounded_source_title(title: str, fallback: str) -> str:
    return (title.strip() or fallback)[:SOURCE_TITLE_MAX_CHARACTERS]


class ResearchTools:
    """Own source ids and warnings for exactly one research request."""

    def __init__(
        self,
        search_provider: SearchProvider,
        page_reader: PageReader,
        *,
        url_validator: UrlValidator = validate_public_http_url,
        max_search_results: int = 5,
    ) -> None:
        self._search_provider = search_provider
        self._page_reader = page_reader
        self._url_validator = url_validator
        self._max_search_results = max_search_results
        self._sources_by_url: dict[str, _RegisteredSource] = {}
        self._sources_by_id: dict[str, _RegisteredSource] = {}
        self._read_sources_by_id: dict[str, Source] = {}
        self.warnings: list[str] = []

    @property
    def registered_source_ids(self) -> set[str]:
        return set(self._sources_by_id)

    @property
    def read_sources(self) -> list[Source]:
        return list(self._read_sources_by_id.values())

    @property
    def read_source_ids(self) -> set[str]:
        return set(self._read_sources_by_id)

    def search_web(self, query: str) -> str:
        """Search the public web and return source ids, titles, URLs and snippets."""

        try:
            hits = self._search_provider.search(query, max_results=self._max_search_results)
        except Exception as exc:  # provider errors become model-visible, fail-closed warnings
            warning = f"web search failed: {exc}"
            self.warnings.append(warning)
            return json.dumps({"error": warning, "sources": []}, ensure_ascii=False)

        return self.register_sources(hits[: self._max_search_results])

    def register_sources(self, hits: Sequence[SearchHit]) -> str:
        """Register trusted or searched candidates in the request-local source registry."""

        results: list[dict[str, str]] = []
        for hit in hits:
            try:
                url = self._url_validator(hit.url)
            except (UnsafeUrlError, ValueError) as exc:
                self.warnings.append(f"skipped unsafe search result {hit.url!r}: {exc}")
                continue

            source = self._sources_by_url.get(url)
            if source is None:
                source = _RegisteredSource(
                    source_id=f"S{len(self._sources_by_id) + 1}",
                    title=_bounded_source_title(hit.title, url),
                    url=url,
                )
                self._sources_by_url[url] = source
                self._sources_by_id[source.source_id] = source
            results.append(
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "url": source.url,
                    "snippet": hit.snippet[:_MAX_CANDIDATE_SNIPPET_CHARACTERS],
                }
            )

        deduplicated = list({item["source_id"]: item for item in results}.values())
        return json.dumps({"sources": deduplicated}, ensure_ascii=False)

    def read_source(self, source_id: str) -> str:
        """Read a previously registered source by id; arbitrary URL input is not accepted."""

        source = self._sources_by_id.get(source_id)
        if source is None:
            warning = f"unknown source id: {source_id}"
            self.warnings.append(warning)
            return json.dumps({"error": warning}, ensure_ascii=False)

        try:
            page = self._page_reader.read(source.url)
            final_url = self._url_validator(page.url)
            read_source = Source(
                source_id=source_id,
                title=_bounded_source_title(page.title, final_url),
                url=final_url,
                retrieved_at=page.retrieved_at,
            )
        except Exception as exc:  # network/parser failures must not crash the agent loop
            warning = f"failed to read {source_id}: {exc}"
            self.warnings.append(warning)
            return json.dumps({"error": warning, "source_id": source_id}, ensure_ascii=False)

        self._read_sources_by_id[source_id] = read_source
        return json.dumps(
            {
                "source_id": source_id,
                "title": read_source.title,
                "url": read_source.url,
                "retrieved_at": read_source.retrieved_at.isoformat(),
                "text": page.text,
            },
            ensure_ascii=False,
        )
