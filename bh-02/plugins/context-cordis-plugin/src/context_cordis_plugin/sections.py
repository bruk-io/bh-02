"""bh-02's own section functions: what a context file's `[[section]]` can name to say what its
files mean to the model.

Each is `function(files, *, root, home) -> str`: the files the section's patterns matched (in
the order of its patterns, each once), the project's root, the person's home, and the text the
model is told ('' for nothing). One runs each time the prompt is read, so it reads its files then.

- `place`: guidance files (AGENTS.md, CLAUDE.md, ...), each of which applies to everything under
  the directory it sits in: those at the project's root or outside the project (the person's
  own, in their home) whole, broadest first, each once; those further down named, for the model
  to read before it works there.
- `rules`: rule files, as each one's frontmatter says (`rule`).
- `whole`: each file, whole.
- `named`: each file by name, for the model to read when it bears on its work.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Rule", "frontmatter", "named", "place", "rule", "rules", "whole"]

_LISTED = 30  # files named, the rest counted
_FRONT = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
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
    read: dict[str, str] = {}
    for path in covering:
        text = _text(path)
        if text.strip() and text not in read.values():
            read[_where(path, root, home)] = text
    parts: list[str] = []
    if read:
        parts.append(_GUIDANCE)
        for where, text in read.items():
            parts += [f"From {where}:", text.strip()]
    if below:
        parts.append(
            f"Some directories have guidance of their own: {_named([_where(f, root, home) for f in below])}. "
            "Before you work in one of them, read its file; where it disagrees with the guidance "
            "above, it wins there."
        )
    return "\n\n".join(parts)


def rules(files: Sequence[Path], *, root: Path, home: Path) -> str:
    """Rule files, as each one's frontmatter says (`rule`): one that always applies whole; one
    for some files named with them, one for some kinds of work with its description, for the
    model to read when they bear on its work; a manual one not at all (it is the person's to
    bring in)."""
    each = [rule(_where(p, root, home), _text(p)) for p in files]
    parts = [part for r in each if r.applies == "always" and r.text for part in (f"From {r.path}:", r.text)]
    pathed = [f"{r.path} (for {', '.join(r.paths)})" for r in each if r.applies == "paths"]
    if pathed:
        parts.append(
            f"Rules for some files; read one before you work on files it is for: {_named(pathed, '; ')}."
        )
    asked = [f"{r.path} ({r.description})" for r in each if r.applies == "asked"]
    if asked:
        parts.append(f"Rules to read when what they are for bears on your work: {_named(asked, '; ')}.")
    return "\n\n".join(parts)


def whole(files: Sequence[Path], *, root: Path, home: Path) -> str:
    """Each file, whole, as it is."""
    texts = [(_where(p, root, home), _text(p)) for p in files]
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
    (`[a, b]`, or `- a` lines under it), and the text after it. A small, forgiving reading of
    YAML: what rule files use, nothing more."""
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
            said[key] = [_bare(v) for v in value[1:-1].split(",") if v.strip()]
        else:
            said[key] = _bare(value)
    return said, text[found.end() :]


def rule(path: str, text: str) -> Rule:
    """A rule file, read by its frontmatter: `alwaysApply: true`, or no frontmatter at all,
    always; `paths` or `globs` (a list, or one string of comma-separated patterns) for matching
    files; a `description`, when what it describes bears on the work; `alwaysApply: false` and
    nothing else, only when the person brings it in."""
    said, body = frontmatter(text)
    paths = said.get("paths") or said.get("globs") or []
    if isinstance(paths, str):
        paths = [p.strip() for p in paths.split(",") if p.strip()]
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


def _bare(value: str) -> str:
    return value.strip().strip("\"'")


def _named(items: Sequence[str], sep: str = ", ") -> str:
    more = f"{sep}and {len(items) - _LISTED} more" if len(items) > _LISTED else ""
    return sep.join(items[:_LISTED]) + more


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _where(path: Path, root: Path, home: Path) -> str:
    """How a file is named to the model: from the project's root inside it, from `~` inside the
    home, whole otherwise."""
    if path.is_relative_to(root):
        return str(path.relative_to(root))
    if path.is_relative_to(home):
        return "~/" + str(path.relative_to(home))
    return str(path)
