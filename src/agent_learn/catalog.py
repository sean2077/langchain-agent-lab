"""Curated first-party entry points for the learning project's core ecosystem."""

from __future__ import annotations

from agent_learn.runtime import SearchHit

_LANGCHAIN_V1 = SearchHit(
    title="What's new in LangChain v1 - Docs by LangChain",
    url="https://docs.langchain.com/oss/python/releases/langchain-v1",
    snippet="Official LangChain v1 positioning, create_agent, middleware, and namespace changes.",
)
_LANGGRAPH = SearchHit(
    title="LangGraph overview - Docs by LangChain",
    url="https://docs.langchain.com/oss/python/langgraph/overview",
    snippet="Official positioning and capabilities of the low-level orchestration runtime.",
)
_LANGSMITH_OBSERVABILITY = SearchHit(
    title="Observability concepts - Docs by LangChain",
    url="https://docs.langchain.com/langsmith/observability-concepts",
    snippet="Official LangSmith trace, run, thread, and observability concepts.",
)
_LANGSMITH_EVALUATION = SearchHit(
    title="LangSmith Evaluation - Docs by LangChain",
    url="https://docs.langchain.com/langsmith/evaluation",
    snippet="Official offline and online evaluation workflows.",
)
_DEEP_AGENTS = SearchHit(
    title="Deep Agents overview - Docs by LangChain",
    url="https://docs.langchain.com/oss/python/deepagents/overview",
    snippet="Official Deep Agents harness capabilities and when to use them.",
)
_DIFY_HOME = SearchHit(
    title="Dify Documentation - Dify Docs",
    url="https://docs.dify.ai/en/home",
    snippet="Official Dify product documentation entry point.",
)
_DIFY_COMPARISON = SearchHit(
    title="Dify vs. LangChain - Dify",
    url="https://dify.ai/blog/dify-vs-langchain",
    snippet="Dify's first-party comparison of its application platform with LangChain.",
)


def official_sources_for(question: str) -> list[SearchHit]:
    """Return stable first-party candidates for named ecosystem products."""

    normalized = question.casefold()
    candidates: list[SearchHit] = []
    if "langchain" in normalized:
        candidates.append(_LANGCHAIN_V1)
    if "langgraph" in normalized:
        candidates.append(_LANGGRAPH)
    if "langsmith" in normalized:
        candidates.extend((_LANGSMITH_OBSERVABILITY, _LANGSMITH_EVALUATION))
    if "deep agent" in normalized or "deepagent" in normalized:
        candidates.append(_DEEP_AGENTS)
    if "dify" in normalized:
        candidates.extend((_DIFY_HOME, _DIFY_COMPARISON))
    return list({candidate.url: candidate for candidate in candidates}.values())
