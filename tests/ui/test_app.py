from datetime import UTC, datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest

from agent_learn.domain import ResearchOutcome, ResearchReport, ResearchRequest, Source

APP_PATH = Path(__file__).parents[2] / "streamlit_app.py"


class SuccessfulService:
    def research(self, request: ResearchRequest) -> ResearchReport:
        return ResearchReport(
            answer_markdown=f"关于 **{request.question}** 的答案。[S1]",
            sources=[
                Source(
                    source_id="S1",
                    title="Official docs",
                    url="https://example.com/docs",
                    retrieved_at=datetime.now(UTC),
                )
            ],
        )


class WarningService:
    def research(self, request: ResearchRequest) -> ResearchReport:
        return ResearchReport(
            answer_markdown="无法生成有来源支持的研究报告。",
            outcome=ResearchOutcome.INSUFFICIENT_EVIDENCE,
            warnings=["Search failed"],
        )


class GroundedWarningService(SuccessfulService):
    def research(self, request: ResearchRequest) -> ResearchReport:
        report = super().research(request)
        return report.model_copy(update={"warnings": ["Citation marker normalized"]})


class MarkdownInjectionService:
    source_url = "https://example.com/) [Injected](https://attacker.example"

    def research(self, request: ResearchRequest) -> ResearchReport:
        return ResearchReport(
            answer_markdown="Grounded answer. [S1]",
            sources=[
                Source(
                    source_id="S1",
                    title="Official [docs]",
                    url=self.source_url,
                    retrieved_at=datetime.now(UTC),
                )
            ],
        )


class ActiveTitleService:
    source_title = (
        "Official [injected](https://attacker.example) ![pixel](https://tracker.example/p.gif)"
    )

    def research(self, request: ResearchRequest) -> ResearchReport:
        return ResearchReport(
            answer_markdown="Grounded answer. [S1]",
            sources=[
                Source(
                    source_id="S1",
                    title=self.source_title,
                    url="https://example.com/docs",
                    retrieved_at=datetime.now(UTC),
                )
            ],
        )


class DestinationOnlyTitleService(ActiveTitleService):
    source_title = "https://tracker.example/p.gif"


class MarkdownDiagnosticService:
    payload = "[Injected](https://attacker.example)"

    def research(self, request: ResearchRequest) -> ResearchReport:
        return ResearchReport(
            answer_markdown="无法生成有来源支持的研究报告。",
            outcome=ResearchOutcome.INVALID_REPORT,
            warnings=[self.payload],
        )


class MarkdownExceptionService:
    def research(self, request: ResearchRequest) -> ResearchReport:
        raise RuntimeError(MarkdownDiagnosticService.payload)


def build_app(service: object) -> AppTest:
    app = AppTest.from_file(APP_PATH)
    app.session_state["_agent_learn_service"] = service
    return app.run()


def test_ui_renders_report_and_source() -> None:
    app = build_app(SuccessfulService())

    app.chat_input[0].set_value("LangChain").run()

    markdown = "\n".join(element.value for element in app.markdown)
    links = app.get("link_button")
    assert "关于 **LangChain** 的答案。[S1]" in markdown
    assert len(links) == 1
    assert links[0].label == "[S1] Official docs"
    assert links[0].url == "https://example.com/docs"
    assert app.status[0].label == "研究完成"
    assert app.status[0].state == "complete"
    assert not app.exception


def test_ui_renders_fail_closed_warning() -> None:
    app = build_app(WarningService())

    app.chat_input[0].set_value("LangChain").run()

    assert app.status[0].label == "研究未完成"
    assert app.status[0].state == "error"
    assert [warning.value for warning in app.warning] == ["研究过程中出现警告，详情如下："]
    assert any("Search failed" in detail.value for detail in app.code)
    assert any("无法生成有来源支持的研究报告" in item.value for item in app.markdown)
    assert not app.exception


def test_ui_does_not_treat_warning_alone_as_failure() -> None:
    app = build_app(GroundedWarningService())

    app.chat_input[0].set_value("LangChain").run()

    assert app.status[0].label == "研究完成"
    assert app.status[0].state == "complete"
    assert [warning.value for warning in app.warning] == ["研究过程中出现警告，详情如下："]
    assert any("Citation marker normalized" in detail.value for detail in app.code)
    assert not app.exception


def test_ui_keeps_source_url_out_of_markdown_syntax() -> None:
    app = build_app(MarkdownInjectionService())

    app.chat_input[0].set_value("LangChain").run()

    links = app.get("link_button")
    assert len(links) == 1
    assert links[0].label == "[S1] Official [docs]"
    assert links[0].url == MarkdownInjectionService.source_url
    assert all("attacker.example" not in element.value for element in app.markdown)
    assert not app.exception


def test_ui_removes_link_targets_from_source_title() -> None:
    app = build_app(ActiveTitleService())

    app.chat_input[0].set_value("LangChain").run()

    link = app.get("link_button")[0]
    assert link.label == "[S1] Official injected pixel"
    assert link.url == "https://example.com/docs"
    assert not app.exception


def test_ui_uses_fixed_title_when_source_title_is_only_a_destination() -> None:
    app = build_app(DestinationOnlyTitleService())

    app.chat_input[0].set_value("LangChain").run()

    link = app.get("link_button")[0]
    assert link.label == "[S1] Source"
    assert link.url == "https://example.com/docs"
    assert not app.exception


def test_ui_keeps_warning_detail_out_of_markdown_alert() -> None:
    app = build_app(MarkdownDiagnosticService())

    app.chat_input[0].set_value("LangChain").run()

    assert [item.value for item in app.warning] == ["研究过程中出现警告，详情如下："]
    assert app.code[-1].value == MarkdownDiagnosticService.payload
    assert all("attacker.example" not in item.value for item in app.warning)
    assert all("attacker.example" not in item.value for item in app.markdown)
    assert not app.exception


def test_ui_keeps_exception_detail_out_of_markdown_alert() -> None:
    app = build_app(MarkdownExceptionService())

    app.chat_input[0].set_value("LangChain").run()

    assert app.status[0].label == "研究失败"
    assert app.status[0].state == "error"
    assert [item.value for item in app.error] == ["研究流程失败，详情如下："]
    assert app.code[-1].value == MarkdownDiagnosticService.payload
    assert all("attacker.example" not in item.value for item in app.error)
    assert all("attacker.example" not in item.value for item in app.markdown)
    assert not app.exception


def test_ui_handles_invalid_runtime_configuration(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://model.example.invalid")

    app = AppTest.from_file(APP_PATH).run()

    assert [item.value for item in app.error] == ["运行时配置无效，详情如下："]
    assert app.code[-1].value == "OLLAMA_BASE_URL must target a loopback address"
    assert not app.exception
