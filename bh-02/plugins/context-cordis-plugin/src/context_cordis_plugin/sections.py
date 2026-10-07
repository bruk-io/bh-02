"""bh-02's own section functions: what a context file's `[[section]]` can name to say what its
files mean to the model.

Each is `function(files, *, root, home) -> str`: the files the section's patterns matched (in
the order of its patterns, each once), the project's root, the person's home, and the text the
model is told ('' for nothing). One runs each time the prompt is read, so it reads its files then,
each through `context_file.read`: a file in the project from its root through no link but one to
another of its files, so a link the model made after they were found is not followed.

- `place`: guidance files (AGENTS.md, CLAUDE.md, ...), each of which applies to everything under
  the directory it sits in: those at the project's root or outside the project (the person's
  own, in their home) whole, broadest first, each once; those further down named, for the model
  to read before it works there.
- `rules`: rule files, as each one's frontmatter says (`rule`).
- `whole`: each file, whole.
- `named`: each file by name, for the model to read when it bears on its work.

And two for a section's `on_touch`, each `on_touch(files, touched, *, root, home)` with the
files an input just opened (absolute), returning, for each of its files that bears on them, the
text to tell with that input's result (the row tells each once a conversation):

- `place_touched`: the guidance further down that covers a file opened (one under its directory).
- `rules_touched`: the rules whose `paths` (or `globs`) match a file opened; a pattern's
  `{a,b}` groups are its alternatives, as in Claude Code's `paths` (`src/**/*.{ts,tsx}`).
"""

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import islice
from pathlib import Path, PurePath

from context_cordis_plugin.context_file import read

__all__ = [
    "Rule",
    "frontmatter",
    "named",
    "place",
    "place_touched",
    "rule",
    "rules",
    "rules_touched",
    "whole",
]

_LISTED = 30  # files named, the rest counted
_FRONT = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
_BRACE = re.compile(r"\{([^{}]*)\}")  # a `{a,b}` group with none inside it: expanded first
_ALTERNATIVES = 1_000  # a pattern's alternatives tried at most, so no rule file's braces take long
_GUIDANCE = (
    "Guidance written for whichever agent works here, the person's own and the project's, "
    "broadest first: where it names Claude Code or another agent it means you, and where it "
    "names that agent's tools, do the same in Python. Where two disagree, the later one wins."
)


def place(files: Sequence[Path], *, root: Path, home: Path) -> str:
    """Guidance files, by where they are: whole when they apply to all of the project (at its
    root, or outside it), broadest first and each once (a CLAUDE.md that links to the AGENTS.md
    beside it is read once); named when they apply to part of it (further down)."""
    below = [f for f in files if f.is_relative_to(root) and f.parent != root]
    covering = sorted((f for f in files if f not in below), key=lambda f: f.is_relative_to(root))
    given: dict[str, str] = {}
    for path in covering:
        text = read(path, files, root)
        if text.strip() and text not in given.values():
            given[_where(path, root, home)] = text
    parts: list[str] = []
    if given:
        parts.append(_GUIDANCE)
        for where, text in given.items():
            parts += [f"From {where}:", text.strip()]
    if below:
        parts.append(
            f"Some directories have guidance of their own: {_named([_where(f, root, home) for f in below])}. "
            "Before you work in one of them, read its file if it has not been given to you yet; "
            "where it disagrees with the guidance above, it wins there."
        )
    return "\n\n".join(parts)


def place_touched(
    files: Sequence[Path], touched: Sequence[Path], *, root: Path, home: Path
) -> dict[Path, str]:
    """The guidance further down the project that covers a file an input opened (the file is
    under its directory), whole, broadest first; of two with the same text (a CLAUDE.md linking
    to the AGENTS.md beside it), one."""
    below = [f for f in files if f.is_relative_to(root) and f.parent != root]
    covering = sorted(
        (f for f in below if any(t.is_relative_to(f.parent) for t in touched)),
        key=lambda f: (len(f.parts), str(f)),
    )
    told: dict[Path, str] = {}
    seen: set[str] = set()
    for path in covering:
        text = read(path, files, root).strip()
        if text and text not in seen:
            seen.add(text)
            where = _where(path.parent, root, home)
            told[path] = (
                f"From {_where(path, root, home)}, guidance for work under {where}/, where it wins "
                f"over the guidance before it:\n\n{text}"
            )
    return told


def rules(files: Sequence[Path], *, root: Path, home: Path) -> str:
    """Rule files, as each one's frontmatter says (`rule`): one that always applies whole; one
    for some files named with them, one for some kinds of work with its description, for the
    model to read when they bear on its work; a manual one not at all (it is the person's to
    bring in)."""
    each = [rule(_where(p, root, home), read(p, files, root)) for p in files]
    parts = [part for r in each if r.applies == "always" and r.text for part in (f"From {r.path}:", r.text)]
    pathed = [f"{r.path} (for {', '.join(r.paths)})" for r in each if r.applies == "paths"]
    if pathed:
        parts.append(
            "Rules for some files; read one before you work on files it is for, if it has not been "
            f"given to you yet: {_named(pathed, '; ')}."
        )
    asked = [f"{r.path} ({r.description})" for r in each if r.applies == "asked"]
    if asked:
        parts.append(f"Rules to read when what they are for bears on your work: {_named(asked, '; ')}.")
    return "\n\n".join(parts)


def rules_touched(
    files: Sequence[Path], touched: Sequence[Path], *, root: Path, home: Path
) -> dict[Path, str]:
    """The rules for some files (`paths` or `globs`) that match a file an input opened in the
    project, each whole, with the patterns it is for (and not the file that matched, so the
    same rule reads the same whichever file brought it)."""
    opened = [t.relative_to(root) for t in touched if t.is_relative_to(root)]
    told: dict[Path, str] = {}
    for path in files:
        found = rule(_where(path, root, home), read(path, files, root))
        if found.applies != "paths" or not found.text:
            continue
        if any(_matches(t, p) for t in opened for p in found.paths):
            told[path] = f"From {found.path}, a rule for {', '.join(found.paths)}:\n\n{found.text}"
    return told


def whole(files: Sequence[Path], *, root: Path, home: Path) -> str:
    """Each file, whole, as it is."""
    texts = [(_where(p, root, home), read(p, files, root)) for p in files]
    return "\n\n".join(f"From {where}:\n\n{text.strip()}" for where, text in texts if text.strip())


def named(files: Sequence[Path], *, root: Path, home: Path) -> str:
    """Each file by name, for the model to read when it bears on its work."""
    if not files:
        return ""
    return f"Files to read when they bear on your work: {_named([_where(p, root, home) for p in files])}."


@dataclass(frozen=True, slots=True)
class Rule:
    """One rule file: where it is, when it applies (`always`, `paths`, `asked` or `manual`), the
    paths it is for (when that is how), what it says it is for, and its text without the
    frontmatter."""

    path: str
    applies: str
    paths: tuple[str, ...] = ()
    description: str = ""
    text: str = ""


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


def rule(path: str, text: str) -> Rule:
    """A rule file, read by its frontmatter: `alwaysApply: true`, or no frontmatter at all,
    always; `paths` or `globs` (a list, or one string of comma-separated patterns, split only
    at the commas outside braces: `_split`) for matching files; a `description`, when what it
    describes bears on the work; `alwaysApply: false` and nothing else, only when the person
    brings it in."""
    said, body = frontmatter(text)
    paths = said.get("paths") or said.get("globs") or []
    if isinstance(paths, str):
        paths = _split(paths)
    described = said.get("description")
    description = described if isinstance(described, str) else ""
    always = str(said.get("alwaysApply", "")).lower()
    if always == "true" or not said:
        applies = "always"
    elif paths:
        applies = "paths"
    elif description:
        applies = "asked"
    else:
        applies = "manual" if always == "false" else "always"
    return Rule(path, applies, tuple(paths), description, body.strip())


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


def _matches(path: PurePath, pattern: str) -> bool:
    """Whether a path from the project's root matches a rule's pattern: any of its alternatives
    (`_alternatives`), each from the root, or, with no `/` (`*.tsx`), at any depth."""
    for each in islice(_alternatives(pattern.strip()), _ALTERNATIVES):
        alternative = each.removeprefix("./").lstrip("/")
        if alternative and (
            path.full_match(alternative) or ("/" not in alternative and path.full_match(f"**/{alternative}"))
        ):
            return True
    return False


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


def _named(items: Sequence[str], sep: str = ", ") -> str:
    more = f"{sep}and {len(items) - _LISTED} more" if len(items) > _LISTED else ""
    return sep.join(items[:_LISTED]) + more


def _where(path: Path, root: Path, home: Path) -> str:
    """How a file is named to the model: from the project's root inside it, from `~` inside the
    home, whole otherwise."""
    if path.is_relative_to(root):
        return str(path.relative_to(root))
    if path.is_relative_to(home):
        return "~/" + str(path.relative_to(home))
    return str(path)
