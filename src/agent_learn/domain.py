"""Stable public data contracts for research requests and reports."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CITATION_PATTERN = re.compile(r"\[(S[1-9]\d*)\]")
_CITATION_LABEL_PATTERN = re.compile(r"S[1-9]\d*")
_LOOSE_CITATION_PATTERN = re.compile(r"\[\s*(S[1-9]\d*)\s*\]")
_BARE_CITATION_PATTERN = re.compile(
    r"(?<![\[\w])S([1-9]\d*)(?![\]\w])(?=\s*(?:[，。；：,.!?、）)'\"”’\n]|\||$))"
)
_REFERENCE_LINK_PATTERN = re.compile(r"(?<!\\)!?\[([^\]\n]*)\]\[[^\]\n]*\]")
_REFERENCE_CONTAINER_PREFIX = r"[ \t]*(?:(?:>[ \t]*)|(?:(?:[-+*]|\d+[.)])[ \t]+))*"
_REFERENCE_DEFINITION_PATTERN = re.compile(
    rf"(?m)^{_REFERENCE_CONTAINER_PREFIX}"
    r"\[(?:\\[^\r\n]|[^\]\\]){1,999}\]:"
    rf"(?:[ \t]*\S[^\r\n]*|[ \t]*\r?\n{_REFERENCE_CONTAINER_PREFIX}\S[^\r\n]*)$"
)
_ANGLE_URI_AUTOLINK_PATTERN = re.compile(
    r"(?<!\\)<[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\x00-\x20\x7f<>]*>"
)
_ANGLE_EMAIL_AUTOLINK_PATTERN = re.compile(
    r"(?<!\\)<[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*>"
)
_GFM_DOMAIN = r"(?:[A-Za-z0-9_-]+\.)*[A-Za-z0-9-]+\.[A-Za-z0-9-]+"
_GFM_URL_AUTOLINK_PATTERN = re.compile(
    rf"(?P<prefix>^|[\s*_~(])(?P<target>(?:https?://|www\.){_GFM_DOMAIN}[^<\s]*)",
    re.IGNORECASE | re.MULTILINE,
)
_GFM_EMAIL = (
    r"[A-Za-z0-9._+-]+@"
    r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.[A-Za-z0-9_-]*[A-Za-z0-9]"
)
_GFM_PROTOCOL_AUTOLINK_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9._+-])(?P<target>(?:mailto:{_GFM_EMAIL}|"
    rf"xmpp:{_GFM_EMAIL}(?:/[A-Za-z0-9@.]*)?))",
    re.IGNORECASE,
)
_GFM_EMAIL_AUTOLINK_PATTERN = re.compile(rf"(?<![A-Za-z0-9._+-]){_GFM_EMAIL}(?![A-Za-z0-9_+-])")
_LINK_WHITESPACE = " \t\r\n\f\v"
_HTML_COMMENT_PATTERN = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
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

SOURCE_TITLE_MAX_CHARACTERS = 500
WARNING_MAX_CHARACTERS = 2_000
_WARNING_TRUNCATION_MARKER = "... [truncated]"


def bounded_warning(warning: str) -> str:
    """Keep an actionable warning prefix within the stable domain limit."""

    if len(warning) <= WARNING_MAX_CHARACTERS:
        return warning
    prefix_length = WARNING_MAX_CHARACTERS - len(_WARNING_TRUNCATION_MARKER)
    return warning[:prefix_length] + _WARNING_TRUNCATION_MARKER


def extract_citation_ids(markdown: str) -> list[str]:
    """Return unique visible citation ids in first-seen order."""

    return list(dict.fromkeys(_CITATION_PATTERN.findall(_without_html_comments(markdown))))


def _without_html_comments(markdown: str) -> str:
    """Exclude non-rendered comments, including an unclosed comment through EOF."""

    return _HTML_COMMENT_PATTERN.sub("", markdown)


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
    lines = _without_html_comments(markdown).splitlines()
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
    """Remove model-controlled Markdown destinations and preserve distinct labels."""

    sanitized, inline_count = _remove_inline_link_targets(markdown)
    sanitized, reference_count = _REFERENCE_LINK_PATTERN.subn(_link_label_only, sanitized)
    sanitized, definition_count = _REFERENCE_DEFINITION_PATTERN.subn("", sanitized)
    sanitized, angle_uri_count = _ANGLE_URI_AUTOLINK_PATTERN.subn("", sanitized)
    sanitized, angle_email_count = _ANGLE_EMAIL_AUTOLINK_PATTERN.subn("", sanitized)
    sanitized, url_count = _GFM_URL_AUTOLINK_PATTERN.subn(_without_extended_autolink, sanitized)
    sanitized, protocol_count = _GFM_PROTOCOL_AUTOLINK_PATTERN.subn(
        _without_extended_autolink, sanitized
    )
    sanitized, email_count = _GFM_EMAIL_AUTOLINK_PATTERN.subn("", sanitized)
    removed_count = sum(
        (
            inline_count,
            reference_count,
            definition_count,
            angle_uri_count,
            angle_email_count,
            url_count,
            protocol_count,
            email_count,
        )
    )
    return sanitized.strip(), removed_count


def _link_label_only(match: re.Match[str]) -> str:
    """Keep a link's visible label, retaining canonical citation brackets."""

    return _link_label(match.group(1))


def _link_label(label: str) -> str:
    return f"[{label}]" if _CITATION_LABEL_PATTERN.fullmatch(label) else label


def _remove_inline_link_targets(markdown: str) -> tuple[str, int]:
    """Remove inline destinations using balanced delimiters rather than fixed depth."""

    sanitized = markdown
    removed_count = 0
    while True:
        sanitized, pass_count = _remove_inline_link_targets_once(sanitized)
        removed_count += pass_count
        if not pass_count:
            return sanitized, removed_count


def _remove_inline_link_targets_once(markdown: str) -> tuple[str, int]:
    pieces: list[str] = []
    output_cursor = 0
    search_cursor = 0
    removed_count = 0

    while (label_start := markdown.find("[", search_cursor)) >= 0:
        if _is_escaped(markdown, label_start):
            search_cursor = label_start + 1
            continue

        label_end = _find_link_label_end(markdown, label_start + 1)
        if label_end is None or label_end + 1 >= len(markdown) or markdown[label_end + 1] != "(":
            search_cursor = label_start + 1
            continue

        destination_end = _find_inline_link_end(markdown, label_end + 2)
        if destination_end is None:
            search_cursor = label_start + 1
            continue

        replacement_start = label_start
        if (
            label_start > 0
            and markdown[label_start - 1] == "!"
            and not _is_escaped(markdown, label_start - 1)
        ):
            replacement_start -= 1
        pieces.append(markdown[output_cursor:replacement_start])
        pieces.append(_link_label(markdown[label_start + 1 : label_end]))
        output_cursor = destination_end + 1
        search_cursor = output_cursor
        removed_count += 1

    pieces.append(markdown[output_cursor:])
    return "".join(pieces), removed_count


def _is_escaped(markdown: str, index: int) -> bool:
    backslash_count = 0
    index -= 1
    while index >= 0 and markdown[index] == "\\":
        backslash_count += 1
        index -= 1
    return bool(backslash_count % 2)


def _find_link_label_end(markdown: str, content_start: int) -> int | None:
    depth = 1
    index = content_start
    while index < len(markdown):
        character = markdown[index]
        if character == "\\" and index + 1 < len(markdown):
            index += 2
            continue
        if character == "`":
            code_span_end = _find_code_span_end(markdown, index)
            if code_span_end is not None:
                index = code_span_end
                continue
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _find_code_span_end(markdown: str, opening_start: int) -> int | None:
    opening_end = opening_start
    while opening_end < len(markdown) and markdown[opening_end] == "`":
        opening_end += 1
    delimiter = markdown[opening_start:opening_end]
    search_start = opening_end
    while (closing_start := markdown.find(delimiter, search_start)) >= 0:
        closing_end = closing_start + len(delimiter)
        if (closing_start == 0 or markdown[closing_start - 1] != "`") and (
            closing_end == len(markdown) or markdown[closing_end] != "`"
        ):
            return closing_end
        search_start = closing_end
    return None


def _find_inline_link_end(markdown: str, content_start: int) -> int | None:
    index = _skip_link_whitespace(markdown, content_start)
    if index >= len(markdown):
        return None
    if markdown[index] == ")":
        return index

    if markdown[index] == "<":
        index = _find_angle_destination_end(markdown, index + 1)
        if index is None:
            return None
    else:
        depth = 0
        while index < len(markdown):
            character = markdown[index]
            if character == "\\" and index + 1 < len(markdown):
                index += 2
                continue
            if character in _LINK_WHITESPACE:
                if depth:
                    return None
                break
            if ord(character) < 0x20 or character in "\x7f<":
                return None
            if character == "(":
                depth += 1
            elif character == ")":
                if depth == 0:
                    return index
                depth -= 1
            index += 1
        if depth:
            return None

    whitespace_start = index
    index = _skip_link_whitespace(markdown, index)
    if index >= len(markdown):
        return None
    if markdown[index] == ")":
        return index
    if index == whitespace_start or markdown[index] not in "\"'(":
        return None

    title_closer = {'"': '"', "'": "'", "(": ")"}[markdown[index]]
    index += 1
    while index < len(markdown):
        character = markdown[index]
        if character == "\\" and index + 1 < len(markdown):
            index += 2
            continue
        if character == title_closer:
            index = _skip_link_whitespace(markdown, index + 1)
            return index if index < len(markdown) and markdown[index] == ")" else None
        index += 1
    return None


def _skip_link_whitespace(markdown: str, index: int) -> int:
    while index < len(markdown) and markdown[index] in _LINK_WHITESPACE:
        index += 1
    return index


def _find_angle_destination_end(markdown: str, index: int) -> int | None:
    while index < len(markdown):
        character = markdown[index]
        if character in "\r\n<":
            return None
        if character == "\\" and index + 1 < len(markdown):
            index += 2
            continue
        if character == ">":
            return index + 1
        index += 1
    return None


def _without_extended_autolink(match: re.Match[str]) -> str:
    prefix = match.groupdict().get("prefix", "")
    target = match.group("target")
    suffix_start = len(target)

    while suffix_start and target[suffix_start - 1] in "?!.,:*_~":
        suffix_start -= 1
    while (
        suffix_start
        and target[suffix_start - 1] == ")"
        and target[:suffix_start].count(")") > target[:suffix_start].count("(")
    ):
        suffix_start -= 1

    entity = re.search(r"&[A-Za-z0-9]+;$", target[:suffix_start])
    if entity:
        suffix_start = entity.start()
    return prefix + target[suffix_start:]


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
    title: str = Field(min_length=1, max_length=SOURCE_TITLE_MAX_CHARACTERS)
    url: str = Field(min_length=1, max_length=2_048)
    retrieved_at: datetime


class ResearchOutcome(StrEnum):
    """Stable terminal category; warnings retain implementation-level detail."""

    SOURCE_GROUNDED = "source_grounded"
    AGENT_ERROR = "agent_error"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INVALID_REPORT = "invalid_report"


class ResearchReport(BaseModel):
    """A validated terminal result shared by research interfaces."""

    model_config = ConfigDict(frozen=True)

    answer_markdown: str = Field(min_length=1)
    outcome: ResearchOutcome = ResearchOutcome.SOURCE_GROUNDED
    sources: list[Source] = Field(default_factory=list)
    warnings: list[Annotated[str, Field(max_length=WARNING_MAX_CHARACTERS)]] = Field(
        default_factory=list
    )

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

        if self.is_source_grounded and not cited_source_ids:
            raise ValueError("source-grounded outcome requires citations")
        if not self.is_source_grounded and cited_source_ids:
            raise ValueError("failure outcome cannot contain citations")
        return self

    @property
    def cited_source_ids(self) -> list[str]:
        return extract_citation_ids(self.answer_markdown)

    @property
    def is_source_grounded(self) -> bool:
        return self.outcome is ResearchOutcome.SOURCE_GROUNDED
