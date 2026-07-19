from datetime import UTC, datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest

from agent_learn.domain import ResearchReport, ResearchRequest, Source

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
            warnings=["Search failed"],
        )


def build_app(service: object) -> AppTest:
    app = AppTest.from_file(APP_PATH)
    app.session_state["_agent_learn_service"] = service
    return app.run()


def test_ui_renders_report_and_source() -> None:
    app = build_app(SuccessfulService())

    app.chat_input[0].set_value("LangChain").run()

    markdown = "\n".join(element.value for element in app.markdown)
    assert "关于 **LangChain** 的答案。[S1]" in markdown
    assert "Official docs" in markdown
    assert "https://example.com/docs" in markdown
    assert not app.exception


def test_ui_renders_fail_closed_warning() -> None:
    app = build_app(WarningService())

    app.chat_input[0].set_value("LangChain").run()

    assert any("Search failed" in warning.value for warning in app.warning)
    assert any("无法生成有来源支持的研究报告" in item.value for item in app.markdown)
    assert not app.exception
