"""Composition root shared by CLI, UI and synthetic tracing."""

from langchain_ollama import ChatOllama

from agent_learn.adapters import (
    DuckDuckGoSearchProvider,
    LangChainAgentBackend,
    SafeHttpPageReader,
)
from agent_learn.config import Settings
from agent_learn.research import ResearchService


def build_research_service(*, trace_enabled: bool = False) -> ResearchService:
    settings = Settings.from_env()
    model = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        num_ctx=16_384,
        num_predict=2_048,
    )
    return ResearchService(
        DuckDuckGoSearchProvider(),
        SafeHttpPageReader(),
        LangChainAgentBackend(
            model,
            trace_enabled=trace_enabled,
            trace_project=settings.langsmith_project,
        ),
    )
