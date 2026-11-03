"""Fold anything that is a tree of line ranges: code, XML, accessibility trees, outlines.

A node is a range of source lines with a header (the lines shown when it is folded: a signature,
an opening tag, an outline entry) and child nodes inside it. The fold starts from the outline,
every top-level node's header, and expands nodes in order of depth, cheapest first, while the
result fits the budget. A folded node shows its header and one marker naming the source lines it
hides, so a reader can fetch exactly those lines (Read with offset and limit, or sed -n).

Adapters here build the tree for indentation outlines (Playwright-style accessibility snapshots,
YAML-ish trees) and XML (Figma node metadata, Android UI dumps); `compressors.code` builds it for
source code with ast-grep.
"""

import heapq
import itertools
import re
import xml.dom.minidom
import xml.parsers.expat
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field

from compressors import markers
from compressors.common import discriminating, estimate_tokens, matches, split_lines

_ID_TOKEN = re.compile(r"[A-Za-z0-9_]*\d[A-Za-z0-9_]*")
_VARIABLE = re.compile(r"0x[0-9a-fA-F]+|[0-9a-fA-F]{8,}|\d+")

_MARKER_TOKENS = 12


@dataclass(frozen=True)
class Node:
    first: int  # 0-based index of the node's first line
    head_end: int  # last line of the header, shown when folded (>= first)
    last: int  # last line of the node (>= head_end)
    children: tuple[Node, ...] = ()
    run: bool = False  # a run of plain lines no other node covers, not structure


@dataclass(frozen=True)
class TreeFold:
    text: str  # what the reader sees
    source: str  # the text the markers' line numbers refer to (raw, or raw pretty-printed)
    expanded: int  # nodes shown open
    folded: int  # nodes shown as a header and a marker


def _with_gaps(
    lines: list[str], nodes: tuple[Node, ...], first: int, last: int, min_gap: int
) -> tuple[Node, ...]:
    """The nodes, plus a leaf for every run of at least `min_gap` lines between them that no node
    covers (3,000 assignments, a module's imports, code the parser gave up on), so plain lines fold
    too and a fold has a floor. A run starts at its first non-blank line, so its header shows.
    Iterative, since trees nest as deep as their input."""

    def gap(start: int, end: int) -> Node | None:
        while start <= end and not lines[start].strip():
            start += 1
        return Node(start, start, end, run=True) if end - start + 1 >= min_gap else None

    top: list[Node] = []
    # a frame: the nodes left in one list, the list rebuilt so far, the first line not yet covered,
    # the list's last line, and the node it is the children of (None at the top) with its own list
    stack: list[tuple[Iterator[Node], list[Node], int, int, tuple[Node, list[Node]] | None]] = [
        (iter(nodes), top, first, last, None)
    ]
    while stack:
        pending, out, cursor, end, parent = stack[-1]
        n = next(pending, None)
        if n is None:
            if (g := gap(cursor, end)) is not None:
                out.append(g)
            stack.pop()
            if parent is not None:
                node, dest = parent
                dest.append(Node(node.first, node.head_end, node.last, tuple(out), node.run))
            continue
        if (g := gap(cursor, n.first - 1)) is not None:
            out.append(g)
        stack[-1] = (pending, out, n.last + 1, end, parent)
        stack.append((iter(n.children), [], n.head_end + 1, n.last, (n, out)))
    return tuple(top)


def _signature(lines: list[str], n: Node, cap: int = 600) -> str:
    """A sibling's shape: its lines with every token that holds a digit blanked (numbers, and ids
    such as INV-a3f09bc, e12345 or 12:345), up to `cap` characters, so a list item whose button is
    disabled differs from its siblings even though their headers match."""
    out, size = [], 0
    for i in range(n.first, n.last + 1):
        line = _ID_TOKEN.sub("#", lines[i].strip())
        out.append(line)
        size += len(line)
        if size >= cap:
            break
    return "\n".join(out)


def _subtree_text(lines: list[str], n: Node, cap: int = 20_000) -> str:
    """A node's whole text, up to `cap` characters: what a query term is looked for in, so a match
    deep inside (entry 13 of a country's 47) still marks the way down."""
    out, size = [], 0
    for i in range(n.first, n.last + 1):
        out.append(lines[i])
        size += len(lines[i])
        if size >= cap:
            break
    return "\n".join(out)


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


_MIN_HIDDEN = 3  # a node hiding fewer lines than this is shown whole: its marker would cost as much
_MAX_LINE_CHARS = 300
_HEAD_CHILDREN = 3  # a list opened partly shows at least its first 3 children,
_TAIL_CHILDREN = 1  # its last one, and its stand-outs
_MIN_GAP = 6  # a run of this many plain lines no node covers folds as a leaf of its own
_MAX_PROMOTED = 10  # stand-outs shown per list; the rest are counted in the marker that hides them


@dataclass(frozen=True)
class _Promotion:
    """A list's stand-outs: the children shown out of turn, and those past the cap."""

    picks: tuple[int, ...]
    unshown: frozenset[int] = frozenset()


@dataclass(frozen=True)
class _Fold:
    """What every phase reads: the lines, as shown and what any span of them costs, and the query.

    `promotions` is a cache (id of a children tuple -> its stand-outs): finding a list's stand-outs
    reads every child's text, so it is done once, when the list is first costed."""

    lines: list[str]
    shown: tuple[str, ...]  # each line as the fold shows it: clipped, and numbered when asked
    prefix: tuple[int, ...]  # prefix[i]: the cost of showing lines 0 to i-1
    numbered: bool
    terms: frozenset[str]
    promotions: dict[int, _Promotion] = field(default_factory=dict)


@dataclass(frozen=True)
class _Plan:
    root_k: int | None  # how the top-level list opens: None in full, k its first k children (and so on)
    opened: dict[int, int | None]  # id(node) -> k, for every node shown open


def _fold_of(lines: list[str], numbered: bool, terms: frozenset[str]) -> _Fold:
    clipped = (markers.clipped(line, _MAX_LINE_CHARS) for line in lines)
    shown = tuple(f"{i + 1}\t{line}" if numbered else line for i, line in enumerate(clipped))
    prefix = (0, *itertools.accumulate(estimate_tokens(line) + 1 for line in shown))
    return _Fold(lines, shown, prefix, numbered, terms)


def _span(f: _Fold, a: int, b: int) -> int:
    """The cost of showing lines a to b (nothing when b < a)."""
    return f.prefix[b + 1] - f.prefix[a] if b >= a else 0


def _small(n: Node) -> bool:
    """Too small to fold on its own (a marker would cost as much as it hides): shown whole when
    shown, but still a child, so a list of small items can open partly."""
    return n.last - n.head_end < _MIN_HIDDEN


def _folded_cost(f: _Fold, n: Node) -> int:
    if _small(n):
        return _span(f, n.first, n.last)
    return _span(f, n.first, n.head_end) + _MARKER_TOKENS


def _standouts(lines: list[str], children: tuple[Node, ...], terms: frozenset[str]) -> _Promotion:
    """Children that stand out among siblings that mostly share one shape, or that hold query terms
    few siblings share, most matched terms first. They open first, since what they hold is why
    they are shown."""
    n = len(children)
    texts = [_subtree_text(lines, c) for c in children]
    if n < 10:  # too few siblings for "rare"; a query match still marks the way down and shows
        return _Promotion(tuple(i for i, text in enumerate(texts) if any(matches(text, t) for t in terms)))
    patterns = [_signature(lines, c) for c in children]
    counts = Counter(patterns)
    rare_cut = max(1, int(0.1 * n))  # no summary counts here, so rare reaches 10%
    dominant = counts.most_common(1)[0][1] / n >= 0.6
    heads = [lines[c.first] for c in children]
    useful_head = discriminating(terms, heads, share=0.05, floor=3)  # a few matches still pick out
    useful_deep = discriminating(terms, texts, share=0.05, floor=3)
    scored = []
    for i, (pat, head, text) in enumerate(zip(patterns, heads, texts, strict=True)):
        # a match on the node's own header (code="AD") weighs more than one deep inside it
        hits = 2 * sum(matches(head, t) for t in useful_head) + sum(matches(text, t) for t in useful_deep)
        rare = dominant and counts[pat] <= rare_cut
        if hits or rare:
            scored.append((-(2 * hits + rare), i))
    ranked = [i for _, i in sorted(scored)]
    return _Promotion(tuple(sorted(ranked[:_MAX_PROMOTED])), frozenset(ranked[_MAX_PROMOTED:]))


def _promotion(f: _Fold, children: tuple[Node, ...]) -> _Promotion:
    if id(children) not in f.promotions:
        f.promotions[id(children)] = _standouts(f.lines, children, f.terms)
    return f.promotions[id(children)]


def _shown_children(f: _Fold, children: tuple[Node, ...], k: int | None) -> tuple[int, ...]:
    """Indices of the children shown: all (k is None), or the first k, the stand-outs and the last few."""
    n = len(children)
    if k is None:
        return tuple(range(n))
    return tuple(sorted({*range(k), *_promotion(f, children).picks, *range(n - _TAIL_CHILDREN, n)}))


def _open_cost(f: _Fold, first: int, last: int, children: tuple[Node, ...], k: int | None) -> int:
    shown = set(_shown_children(f, children, k))
    cost, cursor, hidden_run = 0, first, False
    for i, c in enumerate(children):
        if i in shown:  # the lines before a shown child are shown, after a hidden run too
            cost += _span(f, cursor, c.first - 1) + _folded_cost(f, c)
            hidden_run = False
        elif not hidden_run:
            cost += _span(f, cursor, c.first - 1) + _MARKER_TOKENS
            hidden_run = True
        cursor = c.last + 1
    return cost + _span(f, cursor, last)


def _choose(
    f: _Fold, first: int, last: int, children: tuple[Node, ...], room: int
) -> tuple[bool, int | None, int]:
    """Whether a node opens within `room` tokens, how (None: in full; k: its first k children, the
    stand-outs and the last few), and at what cost. Partly, it takes the most children that fit in
    half the room, keeping the rest for opening what it shows: breadth before depth."""
    full = _open_cost(f, first, last, children, None)
    if full <= room:
        return True, None, full
    if len(children) <= _HEAD_CHILDREN + _TAIL_CHILDREN + 1:
        return False, None, 0
    if _open_cost(f, first, last, children, _HEAD_CHILDREN) > room:
        return False, None, 0
    lo, hi = _HEAD_CHILDREN, len(children) - _TAIL_CHILDREN - 1
    while lo < hi:  # the largest k whose cost fits in half the room (at least _HEAD_CHILDREN)
        mid = (lo + hi + 1) // 2
        if _open_cost(f, first, last, children, mid) <= room // 2:
            lo = mid
        else:
            hi = mid - 1
    return True, lo, _open_cost(f, first, last, children, lo)


def _is_container(f: _Fold, n: Node) -> bool:
    """Opening it mostly shows its children's headers (a class, an element), not its own lines.
    Runs of plain lines are not structure: a function whose body is one run is a body."""
    if not any(not c.run for c in n.children):
        return False
    full = _open_cost(f, n.first, n.last, n.children, None)
    return full - sum(_folded_cost(f, c) for c in n.children) <= 0.25 * full


def _key(f: _Fold, depth: int, n: Node, standout: bool) -> tuple[int, int, int, int]:
    """The order nodes open in: stand-outs, then containers, then bodies with structure inside, by
    depth and source order (so the biggest class is not left last with room for only part of its
    outline), then leaves (a docstring, a literal, a block with nothing foldable inside), cheapest
    first, so a long docstring waits."""
    if standout:
        rank = 0
    elif _is_container(f, n):
        rank = 1
    else:
        rank = 2 if any(not c.run for c in n.children) else 3
    cost = _open_cost(f, n.first, n.last, n.children, None) - _folded_cost(f, n) if rank == 3 else 0
    return (rank, depth, cost, n.first)


def _plan(f: _Fold, roots: tuple[Node, ...], budget_tokens: int) -> _Plan:
    """Which nodes open, and how far: the top-level outline first (or as much of it as fits), then
    one node at a time in `_key` order, each opening in full or partly when that fits what is left."""
    last = len(f.lines) - 1
    _, root_k, total = _choose(f, 0, last, roots, budget_tokens)
    if total == 0:  # not even the minimal outline fits: show it anyway, it is the floor
        root_k = _HEAD_CHILDREN if len(roots) > _HEAD_CHILDREN + _TAIL_CHILDREN + 1 else None
        total = _open_cost(f, 0, last, roots, root_k)
    opened: dict[int, int | None] = {}
    heap: list[tuple[int, int, int, int, Node]] = []

    def push(depth: int, children: tuple[Node, ...], k: int | None) -> None:
        picks = _promotion(f, children).picks
        for i in _shown_children(f, children, k):
            if not _small(children[i]):
                heapq.heappush(heap, (*_key(f, depth, children[i], i in picks), children[i]))

    push(1, roots, root_k)
    while heap:
        _, depth, _, _, n = heapq.heappop(heap)
        room = budget_tokens - total + _folded_cost(f, n)
        fits, k, cost = _choose(f, n.first, n.last, n.children, room)
        if fits:
            opened[id(n)] = k
            total += cost - _folded_cost(f, n)
            push(depth + 1, n.children, k)
    return _Plan(root_k, opened)


@dataclass(frozen=True)
class _Open:
    """A list of children rendered in place: the top level, or the children of a node shown open."""

    first: int
    last: int
    kids: tuple[Node, ...]
    k: int | None


def _render(f: _Fold, roots: tuple[Node, ...], plan: _Plan) -> tuple[str, int, int]:
    """The plan as text, and how many nodes it shows open and folded. Each list renders as a
    generator of chunks of lines, and of the open children to render in their place: a stack of
    them, not recursion, since open nodes can nest as deep as the input does."""
    folded = 0
    prefix = "\t" if f.numbered else ""

    def walk(o: _Open) -> Iterator[tuple[str, ...] | _Open]:
        nonlocal folded
        shown = set(_shown_children(f, o.kids, o.k))
        cursor, i = o.first, 0
        while i < len(o.kids):
            c = o.kids[i]
            yield f.shown[cursor : c.first]
            if i in shown:
                if _small(c):
                    yield f.shown[c.first : c.last + 1]
                elif id(c) in plan.opened:
                    yield _Open(c.first, c.last, c.children, plan.opened[id(c)])
                else:
                    folded += 1
                    note = markers.lines_folded(c.head_end + 2, c.last + 1, f"{c.last - c.head_end} lines")
                    if c.head_end == c.first:
                        yield (f"{f.shown[c.first]}  {note}",)
                    else:
                        under = f"{prefix}{_indent_of(f.lines[c.head_end])}    {note}"
                        yield (*f.shown[c.first : c.head_end + 1], under)
                cursor, i = c.last + 1, i + 1
                continue
            j = i
            while j + 1 < len(o.kids) and j + 1 not in shown:
                j += 1
            a, b = c.first, o.kids[j].last
            folded += j - i + 1
            more = sum(1 for x in _promotion(f, o.kids).unshown if i <= x <= j)
            what = markers.siblings(j - i + 1, more)
            yield (f"{prefix}{_indent_of(f.lines[a])}{markers.lines_folded(a + 1, b + 1, what)}",)
            cursor, i = b + 1, j + 1
        yield f.shown[cursor : o.last + 1]

    out: list[str] = []
    stack = [walk(_Open(0, len(f.lines) - 1, roots, plan.root_k))]
    while stack:
        match next(stack[-1], None):
            case None:
                stack.pop()
            case _Open() as o:
                stack.append(walk(o))
            case tuple() as chunk:
                out.extend(chunk)
    return "\n".join(out), len(plan.opened), folded


def fold_tree(
    lines: list[str],
    roots: tuple[Node, ...],
    budget_tokens: int,
    *,
    numbered: bool = True,
    terms: frozenset[str] = frozenset(),
) -> tuple[str, int, int]:
    """The folded text, and how many nodes it shows open and folded.

    Containers (nodes whose opening mostly shows their children's headers: a class, an element)
    open before bodies (functions, blocks), and shallower before deeper. A node opens in full when
    that fits; otherwise, when it has many children, it opens partly: as many of its first children
    as fit in half the room left (at least three), its last, and its stand-outs, with each run
    between them as one marker. A folded node with a one-line header carries its marker on that line.
    """
    f = _fold_of(lines, numbered, terms)
    roots = _with_gaps(lines, roots, 0, len(lines) - 1, _MIN_GAP)
    return _render(f, roots, _plan(f, roots, budget_tokens))


# --- indentation outlines -----------------------------------------------------------------------


def indent_tree(lines: list[str]) -> tuple[Node, ...]:
    """Every non-blank line is a node; the lines indented under it are its children."""
    roots: list[Node] = []
    stack: list[tuple[int, int, list[Node]]] = []  # (indent, first, children)
    last_nonblank = -1

    def close(upto_indent: int) -> None:
        while stack and stack[-1][0] >= upto_indent:
            indent, first, kids = stack.pop()
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


def fold_xml(raw: str, budget_tokens: int, terms: frozenset[str] = frozenset()) -> TreeFold | None:
    tree = xml_tree(raw)
    return None if tree is None else fold_xml_tree(tree, budget_tokens, terms)


def fold_xml_tree(tree: XmlTree, budget_tokens: int, terms: frozenset[str] = frozenset()) -> TreeFold:
    """`fold_xml` for XML already parsed (the router parses once, to detect it)."""
    text, opened, folded = fold_tree(tree.lines, tree.roots, budget_tokens, numbered=False, terms=terms)
    return TreeFold(text, "\n".join(tree.lines), opened, folded)


def fold_outline(raw: str, budget_tokens: int, terms: frozenset[str] = frozenset()) -> TreeFold:
    lines = split_lines(raw)
    text, opened, folded = fold_tree(lines, indent_tree(lines), budget_tokens, numbered=False, terms=terms)
    return TreeFold(text, raw, opened, folded)
