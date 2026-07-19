"""Command-line interface for the same core service used by the UI."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Protocol, TextIO

from agent_learn.bootstrap import build_research_service
from agent_learn.domain import ResearchReport, ResearchRequest


class Researcher(Protocol):
    def research(self, request: ResearchRequest) -> ResearchReport: ...


def run_cli(
    argv: Sequence[str],
    *,
    service: Researcher,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    parser = argparse.ArgumentParser(description="Run the local source-grounded research agent")
    parser.add_argument("question", nargs="+", help="research question")
    parser.add_argument("--json", action="store_true", help="emit the complete report as JSON")
    args = parser.parse_args(list(argv))

    report = service.research(ResearchRequest(question=" ".join(args.question)))
    if args.json:
        stdout.write(report.model_dump_json(indent=2) + "\n")
    else:
        stdout.write(report.answer_markdown.rstrip() + "\n")
        if report.sources:
            stdout.write("\nSources\n")
            for source in report.sources:
                stdout.write(f"- [{source.source_id}] {source.title} — {source.url}\n")
    for warning in report.warnings:
        stderr.write(f"warning: {warning}\n")
    return 0 if report.cited_source_ids else 2


def main() -> None:
    raise SystemExit(
        run_cli(
            sys.argv[1:],
            service=build_research_service(trace_enabled=False),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    )


if __name__ == "__main__":
    main()
