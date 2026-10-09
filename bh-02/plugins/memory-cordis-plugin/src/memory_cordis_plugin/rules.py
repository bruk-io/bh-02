"""Rule files, as Claude Code reads `.claude/rules/`: a Markdown file whose YAML frontmatter may
name `paths`, the files it is for. One without `paths` applies everywhere and is told at the
start; one with them is told when an input first opens a file they match (`matches`): a
pattern from the project's root (`src/api/**/*.ts`), with no `/` at any depth (`*.tsx`), each
`{a,b}` group one of its alternatives (`src/**/*.{ts,tsx}`), as Claude Code writes them.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import islice
from pathlib import PurePath

__all__ = ["Rule", "frontmatter", "matches", "rule"]

_FRONT = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
_BRACE = re.compile(r"\{([^{}]*)\}")  # a `{a,b}` group with none inside it: expanded first
_ALTERNATIVES = 1_000  # a pattern's alternatives tried at most, so no rule file's braces take long


@dataclass(frozen=True, slots=True)
class Rule:
    """One rule file: the files it is for (`paths`; none: everywhere), and its text without the
    frontmatter."""

    paths: tuple[str, ...] = ()
    text: str = ""


def rule(text: str) -> Rule:
    """A rule file, read by its frontmatter: `paths`, a list of patterns or one string of them
    separated by commas (split only at the commas outside braces), the files it is for."""
    said, body = frontmatter(text)
    paths = said.get("paths") or []
    if isinstance(paths, str):
        paths = _split(paths)
    return Rule(tuple(paths), body.strip())


def frontmatter(text: str) -> tuple[dict[str, str | list[str]], str]:
    """A file's frontmatter (between `---` lines at its start), each key to its value or list
    (`[a, b]`, split at the commas outside braces, or `- a` lines under it), and the text after
    it. A small, forgiving reading of YAML: what rule files use, nothing more."""
    found = _FRONT.match(text)
    if found is None:
        return {}, text
    said: dict[str, str | list[str]] = {}
    key: str | None = None
    for line in found.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and key is not None:
            listed = said.get(key)
            said[key] = [*(listed if isinstance(listed, list) else []), _bare(stripped[2:])]
            continue
        name, colon, value = line.partition(":")
        if not colon or line[:1].isspace():
            continue
        key, value = name.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            said[key] = [_bare(v) for v in _split(value[1:-1])]
        else:
            said[key] = _bare(value)
    return said, text[found.end() :]


def matches(path: PurePath, pattern: str) -> bool:
    """Whether a path from the project's root matches a rule's pattern: any of its alternatives
    (`_alternatives`), each from the root, or, with no `/` (`*.tsx`), at any depth."""
    for each in islice(_alternatives(pattern.strip()), _ALTERNATIVES):
        alternative = each.removeprefix("./").lstrip("/")
        if alternative and (
            path.full_match(alternative) or ("/" not in alternative and path.full_match(f"**/{alternative}"))
        ):
            return True
    return False


def _split(patterns: str) -> list[str]:
    """Comma-separated patterns, split at the commas outside braces, each stripped:
    `src/**/*.{ts,tsx}, lib/*` is two patterns, the first with its `{ts,tsx}` whole."""
    parts: list[str] = []
    depth, start = 0, 0
    for at, char in enumerate(patterns):
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(depth - 1, 0)
        elif char == "," and not depth:
            parts.append(patterns[start:at])
            start = at + 1
    return [part.strip() for part in [*parts, patterns[start:]] if part.strip()]


def _alternatives(pattern: str) -> Iterator[str]:
    """`pattern` with each `{a,b}` group one of its alternatives, as in Claude Code's `paths` and
    a shell (`PurePath.full_match` has no braces): `src/*.{ts,tsx}` is `src/*.ts`, then
    `src/*.tsx`; several groups give each combination, in order, and a group inside another is
    expanded first. Lazily, so the first that matches ends the search."""
    todo = [pattern]
    while todo:
        here = todo.pop()
        group = _BRACE.search(here)
        if group is None:
            yield here
            continue
        head, tail = here[: group.start()], here[group.end() :]
        todo += [head + alternative + tail for alternative in reversed(group.group(1).split(","))]


def _bare(value: str) -> str:
    return value.strip().strip("\"'")
