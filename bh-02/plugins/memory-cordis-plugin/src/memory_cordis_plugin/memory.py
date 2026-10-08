"""The `memory` value: Claude Code's memory files, found where Claude Code finds them and read
fresh each time they are asked for.

At the start of every conversation (and before each message the model reads, so an edit
reaches the next one), `text()` is what loads at launch, broadest first:

1. the managed policy's CLAUDE.md (`/etc/claude-code/CLAUDE.md` on Linux,
   `/Library/Application Support/ClaudeCode/CLAUDE.md` on macOS), which no exclude removes;
2. the person's own: `~/.claude/CLAUDE.md`, then each rule in `~/.claude/rules/` without `paths`;
3. each directory from the filesystem's root down to the project's: its `CLAUDE.md`, its
   `.claude/CLAUDE.md`, at the project's own the rules in `.claude/rules/` without `paths`,
   then its `CLAUDE.local.md`;
4. `AGENTS.md` and `.claude/AGENTS.md` as `instruction_files` says: by default only when none of
   those directories has a `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md`.

Each file's block-level HTML comments are taken out, and the files it imports (`@path`) follow
it, up to four hops. `touched(paths)` is what loads on demand, for the files an input opened: a
subdirectory's `CLAUDE.md` and `CLAUDE.local.md` (and `AGENTS.md`, as `instruction_files` says),
its `.claude/rules/`, and every rule whose `paths` match one of them. `excludes` (globs over
absolute paths) leaves files out. `listed()` is what `/memory` shows.

Every file is read through `reading.read`: one in the project, which the model can write, from
the project's root through no link but one to another memory file; one outside it as named,
unless its way passes through the project. A file in the project may import only files in it:
Claude Code asks about an import that leaves the project, and bh-02, which has nobody to ask in
a worker thread, does not follow one, and says so.
"""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from sys import platform

from memory_cordis_plugin.markdown import imports, uncommented, without_trailing
from memory_cordis_plugin.reading import read, roots, under
from memory_cordis_plugin.rules import matches, rule

__all__ = ["INSTRUCTION_FILES", "Entry", "Memory", "MemoryConfig", "Source", "described", "label", "where"]

INSTRUCTION_FILES = ("claude-md-or-agents-md", "claude-md-and-agents-md", "claude-md", "managed-only")
_MANAGED = {
    "linux": "/etc/claude-code/CLAUDE.md",
    "darwin": "/Library/Application Support/ClaudeCode/CLAUDE.md",
}
_CLAUDE = ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md")  # a directory's own: these count
_AGENTS = ("AGENTS.md", ".claude/AGENTS.md")
_HOPS = 4  # imports followed from a file, at most: Claude Code's limit
_PREFACE = (
    "Memory: what the person and the project keep for whichever agent works here, as Claude Code "
    "reads it (CLAUDE.md and AGENTS.md files, the files they import, and rules), broadest first. "
    "Where it names Claude Code or another agent it means you, and where it names that agent's "
    "tools, do the same in Python. Where two disagree, the later one wins. A subdirectory's "
    "CLAUDE.md, and a rule for some files, are told with the result of the first input that "
    "opens a file they cover."
)


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    """`root`: the project (the working directory, in Claude Code's words). `home`: the
    person's, theirs when unset. `instruction_files`: which of CLAUDE.md and AGENTS.md are read,
    as Claude Code's **Project instructions** setting names it. `excludes`: globs over absolute
    paths a memory file (as named, or where its links lead) is left out for, as Claude Code's
    `claudeMdExcludes`. `managed`: the managed policy's CLAUDE.md, the platform's when unset."""

    root: str = "."
    home: str | None = None
    instruction_files: str = "claude-md-or-agents-md"
    excludes: Sequence[str] = ()
    managed: str | None = None

    def __post_init__(self) -> None:
        if self.instruction_files not in INSTRUCTION_FILES:
            raise ValueError(
                f"`instruction_files` is one of {', '.join(INSTRUCTION_FILES)} (Claude Code's Project "
                f"instructions setting), not {self.instruction_files!r}"
            )
        if isinstance(self.excludes, str) or not all(isinstance(e, str) for e in self.excludes):
            raise TypeError(
                "`excludes` is a list of globs over absolute paths, as in "
                f'`excludes = ["**/other-team/CLAUDE.md"]`, not {self.excludes!r}'
            )


@dataclass(frozen=True, slots=True)
class Source:
    """A memory file: where it is, what it is (`managed`, `user`, `user-rule`, `instructions`,
    `local`, `agents`, `rule`, `imported`), the directory it covers (the project's root for a
    rule), and, for an import, the file that imports it."""

    path: Path
    kind: str
    covers: Path | None = None
    by: Path | None = None


@dataclass(frozen=True, slots=True)
class Entry:
    """One memory file as `/memory` lists it and the prompt tells it (the auto memory index, kind
    `auto`, is the memory-auto row's to tell): `state` is `loaded` (its
    `text` told), `on demand` (told when an input opens a file it covers), `missing`, `excluded`,
    `skipped` (an AGENTS.md `instruction_files` leaves out) or `not read` (`why`)."""

    source: Source
    state: str
    text: str = ""
    why: str = ""


class Memory:
    """Implements `memory` (CONTRACTS.md: memory) over one project, read fresh each time: it
    keeps nothing, so `/memory` on the event loop and the prompt in the loop's worker thread may
    ask at once."""

    def __init__(self, config: MemoryConfig, auto: str = "") -> None:
        self._config = config
        self._auto = auto  # the project's auto memory directory ('' for none), for `/memory`

    @property
    def instruction_files(self) -> str:
        return self._config.instruction_files

    def places(self) -> tuple[Path, Path]:
        """The project's root and the person's home, resolved."""
        return Path(self._config.root).resolve(), Path(self._config.home or Path.home()).resolve()

    def text(self) -> str:
        """The section of the system prompt: what loads at launch, each file whole, broadest
        first; '' when there is none."""
        root, home = self.places()
        return described(self.listed(), root, home)

    def listed(self) -> list[Entry]:
        """Every memory file loaded at launch, or that could be (missing, excluded, skipped, not
        read), and the rules and files told on demand, in the order the prompt has them."""
        root, home = self.places()
        sources, skipped = self._at_launch(root, home)
        files = [s.path for s in sources]
        entries: list[Entry] = []
        seen: set[Path] = set()
        for source in sources:
            entries += self._entry(source, files, root, home, seen)
        for path in skipped:
            entries.append(Entry(Source(path, "agents", path.parent), "skipped"))
        if self._auto:
            index = Path(self._auto) / "MEMORY.md"
            entries.append(Entry(Source(index, "auto"), "loaded" if os.path.lexists(index) else "missing"))
        return entries

    def touched(self, paths: Sequence[str]) -> list[tuple[str, str]]:
        """What loads on demand for `paths` (absolute: the files an input opened), each (file,
        text), broadest first: a subdirectory's instructions and rules, and the rules whose
        `paths` match. Called in the loop's worker thread (through the on-touch row's `notes`
        function), so it must not need the event loop."""
        root, home = self.places()
        found = roots(root)
        opened = [Path(p) for p in paths if under(Path(p), found) not in (None, PurePath("."))]
        if not opened:
            return []
        launch, _ = self._at_launch(root, home)
        agents = self._agents_below(root, home)
        sources: list[tuple[Source, str]] = []
        directories = sorted(
            {d for p in opened for d in _between(p.parent, root)}, key=lambda d: (len(d.parts), str(d))
        )
        for directory in directories:
            own = [
                directory / name for name in ("CLAUDE.md", "CLAUDE.local.md") if (directory / name).is_file()
            ]
            for path in own:
                kind = "local" if path.name == "CLAUDE.local.md" else "instructions"
                sources.append(
                    (Source(path, kind, directory), f"for work under {where(directory, root, home)}/")
                )
            if agents == "and" or (
                agents == "instead" and not any((directory / n).is_file() for n in _CLAUDE)
            ):
                for path in (directory / name for name in _AGENTS):
                    if path.is_file():
                        sources.append(
                            (
                                Source(path, "agents", directory),
                                f"for work under {where(directory, root, home)}/",
                            )
                        )
            for path in _rule_files(directory):
                sources.append((Source(path, "rule", directory), ""))
        for path in [*_rule_files(home), *_rule_files(root)]:
            sources.append((Source(path, "rule", root), ""))
        files = [*(s.path for s in launch), *(s.path for s, _ in sources)]
        told: list[tuple[str, str]] = []
        seen: set[Path] = set()
        for source, scope in sources:
            if self._excluded(source):
                continue
            said = self._on_demand(source, scope, opened, files, root, home, seen)
            if said:
                told.append((str(source.path), said))
        return told

    def _at_launch(self, root: Path, home: Path) -> tuple[list[Source], list[Path]]:
        """The memory files launch reads, in order (some missing, for `/memory` to name), and the
        AGENTS.md files there that `instruction_files` leaves out."""
        mode = self._config.instruction_files
        managed = Path(self._config.managed or _MANAGED.get(platform, _MANAGED["linux"]))
        sources = [Source(managed, "managed")]
        if mode == "managed-only":
            return sources, []
        sources.append(Source(home / ".claude" / "CLAUDE.md", "user"))
        sources += [Source(p, "user-rule", root) for p in _rule_files(home)]
        directories = [*reversed(root.parents), root]
        agents = _agents_mode(mode, _counted(directories, home))
        skipped: list[Path] = []
        for directory in directories:
            here = [directory / "CLAUDE.md", directory / ".claude" / "CLAUDE.md"]
            sources += [
                Source(p, "instructions", directory) for p in here if p.is_file() or directory == root
            ]
            if directory == root:
                sources += [Source(p, "rule", root) for p in _rule_files(root)]
            local = directory / "CLAUDE.local.md"
            if local.is_file() or directory == root:
                sources.append(Source(local, "local", directory))
            for path in (directory / name for name in _AGENTS):
                if path.is_file():
                    if agents is None:
                        skipped.append(path)
                    else:
                        sources.append(Source(path, "agents", directory))
        return sources, skipped

    def _agents_below(self, root: Path, home: Path) -> str | None:
        """How a subdirectory's AGENTS.md loads on demand: `and` beside its CLAUDE.md files,
        `instead` only where it has none, or None (never)."""
        mode = self._config.instruction_files
        if mode in ("claude-md", "managed-only"):
            return None
        if mode == "claude-md-and-agents-md":
            return "and"
        return None if _counted([*reversed(root.parents), root], home) else "instead"

    def _entry(
        self, source: Source, files: Sequence[Path], root: Path, home: Path, seen: set[Path]
    ) -> list[Entry]:
        """A launch source as entries: itself (loaded, on demand, missing, excluded, not read)
        and, when loaded, the files it imports."""
        path = source.path
        if not os.path.lexists(path):
            return [Entry(source, "missing")]
        if source.kind != "managed" and self._excluded(source):
            return [Entry(source, "excluded")]
        real = path.resolve()
        if real in seen:
            return []  # read already (a CLAUDE.md that links to the AGENTS.md beside it, an import)
        try:
            text = uncommented(read(path, files, root))
        except OSError as error:
            return [Entry(source, "not read", why=str(error))]
        seen.add(real)
        if source.kind in ("rule", "user-rule"):
            found = rule(text)
            if found.paths:
                return [Entry(source, "on demand", why=", ".join(found.paths))]
            text = found.text
        return [
            Entry(source, "loaded", text.strip()),
            *self._imported(source, text, files, root, home, seen, 1),
        ]

    def _imported(
        self,
        source: Source,
        text: str,
        files: Sequence[Path],
        root: Path,
        home: Path,
        seen: set[Path],
        hop: int,
    ) -> list[Entry]:
        """The files `text` (`source`'s) imports, each followed by its own imports, up to `_HOPS`."""
        if hop > _HOPS:
            return []
        found = roots(root)
        out: list[Entry] = []
        for raw in imports(text):
            target = _resolved(raw, source.path.parent, home)
            if target is None:
                continue  # not a file: text that happens to start with @
            imported = Source(target, "imported", source.covers, by=source.path)
            if self._excluded(imported):
                out.append(Entry(imported, "excluded"))
                continue
            if under(source.path, found) is not None and under(target, found) is None:
                out.append(
                    Entry(
                        imported,
                        "not read",
                        why=f"{where(source.path, root, home)} is in the project, which the model can write, "
                        "so it may import only files in the project",
                    )
                )
                continue
            real = target.resolve()
            if real in seen:
                continue
            try:
                said = uncommented(read(target, [*files, target], root))
            except OSError as error:
                out.append(Entry(imported, "not read", why=str(error)))
                continue
            seen.add(real)
            out += [
                Entry(imported, "loaded", said.strip()),
                *self._imported(imported, said, files, root, home, seen, hop + 1),
            ]
        return out

    def _on_demand(
        self,
        source: Source,
        scope: str,
        opened: Sequence[Path],
        files: Sequence[Path],
        root: Path,
        home: Path,
        seen: set[Path],
    ) -> str:
        """What one on-demand source tells, with the files it imports: '' when it does not apply
        (a rule whose `paths` match none of `opened`, or one with none at the project's root,
        told already at launch) or can't be read."""
        try:
            text = uncommented(read(source.path, files, root))
        except OSError:
            return ""
        named = where(source.path, root, home)
        if source.kind == "rule":
            found = rule(text)
            covers = source.covers or root
            if found.paths:
                relative = [p.relative_to(covers) for p in opened if p.is_relative_to(covers)]
                if not any(matches(p, pattern) for p in relative for pattern in found.paths):
                    return ""
                head = f"From {named}, a rule for {', '.join(found.paths)}"
            elif covers == root:
                return ""  # a rule for everything at the project's root is told at launch
            else:
                head = f"From {named}, a rule for work under {where(covers, root, home)}/"
            text = found.text
        else:
            head = f"From {named}, instructions {scope}"
        real = source.path.resolve()
        if real in seen:
            return ""
        seen.add(real)
        parts = [f"{head}:\n\n{text.strip()}"]
        for entry in self._imported(source, text, files, root, home, seen, 1):
            imported = where(entry.source.path, root, home)
            if entry.state == "loaded":
                by = where(entry.source.by or source.path, root, home)
                parts.append(f"From {imported}, imported by {by}:\n\n{entry.text}")
            elif entry.state == "not read":
                parts.append(f"(bh-02 did not import {imported}: {entry.why})")
        return "\n\n".join(parts)

    def _excluded(self, source: Source) -> bool:
        """Whether an exclude leaves `source` out: its path as named, or where its links lead."""
        if source.kind == "managed":
            return False
        names = {PurePath(os.path.normpath(source.path)), PurePath(source.path.resolve())}
        return any(name.full_match(pattern) for name in names for pattern in self._config.excludes)


def described(entries: Sequence[Entry], root: Path, home: Path) -> str:
    """The prompt's section from `listed()`: each file loaded, whole, with what it is; one line for
    each import that was not read, saying why. '' when nothing loaded."""
    parts: list[str] = []
    for entry in entries:
        named = where(entry.source.path, root, home)
        if entry.source.kind == "auto":
            continue  # the memory-auto row's section, read once a conversation
        if entry.state == "loaded" and entry.text:
            parts.append(f"Contents of {named} ({label(entry.source, root, home)}):\n\n{entry.text}")
        elif entry.state == "not read" and entry.source.kind == "imported":
            parts.append(f"(bh-02 did not import {named}: {entry.why})")
    return "\n\n".join([_PREFACE, *parts]) if parts else ""


def label(source: Source, root: Path, home: Path) -> str:
    """What a memory file is, as the prompt and `/memory` say it."""
    covers = source.covers
    elsewhere = covers is not None and covers != root
    under_it = f"for everything under {where(covers, root, home)}/" if covers is not None else ""
    match source.kind:
        case "managed":
            return "managed policy, for everyone on this machine"
        case "user":
            return "the person's own instructions, for every project"
        case "user-rule":
            return "the person's own rule, for every project"
        case "instructions":
            return (
                f"instructions {under_it}" if elsewhere else "project instructions, checked into the codebase"
            )
        case "local":
            return (
                f"the person's own instructions {under_it}"
                if elsewhere
                else "the person's own instructions for this project, not checked in"
            )
        case "agents":
            return (
                f"instructions for any agent, {under_it}"
                if elsewhere
                else "project instructions for any agent"
            )
        case "rule":
            return "a project rule"
        case "auto":
            return (
                "the model's auto memory index, told at the start of each conversation (the memory-auto row)"
            )
        case _:
            return f"imported by {where(source.by or source.path, root, home)}"


def where(path: Path, root: Path, home: Path) -> str:
    """How a file is named: from the project's root inside it, from `~` inside the home, whole
    otherwise."""
    if path == root:
        return "."
    if path.is_relative_to(root):
        return str(path.relative_to(root))
    if path.is_relative_to(home):
        return "~/" + str(path.relative_to(home))
    return str(path)


def _agents_mode(mode: str, any_claude: bool) -> str | None:
    """Whether launch reads AGENTS.md: `and` (beside CLAUDE.md), `instead` (no CLAUDE.md is
    there), or None."""
    if mode == "claude-md-and-agents-md":
        return "and"
    if mode == "claude-md-or-agents-md" and not any_claude:
        return "instead"
    return None


def _counted(directories: Sequence[Path], home: Path) -> bool:
    """Whether a directory from the filesystem's root to the project's has a CLAUDE.md,
    `.claude/CLAUDE.md` or CLAUDE.local.md, which keeps AGENTS.md out by default. The person's
    `~/.claude/CLAUDE.md` does not count, as in Claude Code."""
    own = home / ".claude" / "CLAUDE.md"
    return any((d / n).is_file() and d / n != own for d in directories for n in _CLAUDE)


def _between(directory: Path, root: Path) -> list[Path]:
    """The directories from `directory` up to the project's root, the root left out: those whose
    instructions load on demand for a file in `directory`."""
    out: list[Path] = []
    while directory != root and directory.is_relative_to(root):
        out.append(directory)
        directory = directory.parent
    return out


def _rule_files(directory: Path) -> list[Path]:
    """The rule files in `directory`'s `.claude/rules/`, sorted: every `.md` under it."""
    rules = directory / ".claude" / "rules"
    return sorted(p for p in rules.rglob("*.md") if p.is_file()) if rules.is_dir() else []


def _resolved(raw: str, base: Path, home: Path) -> Path | None:
    """The file an import names, or None: relative to the importing file's directory, absolute,
    or from the home (`~/`); as written, then without the punctuation a sentence put after it."""
    for candidate in dict.fromkeys((raw, without_trailing(raw))):
        if not candidate:
            continue
        if candidate.startswith("~/"):
            path = home / candidate[2:]
        else:
            path = Path(candidate) if Path(candidate).is_absolute() else base / candidate
        path = Path(os.path.normpath(path))
        if path.is_file():
            return path
    return None
