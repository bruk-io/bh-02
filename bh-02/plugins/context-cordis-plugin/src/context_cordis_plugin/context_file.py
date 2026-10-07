"""The project context: the sections the context files list, each some files and the function
that says what they mean to the model.

A context file is TOML: `[[section]]`s, each `files` (patterns: from the project's root, `**/`
for any depth; `~/...` and `/...` are paths of their own) and `function` (a full module path,
`package.module:function`, called `function(files, root=, home=)` with the files that match and
returning text). A section may also have `on_touch` (another, called `on_touch(files, touched,
root=, home=)` with those files and the ones an input just opened, returning, for each of its
files that bears on those, the text to tell with that input's result), or only that. bh-02's
own (`context.toml`, beside this module) is read first, then each of `ContextConfig.files`: the
person's (`$XDG_CONFIG_HOME/bh-02/context.toml`, else `~/.config/bh-02/context.toml`:
`_located`), then the project's (`.bh-02/context.toml`). Each appends its sections, or starts
the list afresh with `replace = true` at its top. A file is read again when it changes, so a
section added reaches the model's next message; so is a file a section's patterns match, added,
moved or removed (`_Search`: a search keeps the time each directory it looked in last changed,
and looks again when one of them has).

A file inside the project is the model's to write, wherever its name came from (the person's
too, when `$XDG_CONFIG_HOME` or their home is in the project), and bh-02 reads what it names in
its own process, outside the jail. So it may name only bh-02's own functions
(`context_cordis_plugin.sections`, as `function` and as `on_touch`), only files in the project
that are not hidden (no `~`, `/`, `..` or part starting with `.`), and may not `replace` the
sections before it. And whatever file a section names, bh-02 reads nothing through it that the
model could not read itself (`_kept`): a file reached from the project stays in it, none is
read under a secret's name (`local.env`, `.env`, `*.env`), a symlink in the project (where the
model can make one) counts only when it points at another file the section found, and a hard
link in the project is not read. Whether a context file is the project's is whether the model
could have written it, as named or as it resolves (`_writable`): a link in the project to a file
outside it is still the project's.
"""

import importlib
import os
import re
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

__all__ = ["ContextFiles", "Section", "parse"]

_OWN = "context_cordis_plugin.sections:"  # the functions a file inside the project may name
_CONFIG_HOME = "$XDG_CONFIG_HOME/"  # a context file in the person's config directory
_SHIPPED = Path(__file__).with_name("context.toml")
_MAGIC = re.compile(r"[*?\[]")
# Directories a search does not go into, unless its pattern names them: hidden ones, and what
# tools make, fetch or keep.
_SECRET = re.compile(r"^\.env(\..*)?$|\.env$")  # local.env, .env, .env.local, prod.env: never read
_SKIPPED = frozenset({"node_modules", "__pycache__", "venv", "build", "dist", "target", "vendor"})
_LOOKED = 20_000  # directories one search looks in at most, so a project as big as a home ends

type Function = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class Section:
    """One `[[section]]`: its file patterns, its function ('' for none), the context file it
    came from, whether that file is the person's (or bh-02's) rather than the project's, and
    its `on_touch` function ('' for none)."""

    files: tuple[str, ...]
    function: str
    source: str
    trusted: bool = True
    on_touch: str = ""


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
    if not trusted and read.get("replace", False):
        raise ValueError(
            f"{source} is the project's, which the model can write, so it may only add sections, "
            "not `replace` yours"
        )
    sections: list[Section] = []
    for table in read.get("section", []):
        files = table.get("files", []) if isinstance(table, dict) else None
        files = [files] if isinstance(files, str) else files
        function = table.get("function", "") if isinstance(table, dict) else None
        on_touch = table.get("on_touch", "") if isinstance(table, dict) else None
        named = [n for n in (function, on_touch) if n]
        if (
            not isinstance(files, list)
            or not all(isinstance(f, str) and f for f in files)
            or not isinstance(function, str)
            or not isinstance(on_touch, str)
            or not named
            or not all(":" in n for n in named)
            or set(table) - {"files", "function", "on_touch"}
        ):
            raise ValueError(
                f"a [[section]] in {source} is `files` (patterns from the project's root) and "
                '`function` (a module path, "package.module:function"), as in '
                '{ files = ["AGENTS.md"], function = "context_cordis_plugin.sections:place" }, '
                "and may have `on_touch` (another, for what to tell when an input opens a file); "
                f"got {table!r}"
            )
        outside = [
            f for f in files if f.startswith(("~", "/")) or any(p.startswith(".") for p in PurePath(f).parts)
        ]
        if not trusted and outside:
            raise ValueError(
                f"{source} is the project's, which the model can write, so it may name only files "
                f"in the project that are not hidden (no ~, /, .. or part starting with .), not "
                f"{', '.join(outside)}"
            )
        if not trusted and (other := next((n for n in named if not n.startswith(_OWN)), None)):
            raise ValueError(
                f"{source} is the project's, which the model can write, so it may name only "
                f"bh-02's own functions ({_OWN}place, rules, whole, named, ...), not {other}: a "
                "function of yours goes in your own context file, $XDG_CONFIG_HOME/bh-02/context.toml "
                "(else ~/.config/bh-02/context.toml)"
            )
        sections.append(Section(tuple(files), function, source, trusted, on_touch))
    return tuple(sections), bool(read.get("replace", False))


class ContextFiles:
    """The project context, made each time the prompt is read: the sections (bh-02's, then
    each of `files`, each read again when it changes), each section's files (a pattern with no
    wildcard looked for each time; one with a wildcard searched for again when a directory the
    last search looked in has changed since, a file in it added, moved or removed), and each
    section's function given them. A file that can't be read,
    or a function that fails, says so in one line, and the rest still say theirs."""

    def __init__(self, files: Sequence[str], max_chars: int) -> None:
        self._files = files
        self._max_chars = max_chars
        # The caches take no lock. One `ContextFiles` (the `system` value's) serves the prompt
        # (`text`) and the on-touch row (`touched`), and it is used by one thread at a time:
        # `agent:loop` reads the prompt and asks `memory` each in a thread of its own, one at a
        # time: a call a stopped reply left running finishes before the next begins. The one
        # overlap is such a call beside the first of a loop that reloaded meanwhile (`/model`,
        # `/clear`); each change here is a single dict operation, so the worst it costs is a file
        # read or a search done twice.
        self._read: dict[Path, tuple[int, tuple[tuple[Section, ...], bool] | str]] = {}
        self._searched: dict[tuple[Path, str], _Search] = {}

    def text(self, root: Path, home: Path) -> str:
        sections, parts = self._sections(root, home)
        for section in sections:
            if not section.function:
                continue
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

    def touched(self, touched: Sequence[Path], root: Path, home: Path) -> list[tuple[str, str]]:
        """What the sections with an `on_touch` say about the files an input opened (`touched`,
        absolute): each (file, text) its function returned, in the order of the sections. One
        that fails says so in one line, under its own name. A context file that can't be read is
        the prompt's to say, not this."""
        said: list[tuple[str, str]] = []
        for section in self._sections(root, home)[0]:
            if not section.on_touch:
                continue
            try:
                found = _function(section.on_touch)(
                    list(self._found(section, root, home)), list(touched), root=root, home=home
                )
                if not isinstance(found, Mapping):
                    raise TypeError(f"it returned a {type(found).__name__}, not a mapping of file to text")
                said += [(str(path), str(text).strip()) for path, text in found.items() if str(text).strip()]
            except Exception as error:  # one section failing must not take the others with it
                said.append(
                    (section.on_touch, f"(bh-02 could not make the section {section.on_touch}: {error})")
                )
        return said

    def _sections(self, root: Path, home: Path) -> tuple[list[Section], list[str]]:
        sections: list[Section] = []
        problems: list[str] = []
        for name in (str(_SHIPPED), *self._files):
            path = _located(name, root, home, os.environ)
            stamp = path.stat().st_mtime_ns if path.is_file() else 0
            if self._read.get(path, (None,))[0] != stamp:
                self._read[path] = (
                    stamp,
                    _parsed(
                        path,
                        trusted=path == _SHIPPED
                        or not _writable((path, path.resolve()), (root, root.resolve())),
                    )
                    if stamp
                    else ((), False),
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
        found: dict[Path, bool] = {}  # each file, and whether it was reached from the project
        for pattern in section.files:
            if pattern.startswith(("~", "/")):
                path = Path(str(home) + pattern[1:]) if pattern.startswith("~") else Path(pattern)
                matches: Sequence[Path] = [path] if path.is_file() else []
            elif not _MAGIC.search(pattern):
                matches = [root / pattern] if (root / pattern).is_file() else []
            else:
                searched = self._searched.get((root, pattern))
                if searched is None or not _unchanged(searched):
                    searched = self._searched[(root, pattern)] = _search(root, pattern)
                matches = searched.found
            for path in matches:
                found.setdefault(path, not pattern.startswith(("~", "/")))
        resolved = {
            path: (path.parent.resolve() / path.name, path.resolve(), path.stat().st_nlink) for path in found
        }
        return _kept(tuple(found.items()), resolved, root.resolve(), trusted=section.trusted)


def _located(name: str, root: Path, home: Path, environ: Mapping[str, str]) -> Path:
    """Where the context file `name` is: one starting `$XDG_CONFIG_HOME/` in the person's config
    directory (that variable's value, else `home`'s `.config`, as the models file is), one
    starting `~` in `home`, and any other from the project's root (an absolute one is itself).
    Whom it is trusted as is not this: that is whether the model could write it (`_writable`)."""
    if name.startswith(_CONFIG_HOME):
        return Path(environ.get("XDG_CONFIG_HOME") or home / ".config") / name.removeprefix(_CONFIG_HOME)
    return Path(str(home) + name[1:]) if name.startswith("~") else root / name


def _writable(path: tuple[Path, Path], root: tuple[Path, Path]) -> bool:
    """Whether the model could have written a context file: its path as named or as it resolves
    (`path`) is in the project, as named or as it resolves (`root`). Both, because a link in the
    project (`.bh-02/context.toml`, or `.bh-02` itself) may lead to a file the model wrote outside
    it, in the jail's own scratch directory, and a file of the person's may be a link into it."""
    return any(p.is_relative_to(r) for p in path for r in root)


def _kept(
    found: Sequence[tuple[Path, bool]],
    resolved: Mapping[Path, tuple[Path, Path, int]],
    root: Path,
    *,
    trusted: bool,
) -> tuple[Path, ...]:
    """What of a section's files it may read, in order: never more than the model itself could.
    `found`: each file, and whether it was reached from the project (a relative pattern);
    `resolved`: each file's place (its directories' links followed), what it finally is (its own
    link followed too) and how many names it has. One reached from the project must be in it; a
    link in the project, which the model could have made, must lead to another file the section
    found (a CLAUDE.md linking to the AGENTS.md beside it stays), while one of the person's own,
    outside it, is theirs to follow; a file in the project with a second name (a hard link) is
    not read, since that name may be one the model gave a file the jail hides; none named like a
    secret is read; and, for the project's own file, none hidden."""
    places = {place for place, _, _ in resolved.values()}
    kept: list[Path] = []
    for path, from_project in found:
        place, real, names = resolved[path]
        inside = place.is_relative_to(root)
        if from_project and not inside:
            continue
        if inside and (names > 1 or (real != place and real not in places)):
            continue
        if _SECRET.search(place.name) or _SECRET.search(real.name):
            continue
        if not trusted and any(part.startswith(".") for part in place.relative_to(root).parts):
            continue
        kept.append(path)
    return tuple(kept)


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


@dataclass(frozen=True, slots=True)
class _Search:
    """What one search found, and each directory it looked in with the time that directory
    last changed then: a file added, moved or removed in one changes it."""

    found: tuple[Path, ...]
    looked: tuple[tuple[Path, int], ...]


def _unchanged(searched: _Search) -> bool:
    """Whether every directory a search looked in is as it was: one `stat` each, no walk."""
    try:
        return all(where.stat().st_mtime_ns == when for where, when in searched.looked)
    except OSError:  # one is gone
        return False


def _search(root: Path, pattern: str) -> _Search:
    """The files under `root` matching `pattern`, sorted, and the directories looked in. The
    pattern's leading parts with no wildcard are walked into whatever they are (`.claude/rules`);
    below them, hidden directories and those tools fill are skipped, and at most `_LOOKED`
    directories are looked in. Each directory's time is taken before it is listed, so a change
    made while it is read still shows as one. When those leading parts are not there yet, the
    nearest directory above them that is stands in, so their appearing shows too."""
    parts = PurePath(pattern).parts
    lead = next((n for n, part in enumerate(parts) if _MAGIC.search(part)), len(parts))
    base = root.joinpath(*parts[:lead])
    if not base.is_dir():
        near = next((p for p in (base, *base.parents) if p.is_dir() and p.is_relative_to(root)), None)
        return _Search((), ((near, near.stat().st_mtime_ns),) if near else ())
    found: list[Path] = []
    looked: list[tuple[Path, int]] = []
    todo = [base]
    while todo and len(looked) < _LOOKED:
        here = todo.pop()
        try:
            when = here.stat().st_mtime_ns
            entries = list(os.scandir(here))
        except OSError:
            continue
        looked.append((here, when))
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                if not entry.name.startswith(".") and entry.name not in _SKIPPED:
                    todo.append(Path(entry.path))
            elif entry.is_file() and (path := Path(entry.path)).relative_to(root).full_match(pattern):
                found.append(path)
    return _Search(tuple(sorted(found)), tuple(looked))
