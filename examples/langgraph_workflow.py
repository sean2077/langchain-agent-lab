"""LangGraph v1: state, branching, checkpointing and interrupt/resume."""

from __future__ import annotations

from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ReviewState(TypedDict, total=False):
    topic: str
    draft: str
    needs_review: bool
    approved: bool
    status: str


def draft_report(state: ReviewState) -> ReviewState:
    return {
        "draft": f"Draft report about {state['topic']}",
        "needs_review": True,
        "status": "drafted",
    }


def request_review(state: ReviewState) -> ReviewState:
    approved = bool(interrupt({"question": "Publish this draft?", "draft": state["draft"]}))
    return {"approved": approved}


def publish(_: ReviewState) -> ReviewState:
    return {"status": "published"}


def reject(_: ReviewState) -> ReviewState:
    return {"status": "rejected"}


def route_draft(state: ReviewState) -> str:
    return "review" if state["needs_review"] else "publish"


def route_review(state: ReviewState) -> str:
    return "publish" if state["approved"] else "reject"


def build_review_graph():
    graph = StateGraph(ReviewState)
    graph.add_node("draft", draft_report)
    graph.add_node("review", request_review)
    graph.add_node("publish", publish)
    graph.add_node("reject", reject)
    graph.add_edge(START, "draft")
    graph.add_conditional_edges(
        "draft",
        route_draft,
        {"review": "review", "publish": "publish"},
    )
    graph.add_conditional_edges(
        "review",
        route_review,
        {"publish": "publish", "reject": "reject"},
    )
    graph.add_edge("publish", END)
    graph.add_edge("reject", END)
    return graph.compile(checkpointer=InMemorySaver(), name="review_workflow")


def run_interrupt_demo(*, approved: bool) -> tuple[dict, dict]:
    app = build_review_graph()
    config = {"configurable": {"thread_id": str(uuid4())}}
    interrupted = app.invoke({"topic": "LangGraph"}, config=config)
    completed = app.invoke(Command(resume=approved), config=config)
    return interrupted, completed


def main() -> None:
    interrupted, completed = run_interrupt_demo(approved=True)
    print("Interrupted:", interrupted["__interrupt__"])
    print("Completed:", completed)


if __name__ == "__main__":
    main()
