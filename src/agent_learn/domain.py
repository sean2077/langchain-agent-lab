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


def extract_citation_ids(markdown: str) -> list[str]:
    """Return unique citation ids in first-seen order."""

    return list(dict.fromkeys(_CITATION_PATTERN.findall(markdown)))


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

        unknown = sorted(set(self.cited_source_ids) - set(source_ids))
        if unknown:
            raise ValueError(f"unknown source ids: {', '.join(unknown)}")
        return self

    @property
    def cited_source_ids(self) -> list[str]:
        return extract_citation_ids(self.answer_markdown)
