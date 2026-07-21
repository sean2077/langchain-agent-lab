from datetime import UTC, datetime

import httpx
import pytest
from langchain_core.messages import AIMessage

from agent_learn.adapters import LangChainAgentBackend, SafeHttpPageReader
from agent_learn.runtime import Page, SearchHit
from agent_learn.security import UnsafeUrlError, ValidatedHttpUrl
from agent_learn.tools import ResearchTools


def validated_target(url: str) -> ValidatedHttpUrl:
    return ValidatedHttpUrl(
        url=url,
        hostname="example.com",
        port=443,
        addresses=("93.184.216.34",),
    )


def test_page_reader_extracts_readable_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("agent-learn/")
        assert request.headers["host"] == "example.com"
        assert request.url.host == "93.184.216.34"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="""
                <html><head><title>Official docs</title><style>hidden</style></head>
                <body><nav>menu</nav><main><h1>LangChain</h1><p>Grounded text.</p></main></body>
                </html>
            """,
        )

    reader = SafeHttpPageReader(
        transport=httpx.MockTransport(handler), target_validator=validated_target
    )

    page = reader.read("https://example.com/docs")

    assert page.title == "Official docs"
    assert "LangChain" in page.text
    assert "Grounded text." in page.text
    assert "menu" not in page.text
    assert "hidden" not in page.text


def test_page_reader_revalidates_redirect_target() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    def validator(url: str) -> ValidatedHttpUrl:
        if "127.0.0.1" in url:
            raise UnsafeUrlError("private target")
        return validated_target(url)

    reader = SafeHttpPageReader(transport=httpx.MockTransport(handler), target_validator=validator)

    with pytest.raises(UnsafeUrlError, match="private target"):
        reader.read("https://example.com/redirect")


def test_page_reader_rejects_non_text_content() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"pdf"
        )
    )
    reader = SafeHttpPageReader(transport=transport, target_validator=validated_target)

    with pytest.raises(ValueError, match="unsupported content type"):
        reader.read("https://example.com/file.pdf")


def test_page_reader_caps_response_size() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/plain"}, content=b"x" * 11
        )
    )
    reader = SafeHttpPageReader(
        max_bytes=10, transport=transport, target_validator=validated_target
    )

    with pytest.raises(ValueError, match="too large"):
        reader.read("https://example.com/large")


def test_page_reader_tries_each_validated_address() -> None:
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.host)
        if request.url.host == "93.184.216.34":
            raise httpx.ConnectError("first address unavailable", request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="fetched from fallback address",
        )

    def target(url: str) -> ValidatedHttpUrl:
        return ValidatedHttpUrl(
            url=url,
            hostname="example.com",
            port=443,
            addresses=("93.184.216.34", "93.184.216.35"),
        )

    reader = SafeHttpPageReader(transport=httpx.MockTransport(handler), target_validator=target)

    page = reader.read("https://example.com/fallback")

    assert attempts == ["93.184.216.34", "93.184.216.35"]
    assert page.text == "fetched from fallback address"


class OneResultSearch:
    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        return [SearchHit("Official docs", "https://example.com/docs", "Agent API")]


class SuccessfulReader:
    def read(self, url: str) -> Page:
        return Page("Official docs", url, "Supported evidence", datetime.now(UTC))


@pytest.mark.parametrize(
    "draft",
    [
        "Uncited draft",
        "Unsupported claim.\n\nSupported claim. [S1]",
        "# Structural citation [S1]\n\n```text\n[S1]\n```",
    ],
)
def test_agent_backend_repairs_incomplete_citation_coverage_once(
    monkeypatch: pytest.MonkeyPatch,
    draft: str,
) -> None:
    tools = ResearchTools(OneResultSearch(), SuccessfulReader(), url_validator=lambda url: url)
    tools.search_web("official docs")
    tools.read_source("S1")
    agent_invocations: list[dict[str, object]] = []
    model_invocations: list[object] = []

    class FakeAgent:
        def invoke(self, payload: dict[str, object]) -> dict[str, object]:
            agent_invocations.append(payload)
            return {"messages": [AIMessage(content=draft)]}

    class FakeModel:
        def invoke(self, messages: object) -> AIMessage:
            model_invocations.append(messages)
            return AIMessage(content="Revised answer [S1]")

    monkeypatch.setattr("agent_learn.adapters.create_agent", lambda **_kwargs: FakeAgent())
    backend = LangChainAgentBackend(FakeModel())  # type: ignore[arg-type]

    answer = backend.answer("What is the API?", tools)

    assert answer == "Revised answer [S1]"
    assert len(agent_invocations) == 1
    assert len(model_invocations) == 1
    assert "chosen only from: [S1]" in str(model_invocations[0])
    assert any("grounding-format repair pass" in warning for warning in tools.warnings)


def test_agent_backend_repairs_language_for_chinese_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = ResearchTools(OneResultSearch(), SuccessfulReader(), url_validator=lambda url: url)
    tools.search_web("official docs")
    tools.read_source("S1")
    model_invocations: list[object] = []

    class FakeAgent:
        def invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"messages": [AIMessage(content="English answer [S1]")]}

    class FakeModel:
        def invoke(self, messages: object) -> AIMessage:
            model_invocations.append(messages)
            return AIMessage(content="中文答案。[S1]")

    monkeypatch.setattr("agent_learn.adapters.create_agent", lambda **_kwargs: FakeAgent())
    backend = LangChainAgentBackend(FakeModel())  # type: ignore[arg-type]

    answer = backend.answer("这个 API 是什么？", tools)

    assert answer == "中文答案。[S1]"
    assert len(model_invocations) == 1
    assert "Write the revised answer in Chinese" in str(model_invocations[0])
