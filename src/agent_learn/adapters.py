"""Concrete LangChain, Ollama, search and HTTP adapters."""

from __future__ import annotations

import ipaddress
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langchain_ollama import ChatOllama
from langsmith import tracing_context

from agent_learn.catalog import official_sources_for
from agent_learn.domain import (
    count_uncited_content_blocks,
    extract_citation_ids,
    has_citable_content,
    normalize_citation_markers,
    remove_markdown_link_targets,
)
from agent_learn.runtime import AgentBackend, Page, SearchHit
from agent_learn.security import ValidatedHttpUrl, validate_public_http_target
from agent_learn.tools import ResearchTools

_SYSTEM_PROMPT = """You are a read-only research assistant.

Rules:
1. For each named product or project, first search in English for its official
   documentation or another primary source. Use secondary sources only when needed
   for comparison or independent context.
2. Use web_search before making factual claims, then use read_source for every id
   that you cite. Never cite a source that read_source could not fetch.
3. Cite every material factual claim using the exact compact form [S1]. Never write
   bare S1, [ S1 ], or any other citation syntax.
4. Never invent a source id, URL, quotation, or fact not supported by tool output.
5. If evidence is missing or a tool fails, say what could not be verified.
6. Answer in the same language as the user's question.
7. Do not output Markdown links, images, or URL destinations. Cite only with [S#].
8. Return only the final Markdown report. Do not include a separate source list;
   the caller renders it.
9. In product comparisons, label first-party comparative claims as the vendor's
   perspective instead of presenting marketing claims as neutral facts.
10. Stay focused on the products in the question; omit unrelated frameworks.
"""

_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_AGENT_RECURSION_LIMIT = 100


class DuckDuckGoSearchProvider:
    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        raw_results = DDGS().text(query, max_results=max_results)
        return [
            SearchHit(
                title=str(item.get("title") or item.get("href") or "Untitled source"),
                url=str(item.get("href") or item.get("url") or ""),
                snippet=str(item.get("body") or item.get("snippet") or ""),
            )
            for item in raw_results
            if item.get("href") or item.get("url")
        ]


class SafeHttpPageReader:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        connection_budget_seconds: float = 30.0,
        max_bytes: int = 2_000_000,
        max_characters: int = 20_000,
        max_redirects: int = 3,
        transport: httpx.BaseTransport | None = None,
        target_validator: Callable[[str], ValidatedHttpUrl] = validate_public_http_target,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not math.isfinite(connection_budget_seconds) or connection_budget_seconds <= 0:
            raise ValueError("connection_budget_seconds must be positive and finite")
        self._timeout = timeout_seconds
        self._connection_budget = connection_budget_seconds
        self._max_bytes = max_bytes
        self._max_characters = max_characters
        self._max_redirects = max_redirects
        self._transport = transport
        self._target_validator = target_validator
        self._clock = clock

    def read(self, url: str) -> Page:
        connection_deadline = self._clock() + self._connection_budget
        current_url = url
        headers = {"User-Agent": "agent-learn/0.1 (+local research assistant)"}
        with httpx.Client(
            timeout=self._timeout,
            follow_redirects=False,
            headers=headers,
            transport=self._transport,
            trust_env=False,
        ) as client:
            for redirect_count in range(self._max_redirects + 1):
                target = self._target_validator(current_url)
                result = self._fetch_target(client, target, connection_deadline)
                if isinstance(result, Page):
                    return result
                if redirect_count >= self._max_redirects:
                    raise ValueError("too many redirects")
                current_url = result

        raise ValueError("page could not be fetched")

    def _fetch_target(
        self,
        client: httpx.Client,
        target: ValidatedHttpUrl,
        connection_deadline: float,
    ) -> Page | str:
        last_connection_error: httpx.HTTPError | None = None
        for address in target.addresses:
            attempt_timeout = self._remaining_connection_timeout(connection_deadline)
            request_url = self._pinned_url(target, address)
            request_headers = {"Host": self._host_header(target)}
            extensions = (
                {"sni_hostname": target.hostname}
                if urlsplit(target.url).scheme.lower() == "https"
                else {}
            )
            try:
                with client.stream(
                    "GET",
                    request_url,
                    headers=request_headers,
                    extensions=extensions,
                    timeout=attempt_timeout,
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("redirect is missing a Location header")
                        return urljoin(target.url, location)

                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    media_type = content_type.partition(";")[0].strip().lower()
                    if media_type not in {
                        "text/html",
                        "text/plain",
                        "application/xhtml+xml",
                    }:
                        raise ValueError(f"unsupported content type: {content_type or 'missing'}")

                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            raise ValueError("response body is too large")

                    encoding = response.encoding or "utf-8"
                    html = bytes(body).decode(encoding, errors="replace")
                    title, text = self._extract_text(html, media_type)
                    return Page(
                        title=title or target.url,
                        url=target.url,
                        text=text[: self._max_characters],
                        retrieved_at=datetime.now(UTC),
                    )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_connection_error = exc

        if last_connection_error is not None:
            raise last_connection_error
        raise ValueError("validated target has no addresses")

    def _remaining_connection_timeout(self, connection_deadline: float) -> float:
        remaining = connection_deadline - self._clock()
        if remaining <= 0:
            raise TimeoutError("page connection attempt budget exhausted")
        return min(self._timeout, remaining)

    @staticmethod
    def _pinned_url(target: ValidatedHttpUrl, address: str) -> str:
        parts = urlsplit(target.url)
        parsed_address = ipaddress.ip_address(address)
        host = f"[{parsed_address.compressed}]" if parsed_address.version == 6 else address
        default_port = 443 if parts.scheme.lower() == "https" else 80
        netloc = host if target.port == default_port else f"{host}:{target.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))

    @staticmethod
    def _host_header(target: ValidatedHttpUrl) -> str:
        host = f"[{target.hostname}]" if ":" in target.hostname else target.hostname
        scheme = urlsplit(target.url).scheme.lower()
        default_port = 443 if scheme == "https" else 80
        return host if target.port == default_port else f"{host}:{target.port}"

    @staticmethod
    def _extract_text(content: str, media_type: str) -> tuple[str, str]:
        if media_type == "text/plain":
            return "", content.strip()
        soup = BeautifulSoup(content, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if soup.head:
            soup.head.decompose()
        for element in soup(["title", "script", "style", "noscript", "svg", "nav", "footer"]):
            element.decompose()
        lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
        return title, "\n".join(lines)


class LangChainAgentBackend(AgentBackend):
    def __init__(
        self,
        model: ChatOllama,
        *,
        trace_enabled: bool = False,
        trace_project: str = "agent-learn-synthetic",
    ) -> None:
        self._model = model
        self._trace_enabled = trace_enabled
        self._trace_project = trace_project

    def answer(self, question: str, tools: ResearchTools) -> str:
        langchain_tools = [
            StructuredTool.from_function(
                tools.search_web,
                name="web_search",
                description="Search the public web. Returns registered source ids and snippets.",
            ),
            StructuredTool.from_function(
                tools.read_source,
                name="read_source",
                description="Read a source previously returned by web_search, using its source id.",
            ),
        ]
        agent = create_agent(
            model=self._model,
            tools=langchain_tools,
            system_prompt=_SYSTEM_PROMPT,
            name="local_research_agent",
        )
        user_content = question
        official_sources = official_sources_for(question)
        if official_sources:
            source_payload = tools.register_sources(official_sources)
            user_content = (
                f"{question}\n\n"
                "Curated first-party source candidates are already registered below. "
                "Read the relevant ids before searching for secondary context, and prefer "
                f"them in the answer:\n{source_payload}"
            )
        with tracing_context(
            enabled=self._trace_enabled,
            project_name=self._trace_project if self._trace_enabled else None,
            tags=["synthetic"] if self._trace_enabled else None,
        ):
            result = agent.invoke(
                {"messages": [{"role": "user", "content": user_content}]},
                config={"recursion_limit": _AGENT_RECURSION_LIMIT},
            )
            messages = result.get("messages", [])
            if not messages:
                raise ValueError("agent returned no messages")
            answer = _message_text(messages[-1])

            read_source_ids = tools.read_source_ids
            grounding_markdown = _normalized_grounding_markdown(answer)
            cited_source_ids = set(extract_citation_ids(grounding_markdown))
            has_citable_block = has_citable_content(grounding_markdown)
            uncited_content_blocks = count_uncited_content_blocks(grounding_markdown)
            language_mismatch = _chinese_language_mismatch(question, answer)
            if read_source_ids and (
                not cited_source_ids
                or not cited_source_ids <= read_source_ids
                or not has_citable_block
                or uncited_content_blocks
                or language_mismatch
            ):
                allowed = ", ".join(f"[{source_id}]" for source_id in sorted(read_source_ids))
                language_instruction = (
                    " Write the revised answer in Chinese." if language_mismatch else ""
                )
                revision = (
                    "Rewrite your draft without adding any facts. Every prose paragraph, "
                    "list item, or table data row must end with at least one exact source "
                    f"marker chosen only from: {allowed}. Headings, separators, and fenced "
                    "code blocks do not need markers. Omit claims that these sources do not "
                    "support. Do not output links or a source list."
                    f"{language_instruction} Return only the revised Markdown answer."
                )
                revised_message = self._model.invoke(
                    [
                        SystemMessage(content=_SYSTEM_PROMPT),
                        *messages,
                        HumanMessage(content=revision),
                    ]
                )
                answer = _message_text(revised_message)
                tools.warnings.append("agent answer required one grounding-format repair pass")

        return answer


def _normalized_grounding_markdown(markdown: str) -> str:
    without_links, _ = remove_markdown_link_targets(markdown)
    normalized, _ = normalize_citation_markers(without_links)
    return normalized


def _chinese_language_mismatch(question: str, answer: str) -> bool:
    return len(_CJK_PATTERN.findall(question)) >= 2 and len(_CJK_PATTERN.findall(answer)) < 2


def _message_text(message: BaseMessage) -> str:
    text = getattr(message, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    content = message.content
    if isinstance(content, str):
        return content
    blocks: list[str] = []
    for block in content:
        if isinstance(block, str):
            blocks.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            blocks.append(block["text"])
    joined = "\n".join(blocks).strip()
    if not joined:
        raise ValueError("agent returned no textual final answer")
    return joined
