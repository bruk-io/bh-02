"""Text read as a tree of line ranges: indented outlines, a document's headings, and XML.

A node is a range of source lines with a header (the lines that name it: an opening tag, an outline
entry, a heading) and child nodes inside it. These are the trees `compressors.envelope_tree` makes
envelopes of; `compressors.code` builds the same nodes for source code with ast-grep.

Adapters here build the tree for indentation outlines (Playwright-style accessibility snapshots,
YAML-ish trees), a document's headings, and XML (Figma node metadata, Android UI dumps), which is
pretty-printed when it comes packed, so that one element starts each line.
"""

import re
import xml.dom.minidom
import xml.parsers.expat
from dataclasses import dataclass

from compressors.common import split_lines


@dataclass(frozen=True)
class Node:
    first: int  # 0-based index of the node's first line
    head_end: int  # last line of the header, shown when folded (>= first)
    last: int  # last line of the node (>= head_end)
    children: tuple[Node, ...] = ()


# --- indentation outlines -----------------------------------------------------------------------


def indent_tree(lines: list[str]) -> tuple[Node, ...]:
    """Every non-blank line is a node; the lines indented under it are its children."""
    roots: list[Node] = []
    stack: list[tuple[int, int, list[Node]]] = []  # (indent, first, children)
    last_nonblank = -1

    def close(upto_indent: int) -> None:
        while stack and stack[-1][0] >= upto_indent:
            _, first, kids = stack.pop()
            node = Node(first, first, max(first, last_nonblank), tuple(kids))
            (stack[-1][2] if stack else roots).append(node)

    for i, line in enumerate(lines):
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        close(indent)
        stack.append((indent, i, []))
        last_nonblank = i
    close(-1)
    return tuple(roots)


_HEADING = re.compile(r"(#{1,6}) \S")


def heading_tree(lines: list[str]) -> tuple[Node, ...]:
    """A document's headings (`# Title`, `## Part`, as `html.html_to_text` writes them) as nodes,
    each spanning its section, the lines before the first heading one node of their own; with no
    heading, every non-blank line a node."""
    marks = [(i, len(m[1])) for i, line in enumerate(lines) if (m := _HEADING.match(line))]
    if not marks:
        return tuple(Node(i, i, i) for i, line in enumerate(lines) if line.strip())
    roots: list[Node] = []
    stack: list[tuple[int, int, list[Node]]] = []  # (level, first, children)

    def close(level: int, end: int) -> None:
        while stack and stack[-1][0] >= level:
            _, first, kids = stack.pop()
            (stack[-1][2] if stack else roots).append(Node(first, first, end, tuple(kids)))

    if marks[0][0] > 0:
        roots.append(Node(0, 0, marks[0][0] - 1))
    for i, level in marks:
        close(level, i - 1)
        stack.append((level, i, []))
    close(0, len(lines) - 1)
    return tuple(roots)


def looks_like_outline(lines: list[str]) -> bool:
    """Many lines, mostly indented, nested at least three levels: an outline, not a log."""
    body = [line for line in lines if line.strip()]
    if len(body) < 40:
        return False
    indents = sorted({len(line) - len(line.lstrip()) for line in body})
    indented = sum(1 for line in body if line[0] in " \t")
    return len(indents) >= 4 and indented / len(body) >= 0.6


# --- XML ----------------------------------------------------------------------------------------

_XML_START = re.compile(r"\s*(<\?xml|<[A-Za-z_][\w:.-]*[\s>/])")


def looks_like_xml(raw: str) -> bool:
    head = raw.lstrip()[:200].lower()
    if head.startswith(("<!doctype html", "<html")):
        return False
    return bool(_XML_START.match(raw)) and raw.rstrip().endswith(">")


_BETWEEN_TAGS = re.compile(r">\s*<")


def _pretty(raw: str) -> str:
    """One element per line, when the XML came packed onto few lines."""
    lines = split_lines(raw)
    if len(lines) >= raw.count("<") / 4 and max((len(line) for line in lines), default=0) <= 1000:
        return raw
    try:
        # the text, not bytes: it is already decoded, so a declared encoding (ISO-8859-1, UTF-16)
        # must not decode it again, as our own expat parse does not
        pretty = xml.dom.minidom.parseString(raw).toprettyxml(indent="  ")
    except RecursionError:  # nested deeper than minidom's writer recurses: one tag per line, unindented
        pretty = _BETWEEN_TAGS.sub(">\n<", raw)
    return "\n".join(line for line in split_lines(pretty) if line.strip())


_BARE_AMP = re.compile(r"&(?!(?:[A-Za-z][\w.-]*|#\d+|#x[0-9A-Fa-f]+);)")


def lenient_xml(raw: str) -> str:
    """Bare ampersands escaped. Real files have them ("Enewetak & Ujelang" in the ISO 3166-2 data),
    and escaping one moves no line, so line numbers still refer to the original."""
    return _BARE_AMP.sub("&amp;", raw)


def _element_tree(source: str) -> tuple[Node, ...] | None:
    parser = xml.parsers.expat.ParserCreate()
    stack: list[tuple[int, list[Node]]] = [(-1, [])]

    def start(_name: str, _attrs: dict[str, str]) -> None:
        stack.append((parser.CurrentLineNumber - 1, []))

    def end(_name: str) -> None:
        first, kids = stack.pop()
        stack[-1][1].append(Node(first, first, parser.CurrentLineNumber - 1, tuple(kids)))

    def comment(text: str) -> None:  # a long comment folds like an element; expat reports where it starts
        first = parser.CurrentLineNumber - 1
        last = first + text.count("\n")
        if last > first:
            stack[-1][1].append(Node(first, first, last))

    def doctype_start(*_args: object) -> None:
        stack.append((parser.CurrentLineNumber - 1, []))

    def doctype_end() -> None:
        first, _ = stack.pop()
        stack[-1][1].append(Node(first, first, parser.CurrentLineNumber - 1))

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CommentHandler = comment
    parser.StartDoctypeDeclHandler = doctype_start
    parser.EndDoctypeDeclHandler = doctype_end
    try:
        parser.Parse(source, True)
    except xml.parsers.expat.ExpatError:
        return None
    return tuple(stack[0][1])


@dataclass(frozen=True)
class XmlTree:
    lines: list[str]  # the lines the element tree's line numbers refer to
    roots: tuple[Node, ...]
    pretty: bool  # the lines are a pretty-printed copy (the XML came packed), not the input's own


def xml_tree(raw: str) -> XmlTree | None:
    """The XML's lines (pretty-printed if it came packed) and its element tree; None if not XML.

    XML that fails to parse only for bare ampersands is read leniently; its lines are shown as
    they are in the input."""
    for text in (raw, lenient_xml(raw)):
        try:
            source = _pretty(text)
        except Exception:  # minidom raises a handful of unrelated types on bad input  # noqa: BLE001
            continue
        roots = _element_tree(source)
        if roots is not None:
            pretty = source is not text
            return XmlTree(split_lines(source if pretty else raw), roots, pretty)
    return None
