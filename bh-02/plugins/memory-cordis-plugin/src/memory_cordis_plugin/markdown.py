"""What Claude Code reads in a memory file before it tells it: block-level HTML comments taken
out (`uncommented`), and the files it imports with `@path` (`imports`). Both pure.

An import is `@` then a path, at a line's start or after whitespace (so `name@example.com` is
none): relative to the file it is in, absolute, or from the home (`@~/...`). A space in the path
is written `\\ `; a path in quotes is not imported. Fenced code blocks and code spans are skipped,
so `` `@README` `` stays text. A block-level comment is one that starts a line and ends one
(`<!-- maintainer notes -->`, on one line or several); one inside a code block, or with text
after it on its line, stays.
"""

import re

__all__ = ["imports", "uncommented", "without_trailing"]

_TOKEN = re.compile(r"(?<![^\s(\[])@((?:\\ |\S)+)")
_SPAN = re.compile(r"(`+)(.+?)\1")
_FENCE = re.compile(r"^(`{3,}|~{3,})")
_TRAILING = ".,;:!?)]"  # punctuation a sentence puts after an import, tried without when needed


def imports(text: str) -> list[str]:
    """The paths `text` imports, in order, each as written (a `\\ ` read as a space): outside
    code blocks and code spans, never one in quotes. A path may end in punctuation the sentence
    put there (`see @README.`); whoever resolves it tries it without too (`_TRAILING`)."""
    found: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        fence, code = _fenced(line.strip(), fence)
        if code:
            continue
        for match in _TOKEN.finditer(_SPAN.sub(lambda m: " " * len(m.group(0)), line)):
            path = match.group(1)
            if not path.startswith(("'", '"')):
                found.append(path.replace("\\ ", " "))
    return found


def uncommented(text: str) -> str:
    """`text` with its block-level HTML comments taken out: one that starts a line (after
    whitespace) and ends one, on one line or across several; not one in a code block, nor one
    with more text after it on its line."""
    out: list[str] = []
    fence: str | None = None
    inside = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if inside:
            inside = not stripped.endswith("-->")
            continue
        fence, code = _fenced(stripped, fence)
        if not code and stripped.startswith("<!--"):
            if stripped.endswith("-->") and len(stripped) >= len("<!---->"):
                continue
            if "-->" not in stripped:
                inside = True
                continue
        out.append(line)
    return "".join(out)


def without_trailing(path: str) -> str:
    """`path` without the punctuation a sentence may have put after it (`_TRAILING`)."""
    return path.rstrip(_TRAILING)


def _fenced(stripped: str, fence: str | None) -> tuple[str | None, bool]:
    """The fence a line leaves open (None outside a code block), and whether the line is code:
    in a block, or a fence that opens or closes one."""
    opening = _FENCE.match(stripped)
    if fence is None:
        return (opening.group(1), True) if opening else (None, False)
    if (
        opening
        and opening.group(1)[0] == fence[0]
        and len(opening.group(1)) >= len(fence)
        and stripped == opening.group(1)
    ):
        return None, True
    return fence, True
