"""Command-line interface for the same core service used by the UI."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from typing import Protocol, TextIO

from pydantic import ValidationError

from agent_learn.bootstrap import build_research_service
from agent_learn.config import ConfigurationError
from agent_learn.domain import ResearchReport, ResearchRequest

_TERMINAL_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def strip_terminal_controls(value: str) -> str:
    """Remove active terminal controls while preserving tabs, newlines, and text."""

    return _TERMINAL_CONTROL_PATTERN.sub("", value)


def escape_terminal_controls(value: str) -> str:
    """Keep serialized data recoverable without emitting raw terminal controls."""

    return _TERMINAL_CONTROL_PATTERN.sub(lambda match: f"\\u{ord(match.group()):04x}", value)


class Researcher(Protocol):
    def research(self, request: ResearchRequest) -> ResearchReport: ...


def run_cli(
    argv: Sequence[str],
    *,
    stdout: TextIO,
    stderr: TextIO,
    service: Researcher | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Run the local source-grounded research agent")
    parser.add_argument("question", nargs="+", help="research question")
    parser.add_argument("--json", action="store_true", help="emit the complete report as JSON")
    args = parser.parse_args(list(argv))

    try:
        request = ResearchRequest(question=" ".join(args.question))
    except ValidationError:
        stderr.write("error: question must contain between 1 and 4000 non-whitespace characters\n")
        return 2

    if service is None:
        try:
            service = build_research_service(trace_enabled=False)
        except ConfigurationError as error:
            stderr.write(strip_terminal_controls(f"error: {error}\n"))
            return 2

    report = service.research(request)
    if args.json:
        stdout.write(escape_terminal_controls(report.model_dump_json(indent=2)) + "\n")
    else:
        stdout.write(strip_terminal_controls(report.answer_markdown.rstrip()) + "\n")
        if report.sources:
            stdout.write("\nSources\n")
            for source in report.sources:
                stdout.write(
                    strip_terminal_controls(
                        f"- [{source.source_id}] {source.title} — {source.url}\n"
                    )
                )
    for warning in report.warnings:
        stderr.write(strip_terminal_controls(f"warning: {warning}\n"))
    return 0 if report.is_source_grounded else 2


def main() -> None:
    raise SystemExit(
        run_cli(
            sys.argv[1:],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    )


if __name__ == "__main__":
    main()
