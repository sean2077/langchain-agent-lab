from pathlib import Path

import pytest

from examples.deep_agent import build_deep_agent
from examples.langchain_agent import build_langchain_agent
from examples.langgraph_workflow import run_interrupt_demo
from examples.langsmith_trace import SYNTHETIC_CASES

ROOT = Path(__file__).parents[2]


def test_langchain_example_builds_without_calling_model() -> None:
    agent = build_langchain_agent()

    assert agent.name == "langchain_minimal_agent"


@pytest.mark.parametrize(
    ("approved", "expected_status"),
    [(True, "published"), (False, "rejected")],
)
def test_langgraph_example_interrupts_and_resumes(approved: bool, expected_status: str) -> None:
    interrupted, completed = run_interrupt_demo(approved=approved)

    assert interrupted["__interrupt__"]
    assert completed["approved"] is approved
    assert completed["status"] == expected_status


def test_deep_agent_example_builds_without_calling_model() -> None:
    agent = build_deep_agent()

    assert agent.name == "deep_agent_minimal"


def test_langsmith_example_only_exposes_fixed_synthetic_cases() -> None:
    assert set(SYNTHETIC_CASES) == {"langchain-overview", "tool-selection", "local-agent"}
    assert all("private" not in question.lower() for question in SYNTHETIC_CASES.values())


def test_learning_docs_cover_ecosystem_and_three_scenarios() -> None:
    ecosystem = (ROOT / "docs" / "ecosystem-map.md").read_text()
    learning_path = (ROOT / "docs" / "learning-path.md").read_text()

    for term in ("LangChain", "LangGraph", "LangSmith", "Deep Agents", "Dify"):
        assert term in ecosystem
    assert learning_path.count("### 场景") == 3
