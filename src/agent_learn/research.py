"""Deep module that owns one complete, source-grounded research request."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from agent_learn.domain import (
    ResearchReport,
    ResearchRequest,
    Source,
    normalize_citation_markers,
    remove_markdown_link_targets,
)
from agent_learn.runtime import AgentBackend, PageReader, SearchProvider
from agent_learn.security import validate_public_http_url
from agent_learn.tools import ResearchTools

_FAIL_CLOSED_ANSWER = "无法生成有来源支持的研究报告。"


class ResearchService:
    def __init__(
        self,
        search_provider: SearchProvider,
        page_reader: PageReader,
        agent_backend: AgentBackend,
        *,
        url_validator: Callable[[str], str] = validate_public_http_url,
    ) -> None:
        self._search_provider = search_provider
        self._page_reader = page_reader
        self._agent_backend = agent_backend
        self._url_validator = url_validator

    def research(self, request: ResearchRequest) -> ResearchReport:
        tools = ResearchTools(
            self._search_provider,
            self._page_reader,
            url_validator=self._url_validator,
        )
        try:
            answer = self._agent_backend.answer(request.question, tools).strip()
        except Exception as exc:
            return self._failed_report(tools.sources, [*tools.warnings, f"agent failed: {exc}"])

        answer, removed_link_count = remove_markdown_link_targets(answer)
        answer, normalized_citation_count = normalize_citation_markers(answer)
        report_warnings = list(tools.warnings)
        if normalized_citation_count:
            report_warnings.append(
                f"normalized {normalized_citation_count} citation marker(s) to [S#]"
            )
        if removed_link_count:
            report_warnings.append(
                f"removed {removed_link_count} Markdown link target(s) from model response"
            )

        if not tools.sources:
            return self._failed_report([], [*report_warnings, "agent collected no sources"])

        try:
            report = ResearchReport(
                answer_markdown=answer,
                sources=tools.sources,
                warnings=report_warnings,
            )
        except ValidationError as exc:
            concise_error = "; ".join(error["msg"] for error in exc.errors())
            return self._failed_report(
                tools.sources,
                [*report_warnings, f"report validation failed: {concise_error}"],
            )

        if not report.cited_source_ids:
            return self._failed_report(
                tools.sources,
                [*report_warnings, "model response contained no source citations"],
            )

        unread_source_ids = sorted(set(report.cited_source_ids) - tools.read_source_ids)
        if unread_source_ids:
            return self._failed_report(
                tools.sources,
                [
                    *report_warnings,
                    f"model cited unread sources: {', '.join(unread_source_ids)}",
                ],
            )
        return report

    @staticmethod
    def _failed_report(sources: list[Source], warnings: list[str]) -> ResearchReport:
        return ResearchReport(
            answer_markdown=_FAIL_CLOSED_ANSWER,
            sources=sources,
            warnings=list(dict.fromkeys(warnings)),
        )
