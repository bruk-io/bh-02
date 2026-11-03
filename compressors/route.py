"""The middleware's one entry point: route a tool result to a compressor, or pass it through."""

from collections.abc import Mapping
from typing import Any

from compressors.common import Compressed, call_id_for, estimate_tokens, query_terms
from compressors.html import html_to_text, looks_like_html
from compressors.json_fold import fold_json, parse_json_or_jsonl
from compressors.lines import fold_lines

_MIN_LINES = 40  # fewer lines than this and the text is cut by characters instead
_MAX_AVG_LINE = 500
_WORTH_IT = 0.9  # a result that keeps more than this share of the raw tokens is passed through

_HOW_TO_RECOVER = {
    "json": 'a path such as "$.items[10:20]" or "$.items[312].status", or "grep:<text>"',
    "lines": '"lines:<first>-<last>" (1-based, inclusive) or "grep:<text>"',
    "html": '"lines:<first>-<last>" of the page text (1-based, inclusive) or "grep:<text>"',
    "text": '"chars:<start>-<end>" (0-based, end exclusive) or "grep:<text>"',
}


def detect(raw: str) -> str:
    """The branch a large result would take: json, html, lines or text."""
    if parse_json_or_jsonl(raw) is not None:
        return "json"
    if looks_like_html(raw):
        return "html"
    lines = raw.splitlines()
    if len(lines) >= _MIN_LINES and len(raw) / len(lines) <= _MAX_AVG_LINE:
        return "lines"
    return "text"


def _cut_chars(raw: str, budget_tokens: int) -> str:
    keep = budget_tokens * 4
    head, tail = int(keep * 0.65), int(keep * 0.3)
    return f"{raw[:head]}\n[... chars {head}-{len(raw) - tail} omitted]\n{raw[len(raw) - tail :]}"


def _body(branch: str, raw: str, terms: frozenset[str], budget_tokens: int) -> str:
    match branch:
        case "json":
            parsed = parse_json_or_jsonl(raw)
            assert parsed is not None
            value, kind = parsed
            note = "JSONL shown as one array; index i is line i+1.\n" if kind == "jsonl" else ""
            return note + fold_json(value, terms, budget_tokens)
        case "html":
            text = html_to_text(raw)
            return text if estimate_tokens(text) <= budget_tokens else fold_lines(text, terms)
        case "lines":
            return fold_lines(raw, terms)
        case "text":
            return _cut_chars(raw, budget_tokens)
        case _:
            raise ValueError(f"unknown branch {branch!r}: detect() returns json, html, lines or text")


def compress(
    tool_name: str, args: Mapping[str, Any], raw: str, *, budget_tokens: int = 2000, use_query: bool = True
) -> Compressed:
    """What the model should see for this tool result.

    The caller keeps `raw` under the returned call id, so `recovery.recover` can serve slices of
    it. `tool_name` is unused by the deterministic branches and kept for routing experiments.
    """
    del tool_name
    raw_tokens = estimate_tokens(raw)
    passthrough = Compressed(raw, "passthrough", None, raw_tokens, raw_tokens)
    if raw_tokens <= budget_tokens:
        return passthrough
    branch = detect(raw)
    terms = query_terms(args) if use_query else frozenset()
    body = _body(branch, raw, terms, budget_tokens)
    cid = call_id_for(raw)
    banner = (
        f"[Output folded: ~{raw_tokens} tokens -> ~{estimate_tokens(body)}. Markers show what was left out. "
        f'To read omitted parts call recover(call_id="{cid}", query=...) with {_HOW_TO_RECOVER[branch]}.]'
    )
    text = f"{banner}\n{body}"
    out_tokens = estimate_tokens(text)
    if out_tokens > raw_tokens * _WORTH_IT:
        return passthrough
    return Compressed(text, branch, cid, raw_tokens, out_tokens)
