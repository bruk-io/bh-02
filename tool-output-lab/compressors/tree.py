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
import re
import xml.dom.minidom
import xml.parsers.expat
from collections import Counter
from dataclasses import dataclass

from compressors.common import estimate_tokens, split_identifiers

_VARIABLE = re.compile(r"0x[0-9a-fA-F]+|[0-9a-fA-F]{8,}|\d+")

_MARKER_TOKENS = 12


@dataclass(frozen=True)
class Node:
    first: int  # 0-based index of the node's first line
    head_end: int  # last line of the header, shown when folded (>= first)
    last: int  # last line of the node (>= head_end)
    children: tuple[Node, ...] = ()


@dataclass(frozen=True)
class TreeFold:
    text: str  # what the reader sees
    source: str  # the text the markers' line numbers refer to (raw, or raw pretty-printed)
    expanded: int  # nodes shown open
    folded: int  # nodes shown as a header and a marker


def _prune(nodes: tuple[Node, ...], min_hidden: int) -> tuple[Node, ...]:
    """Drop nodes too small to be worth a marker; their lines then show as plain lines."""
    return tuple(
        Node(n.first, n.head_end, n.last, _prune(n.children, min_hidden))
        for n in nodes
        if n.last - n.head_end >= min_hidden
    )


def _signature(lines: list[str], n: Node, cap: int = 600) -> str:
    """A sibling's shape: its lines with numbers blanked out, up to `cap` characters, so a list
    item whose button is disabled differs from its siblings even though their headers match."""
    out, size = [], 0
    for i in range(n.first, n.last + 1):
        line = _VARIABLE.sub("#", lines[i].strip())
        out.append(line)
        size += len(line)
        if size >= cap:
            break
    return "\n".join(out)


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def fold_tree(
    lines: list[str],
    roots: tuple[Node, ...],
    budget_tokens: int,
    *,
    numbered: bool = True,
    min_hidden: int = 3,
    max_line_chars: int = 300,
    head_children: int = 3,
    tail_children: int = 1,
    max_promoted: int = 3,
    terms: frozenset[str] = frozenset(),
) -> tuple[str, int, int]:
    """The folded text, and how many nodes it shows open and folded.

    Containers (nodes whose opening mostly shows their children's headers: a class, an element)
    open before bodies (functions, blocks), and shallower before deeper. A node opens in full when
    that fits; otherwise, when it has many children, it opens partly:
    as many of its first children as fit in half the room left (at least `head_children`) and its
    last `tail_children`, with the run between them as one marker. A folded node with a one-line
    header carries its marker on that line.
    """

    def shown(i: int) -> str:
        line = lines[i]
        if len(line) > max_line_chars:
            line = line[:max_line_chars] + f"...[+{len(line) - max_line_chars} chars]"
        return f"{i + 1}\t{line}" if numbered else line

    line_cost = [estimate_tokens(shown(i)) + 1 for i in range(len(lines))]
    roots = _prune(roots, min_hidden)

    def span_cost(a: int, b: int) -> int:
        return sum(line_cost[a : b + 1])

    def folded_cost(n: Node) -> int:
        return span_cost(n.first, n.head_end) + _MARKER_TOKENS

    standouts: set[tuple[int, int]] = set()

    def promoted(children: tuple[Node, ...]) -> tuple[int, ...]:
        """Children that stand out among siblings that mostly share one shape, or that hold a query
        term few siblings share. They open first, since what they hold is why they are shown."""
        n = len(children)
        if n < 10:
            return ()
        patterns = [_signature(lines, c) for c in children]
        counts = Counter(patterns)
        rare_cut = max(1, int(0.05 * n))
        dominant = counts.most_common(1)[0][1] / n >= 0.6
        words = [
            set(split_identifiers(" ".join(lines[c.first : min(c.last, c.first + 8) + 1]))) for c in children
        ]
        useful = frozenset(t for t in terms if sum(t in w for w in words) <= rare_cut)
        picks = [
            i
            for i, (pat, w) in enumerate(zip(patterns, words, strict=True))
            if (dominant and counts[pat] <= rare_cut) or (useful and w & useful)
        ][:max_promoted]
        standouts.update((children[i].first, children[i].last) for i in picks)
        return tuple(picks)

    def shown_children(children: tuple[Node, ...], k: int | None) -> tuple[int, ...]:
        """Indices of the children shown: all (k is None), or the first k, the stand-outs and the last few."""
        n = len(children)
        if k is None:
            return tuple(range(n))
        return tuple(sorted({*range(k), *promoted(children), *range(n - tail_children, n)}))

    def open_cost(first: int, last: int, children: tuple[Node, ...], k: int | None) -> int:
        shown_set = set(shown_children(children, k))
        cost, cursor, hidden_run = 0, first, False
        for i, c in enumerate(children):
            if i in shown_set:
                if not hidden_run:
                    cost += span_cost(cursor, c.first - 1)
                cost += folded_cost(c)
                hidden_run = False
            elif not hidden_run:
                cost += span_cost(cursor, c.first - 1) + _MARKER_TOKENS
                hidden_run = True
            cursor = c.last + 1
        return cost + span_cost(cursor, last)

    def choose(first: int, last: int, children: tuple[Node, ...], room: int) -> tuple[bool, int | None, int]:
        """Whether a node opens within `room` tokens, how (None: in full; k: its first k children,
        the stand-outs and the last few), and at what cost. Partly, it takes the most children that
        fit in half the room, keeping the rest for opening what it shows: breadth before depth."""
        full = open_cost(first, last, children, None)
        if full <= room:
            return True, None, full
        if len(children) <= head_children + tail_children + 1:
            return False, None, 0
        if open_cost(first, last, children, head_children) > room:
            return False, None, 0
        lo, hi = head_children, len(children) - tail_children - 1
        while lo < hi:  # the largest k whose cost fits in half the room (at least head_children)
            mid = (lo + hi + 1) // 2
            if open_cost(first, last, children, mid) <= room // 2:
                lo = mid
            else:
                hi = mid - 1
        return True, lo, open_cost(first, last, children, lo)

    _, root_k, total = choose(0, len(lines) - 1, roots, budget_tokens)
    if total == 0:  # not even the minimal outline fits: show it anyway, it is the floor
        root_k = head_children if len(roots) > head_children + tail_children + 1 else None
        total = open_cost(0, len(lines) - 1, roots, root_k)
    opened: dict[tuple[int, int], int | None] = {}  # (first, last) -> k, None when open in full

    def is_container(n: Node) -> bool:
        """Opening it mostly shows its children's headers (a class, an element), not its own lines."""
        if not n.children:
            return False
        own = open_cost(n.first, n.last, n.children, None) - sum(folded_cost(c) for c in n.children)
        return own <= 0.25 * open_cost(n.first, n.last, n.children, None)

    def key(depth: int, n: Node) -> tuple[int, int, int, int]:
        """Stand-outs open first, then containers, then bodies; shallower first, cheaper first."""
        rank = 0 if (n.first, n.last) in standouts else 1 if is_container(n) else 2
        return (rank, depth, folded_cost(n), n.first)

    heap = [(*key(1, roots[i]), roots[i]) for i in shown_children(roots, root_k)]
    heapq.heapify(heap)
    while heap:
        _, depth, _, _, n = heapq.heappop(heap)
        room = budget_tokens - total + folded_cost(n)
        fits, k, cost = choose(n.first, n.last, n.children, room)
        if not fits:
            continue
        opened[(n.first, n.last)] = k
        total += cost - folded_cost(n)
        for i in shown_children(n.children, k):
            c = n.children[i]
            heapq.heappush(heap, (*key(depth + 1, c), c))

    out: list[str] = []
    counts = [0, 0]
    prefix = "\t" if numbered else ""

    def emit(a: int, b: int) -> None:
        out.extend(shown(i) for i in range(a, b + 1))

    def marker(a: int, b: int, what: str) -> str:
        return f"[... lines {a + 1}-{b + 1} folded ({what})]"

    def render_child(c: Node) -> None:
        if (c.first, c.last) in opened:
            counts[0] += 1
            render(c.first, c.last, c.children, opened[(c.first, c.last)])
            return
        counts[1] += 1
        note = marker(c.head_end + 1, c.last, f"{c.last - c.head_end} lines")
        if c.head_end == c.first:
            out.append(f"{shown(c.first)}  {note}")
        else:
            emit(c.first, c.head_end)
            out.append(f"{prefix}{_indent_of(lines[c.head_end])}    {note}")

    def render(first: int, last: int, children: tuple[Node, ...], k: int | None) -> None:
        shown_set = set(shown_children(children, k))
        cursor, i = first, 0
        while i < len(children):
            c = children[i]
            emit(cursor, c.first - 1)
            if i in shown_set:
                render_child(c)
                cursor, i = c.last + 1, i + 1
                continue
            j = i
            while j + 1 < len(children) and j + 1 not in shown_set:
                j += 1
            a, b = c.first, children[j].last
            counts[1] += j - i + 1
            out.append(f"{prefix}{_indent_of(lines[a])}{marker(a, b, f'{j - i + 1} siblings')}")
            cursor, i = b + 1, j + 1
        emit(cursor, last)

    render(0, len(lines) - 1, roots, root_k)
    return "\n".join(out), counts[0], counts[1]


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


def _pretty(raw: str) -> str:
    """One element per line, when the XML came packed onto few lines."""
    lines = raw.splitlines()
    if len(lines) >= raw.count("<") / 4 and max((len(line) for line in lines), default=0) <= 1000:
        return raw
    pretty = xml.dom.minidom.parseString(raw.encode("utf-8")).toprettyxml(indent="  ")
    return "\n".join(line for line in pretty.splitlines() if line.strip())


def xml_tree(raw: str) -> tuple[list[str], tuple[Node, ...]] | None:
    """The XML's lines (pretty-printed if it came packed) and its element tree; None if not XML."""
    try:
        source = _pretty(raw)
    except Exception:  # minidom raises a handful of unrelated types on bad input  # noqa: BLE001
        return None
    parser = xml.parsers.expat.ParserCreate()
    stack: list[tuple[int, list[Node]]] = [(-1, [])]

    def start(_name: str, _attrs: dict[str, str]) -> None:
        stack.append((parser.CurrentLineNumber - 1, []))

    def end(_name: str) -> None:
        first, kids = stack.pop()
        stack[-1][1].append(Node(first, first, parser.CurrentLineNumber - 1, tuple(kids)))

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        parser.Parse(source, True)
    except xml.parsers.expat.ExpatError:
        return None
    return source.splitlines(), tuple(stack[0][1])


def fold_xml(raw: str, budget_tokens: int, terms: frozenset[str] = frozenset()) -> TreeFold | None:
    parsed = xml_tree(raw)
    if parsed is None:
        return None
    lines, roots = parsed
    text, opened, folded = fold_tree(lines, roots, budget_tokens, numbered=False, terms=terms)
    return TreeFold(text, "\n".join(lines), opened, folded)


def fold_outline(raw: str, budget_tokens: int, terms: frozenset[str] = frozenset()) -> TreeFold:
    lines = raw.splitlines()
    text, opened, folded = fold_tree(lines, indent_tree(lines), budget_tokens, numbered=False, terms=terms)
    return TreeFold(text, raw, opened, folded)
