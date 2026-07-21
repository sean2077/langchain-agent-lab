"""Composition root shared by CLI, UI and synthetic tracing."""

from langchain_ollama import ChatOllama

from agent_learn.adapters import (
    DuckDuckGoSearchProvider,
    LangChainAgentBackend,
    SafeHttpPageReader,
)
from agent_learn.config import Settings
from agent_learn.research import ResearchService


def build_local_chat_model(
    *,
    num_ctx: int | None = None,
    num_predict: int | None = None,
) -> ChatOllama:
    return _build_local_chat_model(
        Settings.from_env(),
        num_ctx=num_ctx,
        num_predict=num_predict,
    )


def _build_local_chat_model(
    settings: Settings,
    *,
    num_ctx: int | None = None,
    num_predict: int | None = None,
) -> ChatOllama:
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        num_ctx=num_ctx,
        num_predict=num_predict,
        client_kwargs={
            "trust_env": False,
            "timeout": settings.ollama_timeout_seconds,
        },
    )


def build_research_service(*, trace_enabled: bool = False) -> ResearchService:
    settings = Settings.from_env()
    model = _build_local_chat_model(settings, num_ctx=16_384, num_predict=2_048)
    return ResearchService(
        DuckDuckGoSearchProvider(),
        SafeHttpPageReader(),
        LangChainAgentBackend(
            model,
            trace_enabled=trace_enabled,
            trace_project=settings.langsmith_project,
        ),
    )
