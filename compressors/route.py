"""The middleware's one entry point: route a tool result to a compressor, or pass it through."""

from dataclasses import dataclass
from typing import Any

from compressors import markers
from compressors.common import estimate_tokens, split_lines
from compressors.html import html_to_text, looks_like_html
from compressors.json_fold import fold_json, parse_json_or_jsonl
from compressors.lines import fold_lines
from compressors.tree import (
    XmlTree,
    fold_outline,
    fold_xml_tree,
    looks_like_outline,
    looks_like_xml,
    xml_tree,
)

_MIN_LINES = 40  # fewer lines than this and the text is cut by characters instead
_MAX_AVG_LINE = 500
_WORTH_IT = 0.9  # a result that keeps more than this share of the raw tokens is passed through


# What detection parsed, handed to the fold so nothing is parsed twice: a JSON document and its
# kind ("json" or "jsonl"), an XML element tree, or nothing for the branches that parse as they fold.
type _Parsed = tuple[Any, str] | XmlTree | None

_BRANCHES = ("json", "xml", "html", "outline", "lines", "text")


def _detect(raw: str) -> tuple[str, _Parsed]:
    if (doc := parse_json_or_jsonl(raw)) is not None:
        return "json", doc
    if looks_like_xml(raw) and (tree := xml_tree(raw)) is not None:
        return "xml", tree
    if looks_like_html(raw):
        return "html", None
    lines = split_lines(raw)
    if looks_like_outline(lines):
        return "outline", None
    if len(lines) >= _MIN_LINES and len(raw) / len(lines) <= _MAX_AVG_LINE:
        return "lines", None
    return "text", None


def detect(raw: str) -> str:
    """The branch a large result would take: json, xml, html, outline, lines or text."""
    return _detect(raw)[0]


def _parse_as(branch: str, raw: str) -> _Parsed:
    """What `branch` needs parsed, for a branch named instead of detected.

    Raises:
        ValueError: the text cannot take that branch, or there is no such branch.
    """
    match branch:
        case "json":
            if (doc := parse_json_or_jsonl(raw)) is None:
                raise ValueError("--as json: the text does not parse as JSON or JSON Lines")
            return doc
        case "xml":
            if (tree := xml_tree(raw)) is None:
                raise ValueError("--as xml: the text is not well-formed XML")
            return tree
        case _ if branch in _BRANCHES:
            return None
        case _:
            raise ValueError(f"unknown branch {branch!r}: use one of {', '.join(_BRANCHES)}")


def _cut_chars(raw: str, budget_tokens: int) -> str:
    keep = budget_tokens * 4
    head, tail = int(keep * 0.65), int(keep * 0.3)
    return f"{raw[:head]}\n{markers.chars_omitted(head, len(raw) - tail)}\n{raw[len(raw) - tail :]}"


def _body(
    branch: str, parsed: _Parsed, raw: str, terms: frozenset[str], budget_tokens: int
) -> tuple[str, str | None]:
    """The folded text, and the text its line numbers refer to when that is not `raw`."""
    match branch, parsed:
        case "xml", XmlTree() as tree:
            return fold_xml_tree(tree, budget_tokens, terms).text, (
                "\n".join(tree.lines) if tree.pretty else None
            )
        case "json", (value, kind):
            note = "JSONL shown as one array; index i is line i+1.\n" if kind == "jsonl" else ""
            return note + fold_json(value, terms, budget_tokens), None
        case "outline", None:
            return fold_outline(raw, budget_tokens, terms).text, None
        case "html", None:
            text = html_to_text(raw)
            return (
                text if estimate_tokens(text) <= budget_tokens else fold_lines(text, terms, budget_tokens)
            ), text
        case "lines", None:
            return fold_lines(raw, terms, budget_tokens), None
        case "text", None:
            return _cut_chars(raw, budget_tokens), None
        case _:
            raise AssertionError(f"branch {branch!r} reached the fold without what it parses")


@dataclass(frozen=True)
class Folded:
    """A folded body with no banner: the caller says how to reach the raw output."""

    branch: str  # json | xml | html | outline | lines | text
    body: str
    raw_tokens: int
    source: str | None = None  # the text the body's line numbers refer to, when that is not the raw


def fold(
    raw: str,
    *,
    budget_tokens: int = 2000,
    terms: frozenset[str] = frozenset(),
    force: str | None = None,
) -> Folded | None:
    """The folded body of a large result, or None when it should pass through untouched.

    None when the result fits the budget, or when folding would keep more than 90% of it. `terms`
    are the query (`common.query_words` of a query, `common.query_terms` of a tool call's
    arguments); `force` names the branch instead of detecting it.

    Raises:
        ValueError: `force` names a branch the text cannot take (JSON that does not parse, XML that
            is not well formed) or no branch at all.
    """
    raw_tokens = estimate_tokens(raw)
    if raw_tokens <= budget_tokens:
        return None
    branch, parsed = (force, _parse_as(force, raw)) if force else _detect(raw)
    body, source = _body(branch, parsed, raw, terms, budget_tokens)
    if estimate_tokens(body) > raw_tokens * _WORTH_IT:
        return None
    return Folded(branch, body, raw_tokens, source)
