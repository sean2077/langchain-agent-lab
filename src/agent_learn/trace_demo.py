"""Explicit opt-in entry point for hosted LangSmith synthetic traces."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from agent_learn.bootstrap import build_research_service
from agent_learn.cli import run_cli, strip_terminal_controls
from agent_learn.config import ConfigurationError

SYNTHETIC_CASES = {
    "langchain-overview": "What is LangChain v1, according to its official documentation?",
    "tool-selection": "When should a developer use LangGraph instead of LangChain create_agent?",
    "local-agent": "What capabilities does the official ChatOllama integration support?",
}


def run_trace_demo(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Send one fixed, non-sensitive synthetic research trace to LangSmith"
    )
    parser.add_argument("--case", choices=sorted(SYNTHETIC_CASES), required=True)
    args = parser.parse_args(list(argv))
    if not os.getenv("LANGSMITH_API_KEY"):
        print("LANGSMITH_API_KEY is required for the synthetic trace demo.", file=sys.stderr)
        return 2
    try:
        service = build_research_service(trace_enabled=True)
    except ConfigurationError as error:
        sys.stderr.write(strip_terminal_controls(f"error: {error}\n"))
        return 2
    return run_cli(
        [SYNTHETIC_CASES[args.case]],
        service=service,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def main() -> None:
    raise SystemExit(run_trace_demo(sys.argv[1:]))


if __name__ == "__main__":
    main()
