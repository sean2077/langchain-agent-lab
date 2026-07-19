"""Local-only Streamlit interface."""

from __future__ import annotations

import streamlit as st

from agent_learn.bootstrap import build_research_service
from agent_learn.cli import Researcher
from agent_learn.domain import ResearchReport, ResearchRequest

_SERVICE_KEY = "_agent_learn_service"
_HISTORY_KEY = "_agent_learn_history"


@st.cache_resource(show_spinner=False)
def _default_service() -> Researcher:
    # Normal UI runs are intentionally never traced to hosted LangSmith.
    return build_research_service(trace_enabled=False)


def _escape_markdown(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _render_report(report: ResearchReport) -> None:
    st.markdown(report.answer_markdown)
    if report.sources:
        st.markdown("#### 来源")
        for source in report.sources:
            title = _escape_markdown(source.title)
            st.markdown(f"- `[{source.source_id}]` [{title}]({source.url})")
    for warning in report.warnings:
        st.warning(warning)


def _render_exchange(question: str, report: ResearchReport) -> None:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        _render_report(report)


def run_app() -> None:
    st.set_page_config(page_title="Local Research Agent", page_icon="🔎")
    st.title("本地资料研究 Agent")
    st.caption("Ollama + LangChain · 只读搜索 · 来源可追溯 · 正常 UI 不上传 trace")

    service = st.session_state.get(_SERVICE_KEY)
    if service is None:
        service = _default_service()
        st.session_state[_SERVICE_KEY] = service

    history: list[dict[str, object]] = st.session_state.setdefault(_HISTORY_KEY, [])
    for item in history:
        _render_exchange(
            str(item["question"]),
            ResearchReport.model_validate(item["report"]),
        )

    question = st.chat_input("输入一个需要查证的研究问题")
    if not question:
        return

    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.status("正在搜索并核对来源…", expanded=True) as status:
            try:
                report = service.research(ResearchRequest(question=question))
            except Exception as exc:  # keep the local UI usable at the outermost boundary
                status.update(label="研究失败", state="error")
                st.error(f"研究流程失败：{exc}")
                return
            status.update(label="研究完成", state="complete", expanded=False)
        _render_report(report)

    history.append(
        {
            "question": question,
            "report": report.model_dump(mode="json"),
        }
    )
