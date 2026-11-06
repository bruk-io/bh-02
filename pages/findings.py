"""The findings page: results/FINDINGS.md as one self-contained HTML page, written to pages/findings.html.

The text is the file's. The page adds what Markdown cannot show, from markers that are HTML comments
(so GitHub shows nothing for them):

    <!-- figure: NAME -->                    assets/NAME.svg.html as it is
    <!-- stats: V=TEXT; V=TEXT | NOTE -->       headline figures
    <!-- chart: paired | TITLE -->            the next table: a row per run, two columns of "a of b"
    <!-- chart: bars N | TITLE -->            the next table: column N as one series
    <!-- chart: stacked | TITLE -->           the next table: rows are parts, columns are wholes, in %
    <!-- chart: scale A=N; B=M | TITLE -->    two sizes on one scale
    <!-- annotated -->                         the next code block, a section at a time, beside the next list
    <!-- pair -->                              the next code block beside the next paragraph
    <!-- more: SUMMARY --> ... <!-- /more -->  folded under SUMMARY
    <!-- grid --> ... <!-- /grid -->           each ### and what follows it as a card

Code blocks are envelope text and are highlighted as such. Everything here is pure but `main`.
"""

import argparse
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_LAB = Path(__file__).resolve().parent.parent
_ASSETS = Path(__file__).resolve().parent / "assets"
SOURCE = _LAB / "results" / "FINDINGS.md"
OUT = _LAB / "pages" / "findings.html"
TITLE = "Envelope Findings"


@dataclass(frozen=True)
class Block:
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Mark:
    name: str
    arg: str


@dataclass(frozen=True)
class Wrap:
    name: str  # more or grid
    arg: str
    children: tuple[Node, ...]


type Node = Block | Mark | Wrap


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _attr(s: str) -> str:
    return html.escape(s, quote=True)


def slug(title: str) -> str:
    """A heading's anchor, as GitHub makes it for these headings."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def inline(s: str) -> str:
    """Markdown's inline marks: `code`, **bold**, and links (a link within the page gets an arrow)."""
    s = _esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\((#[^)]+)\)", r'<a class="go" href="\2">\1</a>', s)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)


# --- envelope text, highlighted --------------------------------------------------------------------

_LABEL = re.compile(r"^(shape|anomalies|samples|get more):")
_ADDRESS = re.compile(r"^(\s*)(\d+:)(\s.*)?$")  # a line number, then the output's own text
_TOKEN = re.compile(
    r"(?P<c>\s\s\([^()]*\)$|\(<\*>[^()]*\)$)"  # a note at the end of a line
    r"|(?P<s>\"[^\"]*\")"  # a value
    r"|(?P<q>'[^']*')"  # a command's argument
    r"|(?P<x>^\s*(?:jq|grep|sed)\b|\bFILE\b)"  # a command, and the file it reads
    r"|(?P<p>\.[A-Za-z_]\w*(?:\[\d*\])?(?:\.[A-Za-z_]\w*)*)"  # a jq path
    r"|(?P<h><\*>|<n>)"  # a hole in a pattern
    r"|(?P<n>\b\d[\d,]*(?:\.\d+)?\b)"  # a count
)


def _span(cls: str, text: str) -> str:
    return f'<span class="{cls}">{_esc(text)}</span>'


def _tokens(text: str) -> str:
    out, at = [], 0
    for m in _TOKEN.finditer(text):
        out.append(_esc(text[at : m.start()]))
        kind = m.lastgroup or ""
        out.append(_span("s" if kind == "q" else kind, m.group()))
        at = m.end()
    return "".join(out) + _esc(text[at:])


def _banner(line: str) -> str:
    out, at = [], 0
    for m in re.finditer(r"/[\w./-]+\w|~\d+", line):
        out.append(_esc(line[at : m.start()]))
        out.append(_span("p" if m.group().startswith("/") else "n", m.group()))
        at = m.end()
    return "".join(out) + _esc(line[at:])


def highlight(line: str) -> str:
    """One line of an envelope with its parts marked: section names, paths and line numbers, values,
    commands, holes, counts and notes. A line the output itself said stays as it was."""
    if line.startswith("[Folded"):
        return _banner(line)
    if m := _LABEL.match(line):
        return _span("k", m.group()) + _tokens(line[m.end() :])
    if m := _ADDRESS.match(line):
        return _esc(m.group(1)) + _span("p", m.group(2)) + _esc(m.group(3) or "")
    return _tokens(line)


def code(lines: tuple[str, ...]) -> str:
    """A code block; one long line wraps, while a block of lines keeps its columns and scrolls."""
    wrap = ' class="wrap"' if len(lines) == 1 else ""
    return f"<pre{wrap}>{chr(10).join(highlight(ln) for ln in lines)}</pre>"


# --- blocks ----------------------------------------------------------------------------------------

_MARK = re.compile(r"<!-- (/?)([a-z]+)(?:: (.*?))? -->")


def blocks(text: str) -> list[tuple[str, ...]]:
    """The text's blocks: a fenced code block whole (its first line "```"), else what blank lines part."""
    out: list[tuple[str, ...]] = []
    for i, piece in enumerate(re.split(r"(?ms)^```\n(.*?)^```$", text.strip())):
        if i % 2:
            out.append(("```", *piece.rstrip("\n").splitlines()))
            continue
        out += [tuple(chunk.splitlines()) for chunk in re.split(r"\n\s*\n", piece.strip()) if chunk.strip()]
    return out


def tree(bs: list[tuple[str, ...]]) -> tuple[Node, ...]:
    """The blocks as nodes, a fold or a grid holding what its markers enclose.

    Raises:
        ValueError: a closing marker closes nothing open, or an opening one is never closed.
    """
    stack: list[tuple[Mark, list[Node]]] = [(Mark("", ""), [])]
    for b in bs:
        m = _MARK.fullmatch(b[0]) if len(b) == 1 else None
        if m is None:
            stack[-1][1].append(Block(b))
            continue
        close, name, arg = m.group(1), m.group(2), m.group(3) or ""
        if close:
            if stack[-1][0].name != name:
                raise ValueError(f"<!-- /{name} --> closes nothing open: open it with <!-- {name} --> first")
            opened, children = stack.pop()
            stack[-1][1].append(Wrap(name, opened.arg, tuple(children)))
        elif name in ("more", "grid"):
            stack.append((Mark(name, arg), []))
        else:
            stack[-1][1].append(Mark(name, arg))
    if len(stack) > 1:
        raise ValueError(
            f"<!-- {stack[-1][0].name} --> is never closed: end it with <!-- /{stack[-1][0].name} -->"
        )
    return tuple(stack[0][1])


def rows_of(lines: tuple[str, ...]) -> tuple[list[str], list[list[str]]]:
    """A pipe table's head and rows, its rule left out."""
    rows = [
        [c.strip() for c in ln.strip().strip("|").split("|")]
        for ln in lines
        if not re.match(r"^\|[-| ]+\|$", ln)
    ]
    return rows[0], rows[1:]


def table(lines: tuple[str, ...]) -> str:
    head, body = rows_of(lines)
    numeric = [
        i > 0 and all(not r[i] or (r[i][0].isdigit() and len(r[i]) <= 16) for r in body)
        for i in range(len(head))
    ]
    th = "".join(
        f'<th scope="col"{' class="n"' if numeric[i] else ""}>{inline(h)}</th>' for i, h in enumerate(head)
    )
    tb = "".join(
        "<tr>"
        + "".join(f"<td{' class="n"' if numeric[i] else ''}>{inline(c)}</td>" for i, c in enumerate(r))
        + "</tr>"
        for r in body
    )
    return f'<div class="well"><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>'


def items(lines: tuple[str, ...]) -> list[str]:
    """A list's items, each joined from the lines it wraps onto."""
    got: list[str] = []
    for ln in lines:
        if re.match(r"^(- |\d+\. )", ln):
            got.append(re.sub(r"^(- |\d+\. )", "", ln))
        else:
            got[-1] += " " + ln.strip()
    return got


def block(lines: tuple[str, ...]) -> str:
    first = lines[0]
    if first == "```":
        return code(lines[1:])
    if first.startswith("### "):
        name = first[4:]
        rest = block(lines[1:]) if lines[1:] else ""
        return f'<h3 id="{slug(name)}">{inline(name)}</h3>{rest}'
    if first.startswith("|"):
        return f"<figure>{table(lines)}</figure>"
    if first.startswith("- "):
        return '<ul class="points">' + "".join(f"<li>{inline(i)}</li>" for i in items(lines)) + "</ul>"
    if re.match(r"^\d+\. ", first):
        return '<ol class="points">' + "".join(f"<li>{inline(i)}</li>" for i in items(lines)) + "</ol>"
    return f"<p>{inline(' '.join(ln.strip() for ln in lines))}</p>"


# --- figures and charts ----------------------------------------------------------------------------


def _of(cell: str) -> tuple[int, int]:
    """ "104 of 104" as its two numbers.

    Raises:
        ValueError: the cell is not "a of b".
    """
    m = re.fullmatch(r"(\d[\d,]*) of (\d[\d,]*)", cell)
    if m is None:
        raise ValueError(f"a paired chart's cells read 'a of b', such as '80 of 80', not {cell!r}")
    return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))


def _num(cell: str) -> float:
    """The number a cell starts with: "6,158 tokens" is 6158.

    Raises:
        ValueError: the cell does not start with a number.
    """
    m = re.match(r"\d[\d,]*(?:\.\d+)?", cell)
    if m is None:
        raise ValueError(
            f"a chart's cells start with a number, such as '6,158 tokens' or '25%', not {cell!r}"
        )
    return float(m.group().replace(",", ""))


def _bar(cls: str, share: float, value: str, tip: str, track: bool) -> str:
    width = f"{max(share * 100, 0.6):.1f}%"
    return (
        f'<div class="bar"><span class="track{"" if track else " bare"}">'
        f'<span class="fill {cls}" style="width:{width}" data-tip="{_attr(tip)}"></span></span>'
        f'<span class="val">{_esc(value)}</span></div>'
    )


def _legend(pairs: list[tuple[str, str]]) -> str:
    return (
        '<ul class="legend">'
        + "".join(f'<li><i class="sw {c}"></i>{inline(t)}</li>' for c, t in pairs)
        + "</ul>"
    )


def _chart(title: str, legend: str, rows: str, cls: str = "chart") -> str:
    caption = f'<figcaption class="ct">{_esc(title)}</figcaption>'
    return f'<figure class="{cls}">{caption}{legend}<div class="crows">{rows}</div></figure>'


def paired(title: str, lines: tuple[str, ...]) -> str:
    """Each row's two shares of a whole, with the envelope and without, on tracks that show the whole."""
    head, body = rows_of(lines)
    out = []
    for r in body:
        bars = "".join(
            _bar(cls, a / b, f"{a} of {b}", f"{name}: {a} of {b}", True)
            for cls, name, (a, b) in zip(("acc", "mut"), head[1:3], (_of(r[1]), _of(r[2])), strict=True)
        )
        out.append(
            f'<div class="row"><div class="rl">{inline(r[0])}</div><div class="bars">{bars}</div></div>'
        )
    return _chart(title, _legend([("acc", head[1]), ("mut", head[2])]), "".join(out))


def bars(title: str, lines: tuple[str, ...], col: int) -> str:
    """One column of a table as one series of bars, the longest to scale."""
    _, body = rows_of(lines)
    top = max(_num(r[col]) for r in body)
    out = "".join(
        f'<div class="row"><div class="rl">{inline(r[0])}</div><div class="bars">'
        f"{_bar('acc', _num(r[col]) / top, r[col], f'{r[0]}: {r[col]}', False)}</div></div>"
        for r in body
    )
    return _chart(title, "", out)


_PARTS = ("acc", "acc2", "mut", "mut2")  # the envelope's own parts in its hue, the model's own in grey


def stacked(title: str, lines: tuple[str, ...]) -> str:
    """Each column a whole split into the table's rows, one segmented bar per whole; a share of 12% or
    more is printed on its segment, and every share is in the hover and the table."""
    head, body = rows_of(lines)
    out = []
    for w, whole in enumerate(head[1:], start=1):
        segs = []
        for p, r in enumerate(body):
            pct = _num(r[w])
            if pct == 0:
                continue
            tip = f"{r[0].replace('`', '')}: {pct:g}%"
            label = f"{pct:g}%" if pct >= 12 else ""
            segs.append(
                f'<span class="sg {_PARTS[p]}" style="flex-grow:{pct:g}" data-tip="{_attr(tip)}" '
                f'aria-label="{_attr(tip)}">{label}</span>'
            )
        out.append(
            f'<div class="row"><div class="rl">{inline(whole)}</div>'
            f'<div class="segs" role="img" aria-label="{_attr(whole)}">{"".join(segs)}</div></div>'
        )
    return _chart(title, _legend([(_PARTS[p], r[0]) for p, r in enumerate(body)]), "".join(out))


def scale(title: str, arg: str) -> str:
    """Two sizes on one scale, such as an output and what replaced it."""
    pairs = [(k.strip(), int(v)) for k, v in (x.split("=") for x in arg.split(";"))]
    top = max(v for _, v in pairs)
    out = "".join(
        f'<div class="row"><div class="rl">{_esc(k)}</div><div class="bars">'
        f"{_bar(cls, v / top, f'{v:,} tokens', f'{k}: {v:,} tokens', False)}</div></div>"
        for cls, (k, v) in zip(("mut", "acc"), pairs, strict=True)
    )
    return _chart(title, "", out, "chart scale")


def stats(arg: str) -> str:
    """Headline figures, each a value and what it counts, with a note on where they come from."""
    figures, _, note = arg.partition("|")
    tiles = "".join(
        f'<div class="tile"><span class="sv">{_esc(v.strip())}</span><p>{_esc(t.strip())}</p></div>'
        for v, t in (x.split("=", 1) for x in figures.split(";"))
    )
    note_html = f'<p class="note">{_esc(note.strip())}</p>'
    return f'<div class="stats"><div class="readouts rows">{tiles}</div>{note_html}</div>'


_SECTIONS = {"shape": "shape", "anomalies": "anom", "samples": "samp", "get more": "more"}


def annotated(code_lines: tuple[str, ...], list_lines: tuple[str, ...]) -> str:
    """The envelope a section at a time, each with its note: beside it on a wide screen, under it on a phone.

    Raises:
        ValueError: a note does not start with its section's name, or the notes and sections differ.
    """
    notes: dict[str, str] = {}
    for it in items(list_lines):
        m = re.match(r"`([a-z ]+):` (.*)", it)
        if m is None:
            raise ValueError(
                f"an annotation starts with its section's name in backticks, such as `shape:`: {it[:40]}"
            )
        notes[m.group(1)] = m.group(2)
    parts: list[tuple[str, list[str]]] = []
    for ln in code_lines:
        if m := _LABEL.match(ln):
            parts.append((m.group(1), []))
        if not parts:
            raise ValueError(f"an annotated envelope starts with a section such as 'shape:', not {ln!r}")
        parts[-1][1].append(ln)
    if [n for n, _ in parts] != list(notes):
        raise ValueError(
            f"every section needs one note, in order: sections {[n for n, _ in parts]}, notes {list(notes)}"
        )
    rows = "".join(
        f'<div class="ar {_SECTIONS[name]}">{code(tuple(ls))}'
        f'<p class="an"><span class="ak"><i class="sw"></i>{_esc(name)}</span>{inline(notes[name])}</p></div>'
        for name, ls in parts
    )
    return f'<div class="annot" role="group" aria-label="The envelope, a section at a time">{rows}</div>'


def pair(code_lines: tuple[str, ...], para: tuple[str, ...]) -> str:
    return f'<div class="pairing">{code(code_lines)}<div class="pn">{block(para)}</div></div>'


# --- rendering -------------------------------------------------------------------------------------


def _following(nodes: tuple[Node, ...], i: int, n: int, name: str) -> list[tuple[str, ...]]:
    """The `n` blocks after the marker at `i`.

    Raises:
        ValueError: fewer than `n` blocks follow it.
    """
    got = [x.lines for x in nodes[i + 1 : i + 1 + n] if isinstance(x, Block)]
    if len(got) < n:
        raise ValueError(f"<!-- {name} --> draws the {n} block(s) after it, and only {len(got)} follow")
    return got


def _mark(mark: Mark, nodes: tuple[Node, ...], i: int, figures: dict[str, str]) -> tuple[str, int]:
    """What a marker draws, and how many of the nodes after it it used.

    Raises:
        ValueError: the marker names no figure, chart or layout this page knows.
    """
    match mark.name:
        case "figure":
            if mark.arg not in figures:
                raise ValueError(f"no figure named {mark.arg!r}: add assets/{mark.arg}.svg.html")
            return figures[mark.arg], 0
        case "stats":
            return stats(mark.arg), 0
        case "chart":
            spec, _, title = mark.arg.partition(" | ")
            kind, *rest = spec.split()
            if kind == "scale":
                return scale(title, " ".join(rest)), 0
            (lines,) = _following(nodes, i, 1, f"chart: {kind}")
            match kind:
                case "paired":
                    return paired(title, lines), 1
                case "bars":
                    return bars(title, lines, int(rest[0])), 1
                case "stacked":
                    return stacked(title, lines), 1
            raise ValueError(f"no chart named {kind!r}: use paired, bars N, stacked or scale")
        case "annotated":
            envelope, notes = _following(nodes, i, 2, "annotated")
            return annotated(envelope[1:], notes), 2
        case "pair":
            example, para = _following(nodes, i, 2, "pair")
            return pair(example[1:], para), 2
    raise ValueError(f"no marker named {mark.name!r}: see the list at the top of pages/findings.py")


def render(nodes: tuple[Node, ...], figures: dict[str, str]) -> str:
    out: list[str] = []
    i = 0
    while i < len(nodes):
        match nodes[i]:
            case Block(lines):
                out.append(block(lines))
            case Wrap("more", arg, children):
                out.append(
                    f'<details class="more"><summary>{inline(arg)}</summary>'
                    f'<div class="mi">{render(children, figures)}</div></details>'
                )
            case Wrap(_, _, children):
                out.append(cards(children, figures))
            case Mark() as mark:
                drawn, used = _mark(mark, nodes, i, figures)
                out.append(drawn)
                i += used
        i += 1
    return "".join(out)


def cards(nodes: tuple[Node, ...], figures: dict[str, str]) -> str:
    """Each ### heading and what follows it as one card.

    Raises:
        ValueError: the grid does not start with a ### heading.
    """
    groups: list[list[Node]] = []
    for n in nodes:
        if isinstance(n, Block) and n.lines[0].startswith("### "):
            groups.append([])
        if not groups:
            raise ValueError("a grid starts with a ### heading, one per card")
        groups[-1].append(n)
    return (
        '<div class="cards">'
        + "".join(f'<div class="card">{render(tuple(g), figures)}</div>' for g in groups)
        + "</div>"
    )


def page(text: str, figures: dict[str, str], dated: str) -> str:
    """The page's body from the text of FINDINGS.md: a section list, the header, and a section per ##.

    Raises:
        ValueError: the text does not start with its # title.
    """
    title_line, _, rest = text.partition("\n")
    if not title_line.startswith("# "):
        raise ValueError("FINDINGS.md starts with its title, as '# Title'")
    parts = re.split(r"(?m)^## (.+)$", rest)
    names = parts[1::2]
    sections = "".join(
        f'\n  <section id="{slug(name)}" aria-labelledby="{slug(name)}-h">\n'
        f'    <div class="sh"><h2 id="{slug(name)}-h">{inline(name)}</h2></div>\n'
        f"    {render(tree(blocks(body)), figures)}\n  </section>"
        for name, body in zip(names, parts[2::2], strict=True)
    )
    chips = "".join(f'<a href="#{slug(n)}">{inline(n)}</a>' for n in names)
    side = "".join(f'<li><a href="#{slug(n)}">{inline(n)}</a></li>' for n in names)
    return f"""<div class="layout">
<aside class="side"><nav aria-label="Sections"><p class="label">On this page</p><ol>{side}</ol></nav></aside>
<main>
  <header class="top">
    <span class="label">Findings · {_esc(dated)}</span>
    <h1>{inline(title_line[2:])}</h1>
    <div class="lede">{render(tree(blocks(parts[0])), figures)}</div>
    <nav class="toc" aria-label="Sections">{chips}</nav>
  </header>
{sections}
</main>
</div>
<div class="tip" role="tooltip" hidden></div>
"""


def document(body: str, styles: list[str], script: str) -> str:
    """The file to publish: its title and styles at the top, the body, then the script."""
    return (
        f'<title>{TITLE}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
        f"<style>\n{chr(10).join(styles)}\n</style>\n{body}<script>\n{script}</script>\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="./lab page", description=__doc__.split("\n\n")[0] if __doc__ else None
    )
    parser.add_argument("--date", default="6 November 2026", help="the date in the page's header")
    parser.add_argument("-o", "--out", type=Path, default=OUT)
    ns = parser.parse_args(argv)
    figures = {p.name.removesuffix(".svg.html"): p.read_text() for p in _ASSETS.glob("*.svg.html")}
    styles = [(_ASSETS / name).read_text() for name in ("bh01-tokens.css", "base.css", "findings.css")]
    body = page(SOURCE.read_text(), figures, ns.date)
    ns.out.write_text(document(body, styles, (_ASSETS / "findings.js").read_text()))
    print(f"{ns.out} ({ns.out.stat().st_size:,} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
