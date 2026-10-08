"""The project context: the sections the context files list, each some files and the function
that says what they mean to the model.

A context file is TOML: `[[section]]`s, each `files` (patterns: from the project's root, `**/`
for any depth; `~/...` and `/...` are paths of their own) and `function` (a full module path,
`package.module:function`, called `function(files, root=, home=)` with the files that match and
returning text). A section may also have `on_touch` (another, called `on_touch(files, touched,
root=, home=)` with those files and the ones an input just opened, returning, for each of its
files that bears on those, the text to tell with that input's result), or only that. bh-02's
own (`context.toml`, beside this module) comes first, then each of `ContextConfig.files`: the
person's (`$XDG_CONFIG_HOME/bh-02/context.toml`, else `~/.config/bh-02/context.toml`:
`_located`), then the project's (`.bh-02/context.toml`). Each appends its sections, or starts
the list afresh with `replace = true` at its top. bh-02's own is read once, as the row starts:
it is trusted whole, so it is bh-02's code as its modules are, and like them it is read before
any of the model's code runs and not again (bh-02 working on its own checkout has it in the
project). Every other is read again when it changes, so a section added reaches the model's
next message; so is a file a section's patterns match, added, moved or removed (`_Search`: a
search keeps the time each directory it looked in last changed, and looks again when one of
them has).

A file inside the project is the model's to write, wherever its name came from (the person's
too, when `$XDG_CONFIG_HOME` or their home is in the project), and bh-02 reads what it names in
its own process, outside the jail. So it may name only bh-02's own functions
(`context_cordis_plugin.sections`, as `function` and as `on_touch`), only files in the project
that are not hidden (no `~`, `/`, `..` or part starting with `.`), and may not `replace` the
sections before it. Whether a context file is the project's is whether the model could have
written it or chosen what it is (`_writable`): as named, as it resolves, or through any
directory or link on its way (`cordis_helpers.walked`), it is in the project. So a link in the
project to a file outside it is the project's, and so is a file of the person's that is a link
into it (their config kept in dotfiles, and bh-02 run there): the model could repoint the link's
end.

And whatever file a section names, bh-02 reads nothing through it that the model could not read
itself. What it may read is decided when the files are found (`_kept`): a file reached from the
project stays in it, none is read under a secret's name (`local.env`, `.env`, `*.env`), a
symlink in the project (where the model can make one) counts only when it points at another
file the section found, a file in the project reached through a linked directory or with a
second name (a hard link) is not read, and one of the person's own, named outside the project,
is not read when its way passes through the project. The model can make a link at any moment,
between that check and the read, so the read is safe by itself (`read`, which bh-02's own
section functions read with): a file in the project is walked to from the project's root
through no link (`O_NOFOLLOW` on every part) and read from what that opened, only when it is a
regular file with one name, and a link there is read as its target, the same way, only when
that is another of the section's files.
"""

import importlib
import os
import re
import stat
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from cordis_helpers import MOST_LINKS, config_home, walked

__all__ = ["ContextFiles", "Section", "parse", "read"]

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
    """The project context, made each time the prompt is read: the sections (bh-02's own,
    `own`, read once as this starts; then each of `files`, each read again when it changes),
    each section's files (a pattern with no wildcard looked for each time; one with a wildcard
    searched for again when a directory the last search looked in has changed since, a file in
    it added, moved or removed), and each section's function given them. A file that can't be
    read, or a function that fails, says so in one line, and the rest still say theirs. `own` is
    the context file beside this module; a test names another."""

    def __init__(self, files: Sequence[str], max_chars: int, own: Path = _SHIPPED) -> None:
        self._files = files
        self._max_chars = max_chars
        # bh-02's own context file, read once, now. It is trusted whole (a function it names is
        # imported and run in bh-02's process), so it is bh-02's code, as its modules are, and
        # like them it is read as bh-02 starts and not again: the `system` row starts before the
        # kernel and the extensions' worker (the extensions row depends on it), so before any of
        # the model's code runs. When bh-02 works on its own checkout the file is in the project:
        # the jail denies an input writing it (`layers.code`), and should one get to, what it
        # wrote waits for bh-02, or this row, to start again, as an edit to a module does.
        self._own = _parsed(own, trusted=True) if own.is_file() else ((), False)
        # The caches take no lock. One `ContextFiles` (the `system` value's) serves the prompt
        # (`text`) and the on-touch row (`touched`), and it is used by one thread at a time:
        # `agent:loop` reads the prompt and asks `memory` each on its `executor`, one call at a
        # time, a call a stopped reply left running finished before the next begins; and the
        # `executor` row, like this one, outlives a reload of the loop (`/model`, `/clear`). Only
        # a new `executor` (its row restarted, or replaced by a layer) can start a call beside
        # one the last left running; each change here is a single dict operation, so the worst
        # that costs is a file read or a search done twice.
        # each context file read: its time and whether it was trusted then, and what it said
        self._read: dict[Path, tuple[tuple[int, bool], tuple[tuple[Section, ...], bool] | str]] = {}
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
        roots = _roots(root)
        for read in (self._own, *(self._file(name, root, home, roots) for name in self._files)):
            if isinstance(read, str):
                problems.append(read)
                continue
            added, replace = read
            sections = [*([] if replace else sections), *added]
        return sections, problems

    def _file(
        self, name: str, root: Path, home: Path, roots: Sequence[Path]
    ) -> tuple[tuple[Section, ...], bool] | str:
        """What the context file `name` (one of `files`) says now: read again when it changed, or
        when whom it is trusted as did."""
        path = _located(name, root, home, os.environ).absolute()
        stamp = path.stat().st_mtime_ns if path.is_file() else 0
        # walked each time, not only when the file changes: a link on its way may change alone
        trusted = not _writable((Path(os.path.normpath(path)), *walked(path)), roots)
        if self._read.get(path, (None,))[0] != (stamp, trusted):
            self._read[path] = (
                (stamp, trusted),
                _parsed(path, trusted=trusted) if stamp else ((), False),
            )
            self._searched.clear()  # the sections may have changed: search afresh
        return self._read[path][1]

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
        roots = _roots(root)
        facts = {
            path: _Facts(
                path.parent.resolve() / path.name,
                path.resolve(),
                path.stat().st_nlink,
                () if _under(path, roots) is not None else (path, *walked(path)),
            )
            for path in found
        }
        return _kept(tuple(found.items()), facts, roots, trusted=section.trusted)


def _located(name: str, root: Path, home: Path, environ: Mapping[str, str]) -> Path:
    """Where the context file `name` is: one starting `$XDG_CONFIG_HOME/` in the person's config
    directory (`cordis_helpers.config_home`: that variable's value, else `home`'s `.config`, as
    for the models file and the kernel's startup files), one starting `~` in `home`, and any
    other from the project's root (an absolute one is itself). Whom it is trusted as is not
    this: that is whether the model could write it (`_writable`)."""
    if name.startswith(_CONFIG_HOME):
        return config_home(environ, home) / name.removeprefix(_CONFIG_HOME)
    return Path(str(home) + name[1:]) if name.startswith("~") else root / name


def _writable(way: Sequence[Path], roots: Sequence[Path]) -> bool:
    """Whether the model could have written a file, or chosen what it is: a place on its way (the
    file as named, then `cordis_helpers.walked`'s) is in the project, as named or as it resolves
    (`roots`). A link in the project (`.bh-02/context.toml`, or `.bh-02` itself) may lead to a
    file the model wrote outside it, in the jail's own scratch directory; a file of the person's
    may be a link into it, whose end the model could repoint; and a directory on the way it
    could swap for a link. The same walk holds the models file (`in_project`) and the kernel's
    startup files."""
    return any(p.is_relative_to(r) for p in way for r in roots)


@dataclass(frozen=True, slots=True)
class _Facts:
    """What `_found` learned of one file a section found, for `_kept`: where it is (its
    directories' links followed), what it finally is (its own link followed too), how many names
    it has, and, for one named outside the project, the file and every place reading it goes
    through (`cordis_helpers.walked`)."""

    place: Path
    real: Path
    names: int
    way: tuple[Path, ...] = ()


def _kept(
    found: Sequence[tuple[Path, bool]],
    facts: Mapping[Path, _Facts],
    roots: Sequence[Path],
    *,
    trusted: bool,
) -> tuple[Path, ...]:
    """What of a section's files it may read, in order: never more than the model itself could.
    `found`: each file, and whether it was reached from the project (a relative pattern); `facts`:
    what `_found` learned of each; `roots`: the project's root as named, then as it resolves.

    One reached from the project must be in it, as named. One in it is read from the project's
    root through no link (`read`), so one reached through a linked directory is not kept; a link
    there, which the model could have made, must lead to another file the section found (a
    CLAUDE.md linking to the AGENTS.md beside it stays); and one with a second name (a hard link)
    is not read, since that name may be one the model gave a file the jail hides from it. One of
    the person's own, named outside the project, is theirs to follow, unless its way passes
    through the project (a link of theirs into it): the model could repoint what it leads to
    there. None named like a secret is read; and, for the project's own file, none hidden."""
    root = roots[-1]
    places = {fact.place for fact in facts.values()}
    kept: list[Path] = []
    for path, from_project in found:
        fact, named = facts[path], _under(path, roots)
        if named is None:
            if from_project or _writable(fact.way, roots):
                continue
        elif (
            fact.place != root / named
            or fact.names > 1
            or (fact.real != fact.place and fact.real not in places)
        ):
            continue
        if _SECRET.search(fact.place.name) or _SECRET.search(fact.real.name):
            continue
        if not trusted and (named is None or any(part.startswith(".") for part in named.parts)):
            continue
        kept.append(path)
    return tuple(kept)


def read(path: Path, files: Sequence[Path], root: Path) -> str:
    """The text of `path`, one of `files` (a section's, as its function is given them), read so
    that nothing the model changed since they were found chooses what is read. `root` is the
    project's, and every path absolute.

    One in the project is walked to from its root through no link (`O_NOFOLLOW` on every part),
    and read from what that opened only when it is a regular file with one name; a link there is
    read as its target, the same way, only when that is another of `files` (a CLAUDE.md linking
    to the AGENTS.md beside it). One outside the project (the person's own, reached through
    nothing in it: `_kept`) is read as it is named. bh-02's own section functions read every file
    with it, and a function of yours may. Raises OSError saying why a file was not read, and
    ValueError for a `path` that is not one of `files`."""
    roots = _roots(root)
    at, named = _rooted(path, roots), path
    if path not in files and at not in _all_rooted(files, roots):
        raise ValueError(
            f"{path} is not one of the files given: pass `read` one of the files a section was given"
        )
    for _ in range(MOST_LINKS):
        inside = _under(at, roots)
        if inside is None:
            return named.read_text(encoding="utf-8", errors="replace")
        text, link = _opened(roots[-1], inside.parts)
        if link is None:
            return text
        target = _rooted(at.parent / link, roots)
        if target not in _all_rooted(files, roots):
            raise OSError(
                f"{at} is a link to {link}, which is not another of the section's files, so bh-02 "
                "did not read it"
            )
        at = named = target
    raise OSError(f"{path} leads through more than {MOST_LINKS} links, so bh-02 did not read it")


def _opened(root: Path, parts: Sequence[str]) -> tuple[str, str | None]:
    """The file `parts` names under the directory `root`, walked to through no link: its text and
    None, or, when its last part is a link, '' and what that link points to. Raises OSError when a
    directory on the way is a link or not a directory, or the file is not a regular file with one
    name (a hard link; a pipe, opened without waiting for a writer)."""
    if not parts:
        raise IsADirectoryError(f"{root} is the project's root, not a file, so bh-02 did not read it")
    here = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for depth, part in enumerate(parts[:-1], start=1):
            try:
                below = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=here)
            except OSError as error:
                raise OSError(
                    f"{root.joinpath(*parts)} is reached through {root.joinpath(*parts[:depth])}, "
                    f"which is a link or not a directory ({error.strerror}), so bh-02 did not read it"
                ) from None
            os.close(here)
            here = below
        try:
            opened = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=here)
        except OSError as error:
            try:
                return "", os.readlink(parts[-1], dir_fd=here)
            except OSError:  # not a link: gone, or can't be opened
                raise error from None
    finally:
        os.close(here)
    with os.fdopen(opened, "rb") as file:
        found = os.fstat(file.fileno())
        if not stat.S_ISREG(found.st_mode) or found.st_nlink != 1:
            raise OSError(
                f"{root.joinpath(*parts)} is not a regular file with one name (it has another name, "
                "or is a pipe, a device, ...), so bh-02 did not read it"
            )
        return file.read().decode("utf-8", errors="replace"), None


def _roots(root: Path) -> tuple[Path, Path]:
    """The project's root as named (absolute, `..` taken out) and as it resolves: a path is in
    the project when it is under either."""
    return Path(os.path.normpath(root.absolute())), root.resolve()


def _under(path: Path, roots: Sequence[Path]) -> PurePath | None:
    """Where the absolute `path`, as named (`..` taken out), is from the project's root (`roots`,
    as `_roots` gives them); None when it is outside."""
    named = Path(os.path.normpath(path))
    return next((named.relative_to(r) for r in roots if named.is_relative_to(r)), None)


def _all_rooted(files: Sequence[Path], roots: Sequence[Path]) -> set[Path]:
    """Each of `files` by its one name (`_rooted`): made only when a link is followed, or a path
    is not one of them as given, so a section of many files reads each without going over all."""
    return {_rooted(file, roots) for file in files}


def _rooted(path: Path, roots: Sequence[Path]) -> Path:
    """The absolute `path` as named, `..` taken out, and from the resolved root when it is in the
    project, so a file in it has one name however the root was named."""
    inside = _under(path, roots)
    return Path(os.path.normpath(path)) if inside is None else roots[-1] / inside


def _parsed(path: Path, *, trusted: bool) -> tuple[tuple[Section, ...], bool] | str:
    """The context file's sections, read only when what opens there is a regular file. It is
    opened without waiting (`O_NONBLOCK`): a pipe the model left at the project's would otherwise
    hold this reading, and every reading of the prompt after it, since they run one at a time."""
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise OSError(f"{path} is not a regular file, so bh-02 did not read it")
            text = file.read().decode("utf-8")
        return parse(text, str(path), trusted=trusted)
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
