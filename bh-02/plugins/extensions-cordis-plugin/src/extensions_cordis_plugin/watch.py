"""The decisions about the model's extensions, as pure functions of what was found.

Which files to load and unload (`changes`), whether a jail confines what runs in it
(`is_confined`), what an extension's state is (`Status`), and what the model, the status bar
and the status file are told (`instructions`, `status_forms`, `status_file`).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Status",
    "changes",
    "extension_name",
    "instructions",
    "is_confined",
    "status_file",
    "status_forms",
]

_NAME = re.compile(r"[a-z][a-z0-9_]*")
_CONFINING = ("fs_write", "network")  # as the kernel's: what a jail must enforce to confine code

_EXAMPLE = """    from cordis import Effects, acquire, component

    @component
    async def todo(*, commands, system) -> Effects:
        items: list[str] = []

        async def run(args: str) -> str:
            if args:
                items.append(args)
            return "\\n".join(items) or "nothing to do"

        spec = {"name": "todo", "help": "Keep a to-do list", "usage": "/todo [ITEM]"}
        yield acquire(commands.register, spec, run)
        yield acquire(system.add, "The person keeps a to-do list with /todo.")"""


@dataclass(frozen=True, slots=True)
class Status:
    """One extension, as last heard of. `rows`: each component's state (`active`, `waiting on:
    KEY`, `failed: ...`); `error`: why the module did not load at all (or why it was not loaded:
    declined, the worker would not start); `commands`: the slash commands it registered;
    `problems`: registrations bh-02 refused (a command name already taken)."""

    loading: bool = False
    rows: Mapping[str, str] = field(default_factory=dict)
    error: str | None = None
    commands: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Loaded, with every component active and nothing refused."""
        return (
            not self.loading
            and self.error is None
            and not self.problems
            and all(state == "active" for state in self.rows.values())
        )


def extension_name(file: str) -> str | None:
    """The extension a file in the extensions directory is (`todo.py` is `todo`), or None for
    one that is not: another suffix, or a name that is not lowercase letters, digits and `_`."""
    stem, dot, suffix = file.rpartition(".")
    return stem if dot and suffix == "py" and _NAME.fullmatch(stem) else None


def changes(
    before: Mapping[str, object], after: Mapping[str, object]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What to load (new, or changed since: its stamp differs) and what to unload (gone), by name,
    each sorted."""
    load = tuple(sorted(name for name, stamp in after.items() if before.get(name) != stamp))
    unload = tuple(sorted(name for name in before if name not in after))
    return load, unload


def is_confined(report: Mapping[str, str]) -> bool:
    """Whether a jail's report says what runs in it can write only where it was allowed and
    reach no network: the kernel's rule, so extensions load without asking exactly when cells
    run without asking."""
    return all(report.get(axis) == "enforced" for axis in _CONFINING)


def _summary(name: str, status: Status, where: str) -> str:
    if status.loading:
        return f"- {name}: loading"
    if status.error is not None:
        return f"- {name}: not loaded ({status.error.splitlines()[-1]}); {where}/status.json has why"
    commands = f" ({', '.join(status.commands)})" if status.commands else ""
    if status.ok:
        return f"- {name}: active{commands}"
    return f"- {name}: loaded, but not all of it is up{commands}; {where}/status.json has why"


def instructions(where: str, confined: bool, statuses: Mapping[str, Status]) -> str:
    """What the model is told about extending bh-02 (a section of its system prompt): how, what
    an extension reaches, and the state of each one there is. `where` is the extensions
    directory, relative to the project."""
    consent = (
        "Extensions run in a jail of their own, as your cells do: the project is their working "
        "directory and the only place they can write, and they cannot reach the network or "
        "read credentials. Nobody is asked first."
        if confined
        else "bh-02 is running unjailed, so an extension would run with the person's own "
        "permissions: each is shown to the person, who decides whether it loads."
    )
    lines = [
        "You can extend bh-02 yourself, while it runs. An extension is a Python module you "
        f"write at {where}/NAME.py (NAME: lowercase letters, digits and _). bh-02 loads it "
        "within a second of the write, loads it afresh whenever you change it, and unloads it "
        "when you delete the file; it stays with the project, so it loads again in every later "
        f"session here. {consent}",
        "",
        "An extension is cordis components: async generator functions marked @component, whose "
        "keyword-only parameters are the keys they need. A component yields effects, and every "
        "effect is undone when its module changes or is deleted, so state it keeps in memory "
        "starts afresh then (keep what must last in a file). For example:",
        "",
        _EXAMPLE,
        "",
        "What an extension reaches of bh-02, each only to add to it; each call returns its "
        "remover, so make it through `acquire`:",
        "- `commands.register(spec, run)`: a slash command for the person. `spec` has `name` "
        "(lowercase, no slash), `help` and `usage`; `run` is async, the command's argument text "
        "in, the text to show the person out. What a command shows reaches the person, not you.",
        "- `frame.status(field, text)`: text in the status bar; push again to change it.",
        "- `system.add(text)`: text added to this prompt for your later turns.",
        "A component may also `bind(key, value)` (from cordis) for another extension's "
        f"component to depend on by that key. Whether each extension loaded, and each "
        f"component's traceback when one failed, is in {where}/status.json a moment after "
        "your write.",
    ]
    if statuses:
        lines += ["", "Extensions now:"]
        lines += [_summary(name, statuses[name], where) for name in sorted(statuses)]
    return "\n".join(lines)


def status_forms(statuses: Mapping[str, Status]) -> tuple[str, ...]:
    """The status bar's extensions field, fullest form first (`ext: todo ✓ notes ✗`), then the
    count (`ext: 2, 1 ✗`); nothing when there are none."""
    if not statuses:
        return ()
    marks = [f"{name} {'…' if s.loading else '✓' if s.ok else '✗'}" for name, s in sorted(statuses.items())]
    bad = sum(1 for s in statuses.values() if not s.loading and not s.ok)
    return f"ext: {' '.join(marks)}", f"ext: {len(statuses)}" + (f", {bad} ✗" if bad else "")


def status_file(statuses: Mapping[str, Status]) -> dict[str, Any]:
    """`status.json`'s content: each extension's state, for the model to read in a cell."""
    return {
        name: {
            "state": "loading" if s.loading else "active" if s.ok else "failed" if s.error else "partly up",
            "rows": dict(s.rows),
            "error": s.error,
            "commands": list(s.commands),
            "problems": list(s.problems),
        }
        for name, s in sorted(statuses.items())
    }
