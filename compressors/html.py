"""HTML: keep the text a reader would see, as light markdown.

Drops scripts, styles, SVG, templates and the like, and the page chrome (nav, footer, aside).
Headings become `#` lines, list items `- `, table cells ` | `, and a link keeps its href when the
href is short and differs from the text. Whether dropping the chrome loses needles is one of the
things the lab measures.
"""

import re
from html.parser import HTMLParser

from compressors.common import split_lines

_SKIP = frozenset(
    {"script", "style", "svg", "noscript", "template", "iframe", "canvas", "nav", "footer", "aside"}
)
_VOID = frozenset(
    {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "wbr"}
)
_BLOCK = frozenset(
    {"p", "div", "section", "article", "main", "header", "table", "tr", "ul", "ol", "pre", "blockquote"}
    | {"form", "dl", "dt", "dd", "figure", "figcaption", "br", "hr", "title", "body", "html"}
)
_HEADINGS = {f"h{i}": "#" * i for i in range(1, 7)}


class _TextExtractor(HTMLParser):
    """HTMLParser's own extension point is subclassing; the state lives only for one feed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_tag: str | None = None  # inside this element, everything is dropped
        self._skip_nest = 0
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_tag is not None:
            self._skip_nest += tag == self._skip_tag
            return
        if tag in _SKIP:
            self._skip_tag, self._skip_nest = tag, 1
            return
        if tag in _VOID:
            if tag in ("br", "hr"):
                self.parts.append("\n")
            return
        if tag in _HEADINGS:
            self.parts.append(f"\n\n{_HEADINGS[tag]} ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_tag is not None:
            if tag == self._skip_tag:
                self._skip_nest -= 1
                if not self._skip_nest:
                    self._skip_tag = None
            return
        if tag in _VOID:
            return
        if tag == "a" and self._href is not None:
            text = "".join(self._link_text).strip()
            href = self._href
            if href and len(href) < 100 and href != text and not href.startswith(("#", "javascript:")):
                self.parts.append(f" ({href})")
            self._href = None
        elif tag in _HEADINGS or tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_tag is not None:
            return
        if self._href is not None:
            self._link_text.append(data)
        self.parts.append(data)


def looks_like_html(raw: str) -> bool:
    head = raw.lstrip()[:2000].lower()
    if head.startswith(("<!doctype html", "<html")) or "<html" in head or "<body" in head:
        return True
    return len(re.findall(r"</?(?:div|span|p|a|li|td|script|meta)\b", raw[:20000], re.IGNORECASE)) >= 20


def html_to_text(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    parser.close()
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in split_lines("".join(parser.parts))]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()
