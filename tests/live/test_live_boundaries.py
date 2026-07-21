import os

import httpx
import pytest
from langchain.tools import tool

from agent_learn.adapters import DuckDuckGoSearchProvider, SafeHttpPageReader
from agent_learn.bootstrap import build_local_chat_model, build_research_service
from agent_learn.config import Settings
from agent_learn.domain import ResearchRequest
from agent_learn.trace_demo import SYNTHETIC_CASES
from examples.deep_agent import run_deep_agent_demo

pytestmark = pytest.mark.live


def require_ollama() -> Settings:
    settings = Settings.from_env()
    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.fail(f"Ollama is not reachable at {settings.ollama_base_url}: {exc}")
    models = {item["name"] for item in response.json().get("models", [])}
    has_model = any(
        name == settings.ollama_model or name.startswith(f"{settings.ollama_model}:")
        for name in models
    )
    if not has_model:
        pytest.fail(f"Ollama model {settings.ollama_model!r} is not pulled; found {sorted(models)}")
    return settings


def test_ollama_model_calls_typed_tool() -> None:
    require_ollama()

    @tool
    def multiply(a: int, b: int) -> int:
        """Multiply two integers. Always use this tool for multiplication."""

        return a * b

    model = build_local_chat_model(num_ctx=8_192).bind_tools([multiply])

    response = model.invoke("Use the multiply tool to calculate 17 times 23.")

    assert response.tool_calls
    assert response.tool_calls[0]["name"] == "multiply"
    assert response.tool_calls[0]["args"] == {"a": 17, "b": 23}


def test_deep_agent_calls_glossary_tool() -> None:
    require_ollama()

    result = run_deep_agent_demo()
    tool_messages = [message for message in result["messages"] if message.type == "tool"]

    assert tool_messages
    assert tool_messages[-1].name == "glossary_lookup"
    assert "model-driven loop" in str(tool_messages[-1].content)


def test_duckduckgo_returns_public_sources() -> None:
    results = DuckDuckGoSearchProvider().search("LangChain v1 official docs", max_results=3)

    assert results
    assert all(result.url.startswith(("http://", "https://")) for result in results)


def test_safe_reader_fetches_official_langchain_page() -> None:
    page = SafeHttpPageReader().read("https://docs.langchain.com/oss/python/releases/langchain-v1")

    assert "LangChain" in page.title or "LangChain" in page.text
    assert "create_agent" in page.text


def test_end_to_end_agent_returns_known_citations() -> None:
    require_ollama()
    report = build_research_service(trace_enabled=False).research(
        ResearchRequest(question=SYNTHETIC_CASES["langchain-overview"])
    )

    assert report.cited_source_ids
    assert report.answer_markdown != "无法生成有来源支持的研究报告。"
    assert set(report.cited_source_ids) <= {source.source_id for source in report.sources}


@pytest.mark.hosted_langsmith
def test_hosted_langsmith_synthetic_trace() -> None:
    if not os.getenv("LANGSMITH_API_KEY"):
        pytest.skip("LANGSMITH_API_KEY is not configured")
    require_ollama()
    report = build_research_service(trace_enabled=True).research(
        ResearchRequest(question=SYNTHETIC_CASES["tool-selection"])
    )

    assert report.cited_source_ids
