from datetime import UTC, datetime

from agent_learn.domain import ResearchRequest
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


class LinkedBackend(AgentBackend):
    def answer(self, question: str, tools: ResearchTools) -> str:
        tools.search_web("LangChain v1")
        tools.read_source("S1")
        return "旧功能迁移至 [langchain-classic](file:///tmp/generated-reference.py#L1-L2) [S1]"


def test_research_service_returns_grounded_report() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), GroundedBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.cited_source_ids == ["S1"]
    assert report.sources[0].title == "LangChain v1"
    assert report.warnings == []


def test_research_service_fails_closed_on_fabricated_citation() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), FabricatingBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.cited_source_ids == []
    assert "无法生成有来源支持的研究报告" in report.answer_markdown
    assert any("unknown source ids: S9" in warning for warning in report.warnings)


def test_research_service_fails_closed_when_agent_does_not_use_tools() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), NoToolBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.sources == []
    assert any("no sources" in warning.lower() for warning in report.warnings)


def test_research_service_fails_closed_on_citation_to_unread_source() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), SearchOnlyBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.cited_source_ids == []
    assert any("cited unread sources: S1" in warning for warning in report.warnings)


def test_research_service_exposes_search_failure_without_crashing() -> None:
    service = ResearchService(
        BrokenSearch(), FakeReader(), GroundedBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="LangChain 是什么？"))

    assert report.cited_source_ids == []
    assert any("search unavailable" in warning for warning in report.warnings)


def test_research_service_removes_model_generated_link_targets() -> None:
    service = ResearchService(
        FakeSearch(), FakeReader(), LinkedBackend(), url_validator=lambda url: url
    )

    report = service.research(ResearchRequest(question="旧功能迁移到了哪里？"))

    assert report.answer_markdown == "旧功能迁移至 langchain-classic [S1]"
    assert "file://" not in report.answer_markdown
    assert any("removed 1 Markdown link target" in warning for warning in report.warnings)
