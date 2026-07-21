"""Stable public data contracts for research requests and reports."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CITATION_PATTERN = re.compile(r"\[(S[1-9]\d*)\]")
_CITATION_LABEL_PATTERN = re.compile(r"S[1-9]\d*")
_LOOSE_CITATION_PATTERN = re.compile(r"\[\s*(S[1-9]\d*)\s*\]")
_BARE_CITATION_PATTERN = re.compile(
    r"(?<![\[\w])S([1-9]\d*)(?![\]\w])(?=\s*(?:[，。；：,.!?、）)'\"”’\n]|\||$))"
)
_INLINE_LINK_PATTERN = re.compile(r"(?<!\\)!?\[([^\]\n]*)\]\((?:[^()\n]|\([^()\n]*\))*\)")
_REFERENCE_LINK_PATTERN = re.compile(r"(?<!\\)!?\[([^\]\n]*)\]\[[^\]\n]*\]")
_REFERENCE_DEFINITION_PATTERN = re.compile(r"(?m)^[ \t]{0,3}\[[^\]\n]+\]:[ \t]+\S+[^\n]*$")
_ATX_HEADING_PATTERN = re.compile(r"^[ \t]{0,3}#{1,6}(?:[ \t]+|$)")
_SETEXT_HEADING_PATTERN = re.compile(r"^[ \t]{0,3}(?:=+|-+)[ \t]*$")
_THEMATIC_BREAK_PATTERN = re.compile(
    r"^[ \t]{0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$"
)
_FENCE_PATTERN = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_LIST_ITEM_PATTERN = re.compile(r"^[ \t]*(?:[-+*]|\d+[.)])[ \t]+")
_TABLE_SEPARATOR_PATTERN = re.compile(
    r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*$"
)


def extract_citation_ids(markdown: str) -> list[str]:
    """Return unique citation ids in first-seen order."""

    return list(dict.fromkeys(_CITATION_PATTERN.findall(markdown)))


def count_uncited_content_blocks(markdown: str) -> int:
    """Count prose, list items and table rows without a canonical citation.

    This is a deliberately syntactic coverage check, not a claim-support or
    entailment evaluator. Markdown headings, separators and fenced code are
    structural and therefore excluded.
    """

    return sum(not extract_citation_ids(block) for block in _citation_content_blocks(markdown))


def has_citable_content(markdown: str) -> bool:
    """Return whether Markdown contains prose, a list item or a table data row."""

    return bool(_citation_content_blocks(markdown))


def _citation_content_blocks(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    current_is_list_item = False
    fence_character = ""
    fence_length = 0
    in_table = False

    def flush_current() -> None:
        nonlocal current_is_list_item
        if current:
            blocks.append("\n".join(current))
            current.clear()
        current_is_list_item = False

    index = 0
    while index < len(lines):
        stripped = lines[index].strip()

        if fence_character:
            if len(stripped) >= fence_length and set(stripped) == {fence_character}:
                fence_character = ""
                fence_length = 0
            index += 1
            continue

        fence_match = _FENCE_PATTERN.match(lines[index])
        if fence_match:
            flush_current()
            delimiter = fence_match.group(1)
            fence_character = delimiter[0]
            fence_length = len(delimiter)
            in_table = False
            index += 1
            continue

        if not stripped:
            flush_current()
            in_table = False
            index += 1
            continue

        next_stripped = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if (
            not current_is_list_item
            and not _LIST_ITEM_PATTERN.match(lines[index])
            and "|" in stripped
            and _TABLE_SEPARATOR_PATTERN.fullmatch(next_stripped)
        ):
            flush_current()
            in_table = True
            index += 2
            continue

        if (
            not current_is_list_item
            and not _LIST_ITEM_PATTERN.match(lines[index])
            and _SETEXT_HEADING_PATTERN.fullmatch(next_stripped)
        ):
            current.clear()
            current_is_list_item = False
            in_table = False
            index += 2
            continue

        if in_table:
            if "|" in stripped:
                blocks.append(stripped)
                index += 1
                continue
            in_table = False

        if (
            _ATX_HEADING_PATTERN.match(lines[index])
            or _THEMATIC_BREAK_PATTERN.fullmatch(lines[index])
            or _TABLE_SEPARATOR_PATTERN.fullmatch(lines[index])
        ):
            flush_current()
            index += 1
            continue

        if _LIST_ITEM_PATTERN.match(lines[index]):
            flush_current()
            current_is_list_item = True
        current.append(stripped)
        index += 1

    flush_current()
    return blocks


def normalize_citation_markers(markdown: str) -> tuple[str, int]:
    """Canonicalize common local-model variants such as ``S1`` and ``[ S1 ]``."""

    loose_count = 0

    def canonicalize_loose(match: re.Match[str]) -> str:
        nonlocal loose_count
        canonical = f"[{match.group(1)}]"
        if match.group(0) != canonical:
            loose_count += 1
        return canonical

    normalized = _LOOSE_CITATION_PATTERN.sub(canonicalize_loose, markdown)
    normalized, bare_count = _BARE_CITATION_PATTERN.subn(
        lambda match: f"[S{match.group(1)}]", normalized
    )
    return normalized, loose_count + bare_count


def remove_markdown_link_targets(markdown: str) -> tuple[str, int]:
    """Remove model-controlled Markdown destinations while preserving labels."""

    def label_only(match: re.Match[str]) -> str:
        label = match.group(1)
        return f"[{label}]" if _CITATION_LABEL_PATTERN.fullmatch(label) else label

    sanitized, inline_count = _INLINE_LINK_PATTERN.subn(label_only, markdown)
    sanitized, reference_count = _REFERENCE_LINK_PATTERN.subn(label_only, sanitized)
    sanitized, definition_count = _REFERENCE_DEFINITION_PATTERN.subn("", sanitized)
    return sanitized.strip(), inline_count + reference_count + definition_count


class ResearchRequest(BaseModel):
    """A single research task submitted by a user."""

    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1, max_length=4_000)

    @field_validator("question", mode="before")
    @classmethod
    def normalize_question(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class Source(BaseModel):
    """A public source collected by read-only research tools."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(pattern=r"^S[1-9]\d*$")
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2_048)
    retrieved_at: datetime


class ResearchReport(BaseModel):
    """A source-grounded answer safe for CLI and UI rendering."""

    model_config = ConfigDict(frozen=True)

    answer_markdown: str = Field(min_length=1)
    sources: list[Source] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_references(self) -> ResearchReport:
        _, noncanonical_citation_count = normalize_citation_markers(self.answer_markdown)
        if noncanonical_citation_count:
            raise ValueError("citation markers must use canonical [S#] form")

        _, link_target_count = remove_markdown_link_targets(self.answer_markdown)
        if link_target_count:
            raise ValueError(
                "Markdown link targets are not allowed in answer_markdown; "
                "render registered sources separately"
            )

        source_ids = [source.source_id for source in self.sources]
        duplicates = sorted(
            source_id for source_id in set(source_ids) if source_ids.count(source_id) > 1
        )
        if duplicates:
            raise ValueError(f"duplicate source ids: {', '.join(duplicates)}")

        cited_source_ids = self.cited_source_ids
        unknown = sorted(set(cited_source_ids) - set(source_ids))
        if unknown:
            raise ValueError(f"unknown source ids: {', '.join(unknown)}")

        if cited_source_ids:
            if not has_citable_content(self.answer_markdown):
                raise ValueError("answer contains no citable content block")
            uncited_content_blocks = count_uncited_content_blocks(self.answer_markdown)
            if uncited_content_blocks:
                raise ValueError(f"{uncited_content_blocks} uncited content block(s)")
        return self

    @property
    def cited_source_ids(self) -> list[str]:
        return extract_citation_ids(self.answer_markdown)
