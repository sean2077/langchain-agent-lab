from datetime import UTC, datetime

from agent_learn.domain import ResearchOutcome, ResearchRequest
from agent_learn.research import ResearchService
from agent_learn.runtime import AgentBackend, Page, PageReader, SearchHit, SearchProvider
from agent_learn.tools import ResearchTools


class FakeSearch(SearchProvider):
    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        assert query
        assert max_results == 5
        return [
            SearchHit(
                title="LangChain v1",
                url="https://docs.langchain.com/oss/python/releases/langchain-v1",
                snippet="create_agent is the standard API.",
            )
        ]


class BrokenSearch(SearchProvider):
    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        raise RuntimeError("search unavailable")


class HandlesBrokenSearchBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        result = tools.search_web("LangChain v1")
        assert "search unavailable" in result
        return "No source-backed answer is available."


class FailingBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        raise RuntimeError("model unavailable")


class FakeReader(PageReader):
    def read(self, url: str) -> Page:
        return Page(
            title="LangChain v1",
            url=url,
            text="LangChain v1 uses create_agent as its standard agent API.",
            retrieved_at=datetime.now(UTC),
        )


class GroundedBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        search_result = tools.search_web("LangChain v1")
        assert '"source_id": "S1"' in search_result
        page = tools.read_source("S1")
        assert "standard agent API" in page
        return "LangChain v1 的标准入口是 `create_agent`。[S1]"


class FabricatingBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("LangChain v1")
        return "这是一个没有收集到的说法。[S9]"


class NoToolBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        return "I already know the answer."


class SearchOnlyBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("LangChain v1")
        return "LangChain v1 使用 `create_agent`。[S1]"


class ReadsWithoutCitingBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("LangChain v1")
        tools.read_source("S1")
        return "LangChain v1 uses create_agent."


class LinkedBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("LangChain v1")
        tools.read_source("S1")
        return "旧功能迁移至 [langchain-classic](file:///tmp/generated-reference.py#L1-L2) [S1]"


class BareLinkedBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("LangChain v1")
        tools.read_source("S1")
        return "Read https://attacker.example/escape for details. [S1]"


class HiddenReferenceCitationBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("LangChain v1")
        tools.read_source("S1")
        return 'Unsupported shortcut [label].\n\n[label]:\nfile:///tmp/secret "[S1]"'


class PartiallyGroundedBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("LangChain v1")
        tools.read_source("S1")
        return "LangChain 适合所有生产工作负载。\n\nLangChain v1 的标准入口是 `create_agent`。[S1]"


class HiddenCitationBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("LangChain v1")
        tools.read_source("S1")
        return "LangChain v1 uses create_agent.\n<!-- [S1] -->"


class CandidateSearch(SearchProvider):
    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        return [
            SearchHit("Search title", "https://example.com/start", "read candidate"),
            SearchHit("Unread candidate", "https://example.com/unread", "not read"),
        ]


class RedirectingReader(PageReader):
    retrieved_at = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)

    def read(self, url: str) -> Page:
        return Page(
            title="Final page title",
            url="https://docs.example.com/final",
            text="Grounded evidence.",
            retrieved_at=self.retrieved_at,
        )


class ReadsFirstCandidateBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("query")
        tools.read_source("S1")
        return "Grounded answer. [S1]"


def test_research_service_returns_grounded_report() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), GroundedBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.cited_source_ids == ["S1"]
    assert report.outcome is ResearchOutcome.SOURCE_GROUNDED
    assert report.sources[0].title == "LangChain v1"
    assert report.warnings == []


def test_successful_report_exposes_only_read_final_page_provenance() -> None:
    service = ResearchService(
        CandidateSearch(),
        RedirectingReader(),
        ReadsFirstCandidateBackend(),
        url_validator=lambda url: url,
    )

    report = service.research(ResearchRequest(question="question"))

    assert [source.model_dump(mode="json") for source in report.sources] == [
        {
            "source_id": "S1",
            "title": "Final page title",
            "url": "https://docs.example.com/final",
            "retrieved_at": "2026-07-21T12:00:00Z",
        }
    ]
    assert report.cited_source_ids == ["S1"]
    assert report.warnings == []


def test_research_service_fails_closed_on_fabricated_citation() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), FabricatingBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.cited_source_ids == []
    assert report.outcome is ResearchOutcome.INVALID_REPORT
    assert "无法生成有来源支持的研究报告" in report.answer_markdown
    assert any("unknown source ids: S9" in warning for warning in report.warnings)


def test_research_service_fails_closed_when_agent_does_not_use_tools() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), NoToolBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.sources == []
    assert report.outcome is ResearchOutcome.INSUFFICIENT_EVIDENCE
    assert any("no sources" in warning.lower() for warning in report.warnings)


def test_research_service_fails_closed_on_citation_to_unread_source() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), SearchOnlyBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.cited_source_ids == []
    assert report.outcome is ResearchOutcome.INVALID_REPORT
    assert report.sources == []
    assert any("cited unread sources: S1" in warning for warning in report.warnings)


def test_research_service_exposes_search_failure_without_crashing() -> None:
    service = ResearchService(
        BrokenSearch(),
        FakeReader(),
        HandlesBrokenSearchBackend(),
        url_validator=lambda url: url,
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.cited_source_ids == []
    assert report.outcome is ResearchOutcome.INSUFFICIENT_EVIDENCE
    assert any("search unavailable" in warning for warning in report.warnings)


def test_research_service_classifies_agent_exception() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), FailingBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.outcome is ResearchOutcome.AGENT_ERROR
    assert any("model unavailable" in warning for warning in report.warnings)


def test_research_service_classifies_missing_citations_as_insufficient_evidence() -> None:
    service = ResearchService(
        FakeSearch(),
        FakeReader(),
        ReadsWithoutCitingBackend(),
        url_validator=lambda url: url,
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.outcome is ResearchOutcome.INSUFFICIENT_EVIDENCE
    assert any("no source citations" in warning for warning in report.warnings)


def test_research_service_removes_model_generated_link_targets() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), LinkedBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="旧功能迁移到了哪里？"))

    assert report.answer_markdown == "旧功能迁移至 langchain-classic [S1]"
    assert "file://" not in report.answer_markdown
    assert any("removed 1 Markdown link target" in warning for warning in report.warnings)


def test_research_service_removes_model_generated_gfm_autolink() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), BareLinkedBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="Where is the documentation?"))

    assert report.answer_markdown == "Read  for details. [S1]"
    assert "attacker.example" not in report.answer_markdown
    assert any("removed 1 Markdown link target" in warning for warning in report.warnings)


def test_research_service_fails_closed_on_citation_hidden_in_reference_definition() -> None:
    service = ResearchService(
        FakeSearch(),
        FakeReader(),
        HiddenReferenceCitationBackend(),
        url_validator=lambda url: url,
    )

    report = service.research(ResearchRequest(question="Where is the documentation?"))

    assert report.cited_source_ids == []
    assert report.outcome is ResearchOutcome.INSUFFICIENT_EVIDENCE
    assert any("removed 1 Markdown link target" in warning for warning in report.warnings)
    assert any("no source citations" in warning for warning in report.warnings)


def test_research_service_fails_closed_on_uncited_content_block() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), PartiallyGroundedBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.cited_source_ids == []
    assert report.outcome is ResearchOutcome.INVALID_REPORT
    assert any("uncited content block" in warning for warning in report.warnings)


def test_research_service_fails_closed_on_citation_hidden_in_html_comment() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), HiddenCitationBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="What is LangChain?"))

    assert report.cited_source_ids == []
    assert report.outcome is ResearchOutcome.INSUFFICIENT_EVIDENCE
    assert any("no source citations" in warning for warning in report.warnings)
