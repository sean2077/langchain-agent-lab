"""Ports and immutable values at the model and network boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

if False:  # pragma: no cover - imported only for static type checking
    from agent_learn.tools import ResearchTools


@dataclass(frozen=True, slots=True)
class SearchHit:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True, slots=True)
class Page:
    title: str
    url: str
    text: str
    retrieved_at: datetime


class SearchProvider(Protocol):
    def search(self, query: str, *, max_results: int) -> list[SearchHit]: ...


class PageReader(Protocol):
    def read(self, url: str) -> Page: ...


class AgentBackend(Protocol):
    def answer(self, question: str, tools: ResearchTools) -> str: ...
