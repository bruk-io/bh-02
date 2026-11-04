"""The middleware's one entry point: route a tool result to a compressor, or pass it through."""

from dataclasses import dataclass
from typing import Any

from compressors import envelope_log, envelope_tree, markers
from compressors.code import code_tree
from compressors.common import estimate_tokens, split_lines
from compressors.config import DEFAULT, FoldConfig
from compressors.envelope import Envelope
from compressors.envelope_json import VIEWS, envelope
from compressors.html import html_to_text, looks_like_html
from compressors.json_items import parse_json_or_jsonl
from compressors.tree import XmlTree, heading_tree, indent_tree, looks_like_outline, looks_like_xml, xml_tree

_MIN_LINES = 40  # fewer lines than this and the text is cut by characters instead
_MAX_AVG_LINE = 500
_BOM = "\ufeff"


# What detection parsed, handed to the fold so nothing is parsed twice: a JSON document and its
# kind ("json" or "jsonl", which is also its branch), an XML element tree, or nothing for the branches
# that parse as they fold.
type _Parsed = tuple[Any, str] | XmlTree | None

_BRANCHES = ("json", "xml", "html", "outline", "lines", "text")


def _detect(raw: str) -> tuple[str, _Parsed]:
    if (doc := parse_json_or_jsonl(raw)) is not None:
        return doc[1], doc
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
    """The branch a large result would take: json, jsonl, xml, html, outline, lines or text."""
    return _detect(raw)[0]


def _parse_as(branch: str, raw: str) -> tuple[str, _Parsed]:
    """The branch and what it needs parsed, for a branch named instead of detected ("json" takes
    JSON Lines too, and becomes "jsonl").

    Raises:
        ValueError: the text cannot take that branch, or there is no such branch.
    """
    match branch:
        case "json":
            if (doc := parse_json_or_jsonl(raw)) is None:
                raise ValueError(
                    "--as json: the text does not parse as JSON or JSON Lines, "
                    "or nests deeper than the parser allows"
                )
            return doc[1], doc
        case "xml":
            if (tree := xml_tree(raw)) is None:
                raise ValueError("--as xml: the text is not well-formed XML")
            return "xml", tree
        case _ if branch in _BRANCHES:
            return branch, None
        case _:
            raise ValueError(f"unknown branch {branch!r}: use one of {', '.join(_BRANCHES)}")


def _records_by_line(raw: str) -> bool:
    """Whether JSON Lines record i is on line i+1: no blank line before the last record."""
    filled = [i for i, line in enumerate(split_lines(raw)) if line.strip()]
    return filled == list(range(len(filled)))


LINE_BRANCHES = ("lines", "xml", "outline", "html", "text", "code")  # read as lines, addressed by number


def lines_envelope(
    raw: str,
    branch: str,
    terms: frozenset[str],
    budget_tokens: int,
    config: FoldConfig = DEFAULT,
    view: str = "sample",
    *,
    language: str = "",
    tree: XmlTree | None = None,
) -> tuple[Envelope, str]:
    """The envelope of a text read as lines, and the source its line numbers refer to: a log's
    (`envelope_log`), or a tree's (`envelope_tree`) over an outline's indentation, XML's elements
    (`tree`, when detection parsed it already), a page's headings once it is text, a plain text's
    lines, or code's definitions (`language`). A language ast-grep has no grammar for raises
    ValueError, from `code.code_tree`.

    Raises:
        ValueError: the branch is not read as lines, or the text is not well-formed XML.
    """
    match branch:
        case "lines":
            return envelope_log.envelope(raw, terms, budget_tokens, config, view), raw
        case "xml":
            if (tree := tree or xml_tree(raw)) is None:
                raise ValueError("the text is not well-formed XML")
            source = "\n".join(tree.lines) if tree.pretty else raw
            return envelope_tree.envelope(
                tuple(tree.lines), tree.roots, terms, budget_tokens, config, view
            ), source
        case "outline" | "html" | "text" | "code":
            source = html_to_text(raw) if branch == "html" else raw
            lines = tuple(split_lines(source))
            match branch:
                case "outline":
                    roots = indent_tree(list(lines))
                case "code":
                    roots = code_tree(source, language)
                case _:
                    roots = heading_tree(list(lines))
            return envelope_tree.envelope(lines, roots, terms, budget_tokens, config, view), source
        case _:
            raise ValueError(f"{branch!r} is not read as lines: those are {', '.join(LINE_BRANCHES)}")


def _body(
    branch: str,
    parsed: _Parsed,
    raw: str,
    terms: frozenset[str],
    budget_tokens: int,
    config: FoldConfig,
    view: str = "sample",
) -> tuple[str, str | None]:
    """The folded text, and the text its line numbers refer to when that is not `raw`.

    Raises:
        AssertionError: a branch arrived without what it parses (a bug in `_detect` or `_parse_as`).
    """
    match branch, parsed:
        case "json", (value, "json"):
            return envelope(value, terms, budget_tokens, config=config, view=view).text(), None
        case "jsonl", (list() as records, "jsonl"):
            note = markers.jsonl_note(len(records), _records_by_line(raw))
            body = envelope(records, terms, budget_tokens, slurp=True, config=config, view=view).text()
            return f"{note}\n{body}", None
        case "xml", XmlTree() as tree:
            env, source = lines_envelope(raw, "xml", terms, budget_tokens, config, view, tree=tree)
            return env.text(), (source if tree.pretty else None)
        case "html", None:
            text = html_to_text(raw)
            if estimate_tokens(text) <= budget_tokens:
                return text, text
            env, source = lines_envelope(raw, "html", terms, budget_tokens, config, view)
            return env.text(), source
        case (("lines" | "outline" | "text"), None):
            return lines_envelope(raw, branch, terms, budget_tokens, config, view)[0].text(), None
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
    view: str = "sample",
    config: FoldConfig = DEFAULT,
) -> Folded | None:
    """The folded body of a large result, or None when it should pass through untouched.

    None when the result fits the budget, or when folding would keep more than 90% of it. `terms`
    are the query (`common.query_words` of a query, `common.query_terms` of a tool call's
    arguments); `force` names the branch instead of detecting it; `view` says how a data branch
    shows its data: the recipe of a JSON envelope (`compressors.envelope_json`), sample or schema,
    whose parts the `json_envelope` knobs can change one by one; `config` holds the knobs
    (`compressors.config`). A `force` the text cannot
    take (JSON that does not parse, XML that is not well formed) or that is no branch at all raises
    ValueError, from `_parse_as`.

    Raises:
        ValueError: `view` names no JSON recipe (sample or schema).
    """
    raw_tokens = estimate_tokens(raw)
    if raw_tokens <= budget_tokens:
        return None
    raw = raw.removeprefix(_BOM)  # it defeats JSON and XML detection, and dropping it moves no line
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}: use {' or '.join(VIEWS)}")
    branch, parsed = _parse_as(force, raw) if force else _detect(raw)
    body, source = _body(branch, parsed, raw, terms, budget_tokens, config, view)
    if not body.strip() or estimate_tokens(body) > raw_tokens * config.worth_it:  # shows nothing, or too much
        return None
    return Folded(branch, body, raw_tokens, source)
