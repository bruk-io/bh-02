"""The middleware's one entry point: route a tool result to a compressor, or pass it through."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from compressors.common import Compressed, call_id_for, estimate_tokens, query_terms
from compressors.html import html_to_text, looks_like_html
from compressors.json_fold import fold_json, parse_json_or_jsonl
from compressors.lines import fold_lines
from compressors.tree import fold_outline, fold_xml, looks_like_outline, looks_like_xml, xml_tree

_MIN_LINES = 40  # fewer lines than this and the text is cut by characters instead
_MAX_AVG_LINE = 500
_WORTH_IT = 0.9  # a result that keeps more than this share of the raw tokens is passed through

_FOLDED_SLICE = re.compile(r'"_folded": "(\$[^"\s]*)\[(\d+):(\d+)\] omitted')
_HOW_TO_RECOVER = {
    "lines": '"lines:<first>-<last>" (1-based, inclusive) or "grep:<text>"',
    "html": '"lines:<first>-<last>" of the page text (1-based, inclusive) or "grep:<text>"',
    "xml": '"lines:<first>-<last>" (1-based, inclusive) or "grep:<text>"',
    "outline": '"lines:<first>-<last>" (1-based, inclusive) or "grep:<text>"',
    "text": '"chars:<start>-<end>" (0-based, end exclusive) or "grep:<text>"',
}


def _how_to_recover(branch: str, body: str) -> str:
    if branch != "json":
        return _HOW_TO_RECOVER[branch]
    m = _FOLDED_SLICE.search(body)
    example = f"{m[1]}[{m[2]}:{min(int(m[3]), int(m[2]) + 5)}]" if m else "$.key[3]"
    return (
        f'a JSON path such as "{example}" (keys as .name, indices as [i], slices as [a:b]), or "grep:<text>"'
    )


def detect(raw: str) -> str:
    """The branch a large result would take: json, xml, html, outline, lines or text."""
    if parse_json_or_jsonl(raw) is not None:
        return "json"
    if looks_like_xml(raw) and xml_tree(raw) is not None:
        return "xml"
    if looks_like_html(raw):
        return "html"
    lines = raw.splitlines()
    if looks_like_outline(lines):
        return "outline"
    if len(lines) >= _MIN_LINES and len(raw) / len(lines) <= _MAX_AVG_LINE:
        return "lines"
    return "text"


def _cut_chars(raw: str, budget_tokens: int) -> str:
    keep = budget_tokens * 4
    head, tail = int(keep * 0.65), int(keep * 0.3)
    return f"{raw[:head]}\n[... chars {head}-{len(raw) - tail} omitted]\n{raw[len(raw) - tail :]}"


def _body(branch: str, raw: str, terms: frozenset[str], budget_tokens: int) -> tuple[str, str | None]:
    """The folded text, and the text its line numbers refer to when that is not `raw`."""
    match branch:
        case "xml":
            fold = fold_xml(raw, budget_tokens, terms)
            assert fold is not None
            return fold.text, (fold.source if fold.source != raw else None)
        case "outline":
            return fold_outline(raw, budget_tokens, terms).text, None
        case "json":
            parsed = parse_json_or_jsonl(raw)
            assert parsed is not None
            value, kind = parsed
            note = "JSONL shown as one array; index i is line i+1.\n" if kind == "jsonl" else ""
            return note + fold_json(value, terms, budget_tokens), None
        case "html":
            text = html_to_text(raw)
            return (text if estimate_tokens(text) <= budget_tokens else fold_lines(text, terms)), text
        case "lines":
            return fold_lines(raw, terms), None
        case "text":
            return _cut_chars(raw, budget_tokens), None
        case _:
            raise ValueError(
                f"unknown branch {branch!r}: detect() returns json, xml, html, outline, lines or text"
            )


@dataclass(frozen=True)
class Folded:
    """A folded body with no banner: the caller says how to reach the raw output."""

    branch: str  # json | xml | html | outline | lines | text
    body: str
    raw_tokens: int
    source: str | None = None  # the text the body's line numbers refer to, when that is not the raw


def fold(
    args: Mapping[str, Any], raw: str, *, budget_tokens: int = 2000, use_query: bool = True
) -> Folded | None:
    """The folded body of a large result, or None when it should pass through untouched.

    None when the result fits the budget, or when folding would keep more than 90% of it.
    """
    raw_tokens = estimate_tokens(raw)
    if raw_tokens <= budget_tokens:
        return None
    branch = detect(raw)
    terms = query_terms(args) if use_query else frozenset()
    body, source = _body(branch, raw, terms, budget_tokens)
    if estimate_tokens(body) > raw_tokens * _WORTH_IT:
        return None
    return Folded(branch, body, raw_tokens, source)


def compress(
    tool_name: str, args: Mapping[str, Any], raw: str, *, budget_tokens: int = 2000, use_query: bool = True
) -> Compressed:
    """What the model should see for this tool result, with a banner naming `recovery.recover`.

    The caller keeps `raw` under the returned call id, so `recovery.recover` can serve slices of
    it. `tool_name` is unused by the deterministic branches and kept for routing experiments.
    """
    del tool_name
    raw_tokens = estimate_tokens(raw)
    passthrough = Compressed(raw, "passthrough", None, raw_tokens, raw_tokens)
    folded = fold(args, raw, budget_tokens=budget_tokens, use_query=use_query)
    if folded is None:
        return passthrough
    cid = call_id_for(raw)
    how = _how_to_recover(folded.branch, folded.body)
    banner = (
        f"[Output folded: ~{raw_tokens} tokens -> ~{estimate_tokens(folded.body)}. Markers show what was "
        f'left out. To read omitted parts call recover(call_id="{cid}", query=...) with {how}.]'
    )
    text = f"{banner}\n{folded.body}"
    out_tokens = estimate_tokens(text)
    if out_tokens > raw_tokens * _WORTH_IT:
        return passthrough
    return Compressed(text, folded.branch, cid, raw_tokens, out_tokens)
