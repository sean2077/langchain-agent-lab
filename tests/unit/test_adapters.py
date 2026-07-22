import socket
from datetime import UTC, datetime

import httpx
import pytest
from langchain_core.messages import AIMessage
from langsmith import get_tracing_context
from langsmith.utils import get_env_var, tracing_is_enabled

from agent_learn.adapters import LangChainAgentBackend, SafeHttpPageReader
from agent_learn.runtime import Page, SearchHit
from agent_learn.security import UnsafeUrlError, ValidatedHttpUrl, validate_public_http_target
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
            headers={"content-type": "Text/HTML; Charset=UTF-8"},
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
    assert "Official docs" not in page.text
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


def test_page_reader_rejects_zero_port_redirect_before_second_request() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://example.com:0/final"})
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="must not be read",
        )

    def validator(url: str) -> ValidatedHttpUrl:
        return validate_public_http_target(
            url,
            resolver=lambda _hostname, port, *_: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
            ],
        )

    reader = SafeHttpPageReader(
        transport=httpx.MockTransport(handler),
        target_validator=validator,
    )

    with pytest.raises(UnsafeUrlError, match="port must be between 1 and 65535"):
        reader.read("https://example.com/start")

    assert requests == ["https://93.184.216.34/start"]


def test_page_reader_rejects_non_text_content() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"pdf"
        )
    )
    reader = SafeHttpPageReader(transport=transport, target_validator=validated_target)

    with pytest.raises(ValueError, match="unsupported content type"):
        reader.read("https://example.com/file.pdf")


def test_page_reader_accepts_xhtml_media_type_with_parameter() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "Application/XHTML+XML; Charset=UTF-8"},
            text=(
                "<html><head><title>XHTML metadata title</title></head>"
                "<body><main>Readable XHTML</main></body></html>"
            ),
        )
    )
    reader = SafeHttpPageReader(transport=transport, target_validator=validated_target)

    page = reader.read("https://example.com/page.xhtml")

    assert page.title == "XHTML metadata title"
    assert page.text == "Readable XHTML"


def test_page_reader_keeps_html_title_out_of_body_character_budget() -> None:
    title = "T" * 100
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                f"<html><head><title>{title}</title></head>"
                "<body><main>BODY_EVIDENCE</main></body></html>"
            ),
        )
    )
    reader = SafeHttpPageReader(
        max_characters=20,
        transport=transport,
        target_validator=validated_target,
    )

    page = reader.read("https://example.com/bounded")

    assert page.title == title
    assert page.text == "BODY_EVIDENCE"


def test_page_reader_excludes_standalone_title_from_html_fragment() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<title>Fragment metadata</title><main>Fragment body</main>",
        )
    )
    reader = SafeHttpPageReader(transport=transport, target_validator=validated_target)

    page = reader.read("https://example.com/fragment")

    assert page.title == "Fragment metadata"
    assert page.text == "Fragment body"


def test_page_reader_keeps_plain_text_body_unchanged() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="  Plain title-like text\nwith body evidence.  ",
        )
    )
    reader = SafeHttpPageReader(transport=transport, target_validator=validated_target)

    page = reader.read("https://example.com/plain")

    assert page.text == "Plain title-like text\nwith body evidence."


@pytest.mark.parametrize(
    "content_type",
    [
        "application/octet-stream; profile=text/html",
        "application/pdf; note=text/plain",
    ],
)
def test_page_reader_rejects_allowed_type_only_in_parameter(content_type: str) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": content_type},
            content=b"not an approved web media type",
        )
    )
    reader = SafeHttpPageReader(transport=transport, target_validator=validated_target)

    with pytest.raises(ValueError, match="unsupported content type"):
        reader.read("https://example.com/payload.bin")


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


def test_page_reader_tries_other_address_family_before_budget_expires() -> None:
    elapsed = [0.0]
    attempts: list[str] = []
    connect_timeouts: list[float] = []
    resolved = [
        (
            socket.AF_INET6,
            socket.SOCK_STREAM,
            6,
            "",
            ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0),
        ),
        (
            socket.AF_INET6,
            socket.SOCK_STREAM,
            6,
            "",
            ("2001:4860:4860::8888", 443, 0, 0),
        ),
        (
            socket.AF_INET6,
            socket.SOCK_STREAM,
            6,
            "",
            ("2606:4700:4700::1111", 443, 0, 0),
        ),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2620:fe::fe", 443, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.host)
        connect_timeouts.append(request.extensions["timeout"]["connect"])
        if ":" in request.url.host:
            elapsed[0] += 2.0
            raise httpx.ConnectError("IPv6 path unavailable", request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="IPv4 fallback works",
        )

    reader = SafeHttpPageReader(
        connection_budget_seconds=5.0,
        clock=lambda: elapsed[0],
        transport=httpx.MockTransport(handler),
        target_validator=lambda url: validate_public_http_target(
            url,
            resolver=lambda *_: resolved,
        ),
    )

    page = reader.read("https://example.com/dual-stack")

    assert attempts == ["2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34"]
    assert connect_timeouts == [5.0, 3.0]
    assert page.text == "IPv4 fallback works"


@pytest.mark.parametrize(
    "connection_budget_seconds",
    [0.0, -1.0, float("inf"), float("nan")],
)
def test_page_reader_rejects_invalid_connection_budget(
    connection_budget_seconds: float,
) -> None:
    with pytest.raises(ValueError, match="connection_budget_seconds must be positive and finite"):
        SafeHttpPageReader(connection_budget_seconds=connection_budget_seconds)


def test_page_reader_does_not_connect_after_validation_exhausts_budget() -> None:
    elapsed = [0.0]
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.host)
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="too late")

    def target(url: str) -> ValidatedHttpUrl:
        elapsed[0] += 6.0
        return validated_target(url)

    reader = SafeHttpPageReader(
        connection_budget_seconds=5.0,
        clock=lambda: elapsed[0],
        transport=httpx.MockTransport(handler),
        target_validator=target,
    )

    with pytest.raises(TimeoutError, match="page connection attempt budget exhausted"):
        reader.read("https://example.com/slow-validation")

    assert attempts == []


def test_page_reader_bounds_address_attempts_by_shared_connection_budget() -> None:
    elapsed = [0.0]
    attempts: list[str] = []
    connect_timeouts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.host)
        connect_timeouts.append(request.extensions["timeout"]["connect"])
        elapsed[0] += 2.0
        raise httpx.ConnectError("address unavailable", request=request)

    def target(url: str) -> ValidatedHttpUrl:
        return ValidatedHttpUrl(
            url=url,
            hostname="example.com",
            port=443,
            addresses=tuple(f"93.184.216.{suffix}" for suffix in range(34, 39)),
        )

    reader = SafeHttpPageReader(
        timeout_seconds=10.0,
        connection_budget_seconds=5.0,
        clock=lambda: elapsed[0],
        transport=httpx.MockTransport(handler),
        target_validator=target,
    )

    with pytest.raises(TimeoutError, match="page connection attempt budget exhausted"):
        reader.read("https://example.com/unavailable")

    assert attempts == ["93.184.216.34", "93.184.216.35", "93.184.216.36"]
    assert connect_timeouts == [5.0, 3.0, 1.0]


def test_page_reader_shares_connection_budget_across_redirects() -> None:
    elapsed = [0.0]
    connect_timeouts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        connect_timeouts.append(request.extensions["timeout"]["connect"])
        if request.url.path == "/start":
            elapsed[0] += 4.0
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="redirected within budget",
        )

    reader = SafeHttpPageReader(
        timeout_seconds=10.0,
        connection_budget_seconds=5.0,
        clock=lambda: elapsed[0],
        transport=httpx.MockTransport(handler),
        target_validator=validated_target,
    )

    page = reader.read("https://example.com/start")

    assert page.text == "redirected within budget"
    assert connect_timeouts == [5.0, 1.0]


class OneResultSearch:
    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        return [SearchHit("Official docs", "https://example.com/docs", "Agent API")]


class SuccessfulReader:
    def read(self, url: str) -> Page:
        return Page("Official docs", url, "Supported evidence", datetime.now(UTC))


def test_agent_backend_sets_explicit_graph_execution_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_configs: list[dict[str, object] | None] = []

    class FakeAgent:
        def invoke(
            self,
            payload: dict[str, object],
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            observed_configs.append(config)
            return {"messages": [AIMessage(content="Short answer")]}

    monkeypatch.setattr("agent_learn.adapters.create_agent", lambda **_kwargs: FakeAgent())
    backend = LangChainAgentBackend(object())  # type: ignore[arg-type]
    tools = ResearchTools(OneResultSearch(), SuccessfulReader(), url_validator=lambda url: url)

    answer = backend.answer("What is the API?", tools)

    assert answer == "Short answer"
    assert observed_configs == [{"recursion_limit": 100, "max_concurrency": 1}]


def test_agent_backend_initial_prompt_matches_grounding_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_system_prompts: list[str] = []

    class FakeAgent:
        def invoke(
            self,
            payload: dict[str, object],
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            return {"messages": [AIMessage(content="Short answer")]}

    def fake_create_agent(**kwargs: object) -> FakeAgent:
        observed_system_prompts.append(str(kwargs["system_prompt"]))
        return FakeAgent()

    monkeypatch.setattr("agent_learn.adapters.create_agent", fake_create_agent)
    backend = LangChainAgentBackend(object())  # type: ignore[arg-type]
    tools = ResearchTools(OneResultSearch(), SuccessfulReader(), url_validator=lambda url: url)

    backend.answer("What is the API?", tools)

    assert len(observed_system_prompts) == 1
    normalized_prompt = " ".join(observed_system_prompts[0].split())
    assert "Every prose paragraph, list item, and Markdown table data row" in normalized_prompt
    assert "chosen only from sources you successfully read" in normalized_prompt


@pytest.mark.parametrize(
    "draft",
    [
        "Uncited draft",
        "Unsupported claim.\n\nSupported claim. [S1]",
        "# Structural citation [S1]\n\n```text\n[S1]\n```",
        "Unsupported claim.\n<!-- [S1] -->",
        "Unsupported claim.\n<!-- [S1]",
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
        def invoke(
            self,
            payload: dict[str, object],
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            assert config == {"recursion_limit": 100, "max_concurrency": 1}
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
    assert tools.warnings == []


def test_agent_backend_repairs_language_for_chinese_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = ResearchTools(OneResultSearch(), SuccessfulReader(), url_validator=lambda url: url)
    tools.search_web("official docs")
    tools.read_source("S1")
    model_invocations: list[object] = []

    class FakeAgent:
        def invoke(
            self,
            payload: dict[str, object],
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            assert config == {"recursion_limit": 100, "max_concurrency": 1}
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
    assert tools.warnings == []


def test_agent_backend_warns_when_language_repair_still_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = ResearchTools(OneResultSearch(), SuccessfulReader(), url_validator=lambda url: url)
    tools.search_web("official docs")
    tools.read_source("S1")

    class FakeAgent:
        def invoke(
            self,
            payload: dict[str, object],
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            return {"messages": [AIMessage(content="English draft [S1]")]}

    class FakeModel:
        def invoke(self, messages: object) -> AIMessage:
            return AIMessage(content="Still English [S1]")

    monkeypatch.setattr("agent_learn.adapters.create_agent", lambda **_kwargs: FakeAgent())
    backend = LangChainAgentBackend(FakeModel())  # type: ignore[arg-type]

    answer = backend.answer("这个 API 是什么？", tools)

    assert answer == "Still English [S1]"
    assert tools.warnings == ["agent answer remained non-Chinese after one repair pass"]


def test_normal_agent_and_repair_override_globally_enabled_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    get_env_var.cache_clear()
    tools = ResearchTools(OneResultSearch(), SuccessfulReader(), url_validator=lambda url: url)
    tools.search_web("official docs")
    tools.read_source("S1")
    observed_states: list[bool | str] = []

    class FakeAgent:
        def invoke(
            self,
            payload: dict[str, object],
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            assert config == {"recursion_limit": 100, "max_concurrency": 1}
            observed_states.append(tracing_is_enabled())
            return {"messages": [AIMessage(content="Uncited draft")]}

    class FakeModel:
        def invoke(self, messages: object) -> AIMessage:
            observed_states.append(tracing_is_enabled())
            return AIMessage(content="Revised answer. [S1]")

    monkeypatch.setattr("agent_learn.adapters.create_agent", lambda **_kwargs: FakeAgent())
    backend = LangChainAgentBackend(FakeModel())  # type: ignore[arg-type]

    try:
        answer = backend.answer("What is the API?", tools)
        restored_state = tracing_is_enabled()
    finally:
        get_env_var.cache_clear()

    assert answer == "Revised answer. [S1]"
    assert observed_states == [False, False]
    assert restored_state is True


def test_synthetic_opt_in_sets_tracing_project_and_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = ResearchTools(OneResultSearch(), SuccessfulReader(), url_validator=lambda url: url)
    observed_contexts: list[dict[str, object]] = []

    class FakeAgent:
        def invoke(
            self,
            payload: dict[str, object],
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            assert config == {"recursion_limit": 100, "max_concurrency": 1}
            observed_contexts.append(get_tracing_context())
            return {"messages": [AIMessage(content="Synthetic answer")]}

    monkeypatch.setattr("agent_learn.adapters.create_agent", lambda **_kwargs: FakeAgent())
    backend = LangChainAgentBackend(  # type: ignore[arg-type]
        object(), trace_enabled=True, trace_project="agent-learn-test"
    )

    answer = backend.answer("Synthetic case", tools)

    assert answer == "Synthetic answer"
    assert len(observed_contexts) == 1
    assert observed_contexts[0]["enabled"] is True
    assert observed_contexts[0]["project_name"] == "agent-learn-test"
    assert observed_contexts[0]["tags"] == ["synthetic"]
