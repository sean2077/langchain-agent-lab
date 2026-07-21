"""Local-only Streamlit interface."""

from __future__ import annotations

import streamlit as st

from agent_learn.bootstrap import build_research_service
from agent_learn.cli import Researcher
from agent_learn.config import ConfigurationError
from agent_learn.domain import ResearchReport, ResearchRequest, remove_markdown_link_targets

_SERVICE_KEY = "_agent_learn_service"
_HISTORY_KEY = "_agent_learn_history"


def _source_link_label(source_id: str, title: str) -> str:
    safe_title, _ = remove_markdown_link_targets(title)
    return f"[{source_id}] {safe_title or 'Source'}"


@st.cache_resource(show_spinner=False)
def _default_service() -> Researcher:
    # Normal UI runs are intentionally never traced to hosted LangSmith.
    return build_research_service(trace_enabled=False)


def _render_report(report: ResearchReport) -> None:
    st.markdown(report.answer_markdown)
    if report.sources:
        st.markdown("#### 来源")
        for source in report.sources:
            st.link_button(
                _source_link_label(source.source_id, source.title),
                source.url,
                type="tertiary",
            )
    for warning in report.warnings:
        st.warning("研究过程中出现警告，详情如下：")
        st.code(warning, language=None, wrap_lines=True)


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
        try:
            service = _default_service()
        except ConfigurationError as error:
            st.error("运行时配置无效，详情如下：")
            st.code(str(error), language=None, wrap_lines=True)
            return
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
                st.error("研究流程失败，详情如下：")
                st.code(str(exc), language=None, wrap_lines=True)
                return
            if report.is_source_grounded:
                status.update(label="研究完成", state="complete", expanded=False)
            else:
                status.update(label="研究未完成", state="error", expanded=False)
        _render_report(report)

    history.append(
        {
            "question": question,
            "report": report.model_dump(mode="json"),
        }
    )
