"""The project context: the sections the context files list, each some files and the function
that says what they mean to the model.

A context file is TOML: `[[section]]`s, each `files` (patterns: from the project's root, `**/`
for any depth; `~/...` and `/...` are paths of their own) and `function` (a full module path,
`package.module:function`, called `function(files, root=, home=)` with the files that match and
returning text). bh-02's own (`context.toml`, beside this module) is read first, then each of
`ContextConfig.files`: the person's (`~/.config/bh-02/context.toml`), then the project's
(`.bh-02/context.toml`). Each appends its sections, or starts the list afresh with
`replace = true` at its top. A file is read again when it changes, so a section added reaches
the model's next message.

A file inside the project may name only bh-02's own functions (`context_cordis_plugin.sections`):
the model can write there, and a function it named would run in bh-02, outside the jail.
"""

import importlib
import os
import re
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

__all__ = ["ContextFiles", "Section", "parse"]

_OWN = "context_cordis_plugin.sections:"  # the functions a file inside the project may name
_SHIPPED = Path(__file__).with_name("context.toml")
_MAGIC = re.compile(r"[*?\[]")
# Directories a search does not go into, unless its pattern names them: hidden ones, and what
# tools make, fetch or keep.
_SKIPPED = frozenset({"node_modules", "__pycache__", "venv", "build", "dist", "target", "vendor"})
_LOOKED = 20_000  # directories one search looks in at most, so a project as big as a home ends

type Function = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class Section:
    """One `[[section]]`: its file patterns, its function, and the context file it came from."""

    files: tuple[str, ...]
    function: str
    source: str


def parse(text: str, source: str, *, trusted: bool) -> tuple[tuple[Section, ...], bool]:
    """A context file's sections, and whether it starts the list afresh (`replace = true`).
    `trusted`: whether it may name any function, not only bh-02's own. Raises ValueError saying
    what is wrong and what a section looks like."""
    try:
        read = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{source} is not TOML: {error}") from None
    if set(read) - {"section", "replace"} or not isinstance(read.get("replace", False), bool):
        raise ValueError(f"{source} may hold only [[section]]s and `replace = true`; it has {sorted(read)}")
    sections: list[Section] = []
    for table in read.get("section", []):
        files = table.get("files", []) if isinstance(table, dict) else None
        files = [files] if isinstance(files, str) else files
        function = table.get("function") if isinstance(table, dict) else None
        if (
            not isinstance(files, list)
            or not all(isinstance(f, str) and f for f in files)
            or not isinstance(function, str)
            or ":" not in function
            or set(table) - {"files", "function"}
        ):
            raise ValueError(
                f"a [[section]] in {source} is `files` (patterns from the project's root) and "
                '`function` (a module path, "package.module:function"), as in '
                '{ files = ["AGENTS.md"], function = "context_cordis_plugin.sections:place" }; '
                f"got {table!r}"
            )
        if not trusted and not function.startswith(_OWN):
            raise ValueError(
                f"{source} is the project's, which the model can write, so it may name only "
                f"bh-02's own functions ({_OWN}place, rules, whole, named), not {function}: a "
                "function of yours goes in your ~/.config/bh-02/context.toml"
            )
        sections.append(Section(tuple(files), function, source))
    return tuple(sections), bool(read.get("replace", False))


class ContextFiles:
    """The project context, made each time the prompt is read: the sections (bh-02's, then
    each of `files`, each read again when it changes), each section's files (a pattern with no
    wildcard looked for each time; one with a wildcard searched for once, and again when a
    context file changes), and each section's function given them. A file that can't be read,
    or a function that fails, says so in one line, and the rest still say theirs."""

    def __init__(self, files: Sequence[str], max_chars: int) -> None:
        self._files = files
        self._max_chars = max_chars
        self._read: dict[Path, tuple[int, tuple[tuple[Section, ...], bool] | str]] = {}
        self._searched: dict[tuple[Path, str], tuple[Path, ...]] = {}

    def text(self, root: Path, home: Path) -> str:
        sections, parts = self._sections(root, home)
        for section in sections:
            try:
                said = _function(section.function)(
                    list(self._found(section, root, home)), root=root, home=home
                )
                if not isinstance(said, str):
                    raise TypeError(f"it returned a {type(said).__name__}, not text")
            except Exception as error:  # one section failing must not take the prompt with it
                said = f"(bh-02 could not make the section {section.function}: {error})"
            if said.strip():
                parts.append(said.strip())
        text = "\n\n".join(parts)
        cap = self._max_chars
        return (
            text
            if len(text) <= cap
            else f"{text[:cap]}\n... [{len(text) - cap} more chars of project context]"
        )

    def _sections(self, root: Path, home: Path) -> tuple[list[Section], list[str]]:
        sections: list[Section] = []
        problems: list[str] = []
        for name in (str(_SHIPPED), *self._files):
            path = Path(str(home) + name[1:]) if name.startswith("~") else root / name
            stamp = path.stat().st_mtime_ns if path.is_file() else 0
            if self._read.get(path, (None,))[0] != stamp:
                self._read[path] = (
                    stamp,
                    _parsed(path, trusted=not path.is_relative_to(root)) if stamp else ((), False),
                )
                self._searched.clear()  # the sections may have changed: search afresh
            read = self._read[path][1]
            if isinstance(read, str):
                problems.append(read)
                continue
            added, replace = read
            sections = [*([] if replace else sections), *added]
        return sections, problems

    def _found(self, section: Section, root: Path, home: Path) -> tuple[Path, ...]:
        found: dict[Path, None] = {}
        for pattern in section.files:
            if pattern.startswith(("~", "/")):
                path = Path(str(home) + pattern[1:]) if pattern.startswith("~") else Path(pattern)
                matches: Sequence[Path] = [path] if path.is_file() else []
            elif not _MAGIC.search(pattern):
                matches = [root / pattern] if (root / pattern).is_file() else []
            else:
                if (root, pattern) not in self._searched:
                    self._searched[(root, pattern)] = _search(root, pattern)
                matches = self._searched[(root, pattern)]
            for path in matches:
                found.setdefault(path, None)
        return tuple(found)


def _parsed(path: Path, *, trusted: bool) -> tuple[tuple[Section, ...], bool] | str:
    try:
        return parse(path.read_text(encoding="utf-8"), str(path), trusted=trusted)
    except (OSError, ValueError) as error:
        return f"(bh-02 could not read the context file {path}: {error})"


def _function(name: str) -> Function:
    module, _, attribute = name.partition(":")
    function = getattr(importlib.import_module(module), attribute)
    if not callable(function):
        raise TypeError(f"{name} is not a function")
    return function  # type: ignore[no-any-return]


def _search(root: Path, pattern: str) -> tuple[Path, ...]:
    """The files under `root` matching `pattern`, sorted. The pattern's leading parts with no
    wildcard are walked into whatever they are (`.claude/rules`); below them, hidden directories
    and those tools fill are skipped, and at most `_LOOKED` directories are looked in."""
    parts = PurePath(pattern).parts
    lead = next((n for n, part in enumerate(parts) if _MAGIC.search(part)), len(parts))
    found: list[Path] = []
    for looked, (here, dirs, files) in enumerate(os.walk(root.joinpath(*parts[:lead])), 1):
        if looked > _LOOKED:
            break
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIPPED]
        found += [p for f in files if (p := Path(here, f)).relative_to(root).full_match(pattern)]
    return tuple(sorted(found))
