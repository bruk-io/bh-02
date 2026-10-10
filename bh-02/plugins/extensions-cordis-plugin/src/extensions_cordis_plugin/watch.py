"""The decisions about the model's extensions, as pure functions of what was found.

Which files to load and unload (`changes`), which of them bh-02 may read (`refusal`,
`linked`), what an extension's state is (`Status`), and what the model, the status bar and the
status file are told (`instructions`, `status_forms`, `status_file`).
"""

import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Status",
    "changes",
    "extension_name",
    "instructions",
    "linked",
    "refusal",
    "status_file",
    "status_forms",
    "too_large",
]

_NAME = re.compile(r"[a-z][a-z0-9_]*")

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
    declined, the worker would not start); `commands`: the slash commands it registered; `tools`:
    the tools it registered; `problems`: registrations bh-02 refused (a command name already
    taken, a tool spec it could not offer)."""

    loading: bool = False
    rows: Mapping[str, str] = field(default_factory=dict)
    error: str | None = None
    commands: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
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


def refusal(file: str, mode: int, names: int) -> str | None:
    """Why bh-02 does not read the extension `file` (as the model names it, from the project),
    given what it opened there without following a link: its `mode` (`stat.S_IFLNK` when it is a
    link, which it did not open) and how many `names` it has. None when it may: a regular file of
    its own. The model writes the directory from the jail and bh-02 reads it on the host, so a
    link, or a second name (a hard link), could hand the model a file the jail hides."""
    if stat.S_ISLNK(mode):
        return (
            f"{file} is a link, which bh-02 does not follow there (it could lead to a file the jail "
            f"hides): write the extension itself at {file}, not a link to it"
        )
    if not stat.S_ISREG(mode):
        return f"{file} is not a regular file: write the extension at {file} as a file of its own"
    if names > 1:
        return (
            f"{file} has {names} names (a hard link), and bh-02 does not read one there (another "
            f"name could be a file the jail hides): write the extension at {file} as a file of its own"
        )
    if names < 1:
        return f"{file} was removed as bh-02 opened it: it loads when it is written again"
    return None


def too_large(file: str, limit: int) -> str:
    """Why bh-02 does not read the extension `file`: it is larger than `limit` bytes."""
    return (
        f"{file} is larger than {limit // 1024} KiB, so bh-02 did not read it: split it into "
        "extensions of their own"
    )


def linked(where: str, way: str) -> str:
    """Why bh-02 loads nothing from the extensions directory `where`: `way`, the first directory
    on the way to it from the project (`.bh-02`, say, or `where` itself), is a link. The model
    is told so in its prompt, since nothing is written through the link, status.json included."""
    return (
        f"{way} is a link, so bh-02 loads no extension from {where} (a link could lead to files "
        f"the jail hides): make {way} a directory in the project, not a link, and write the "
        f"extensions in {where}"
    )


def instructions(
    where: str,
    confined: bool,
    statuses: Mapping[str, Status],
    reference: str | None = None,
    refused: str = "",
) -> str:
    """What the model is told about extending bh-02 (a section of its system prompt): how, the
    part of cordis an extension uses, what it reaches of bh-02, and which ones there are. `where`
    is the extensions directory, relative to the project; `reference` is cordis's own design
    doc, when there is one to point at; `refused`, why bh-02 loads nothing from the directory
    (`linked`), when it can't."""
    consent = (
        "Extensions run in a jail of their own, as your `python` REPL (below) does: the project "
        "is their working "
        "directory and the only place they can write, and they cannot reach the network or "
        "read credentials. Nobody is asked first, to load one or to run a call to its tool."
        if confined
        else "bh-02 is running unjailed, so an extension would run with the person's own "
        "permissions: each is shown to the person, who decides whether it loads, and so is each "
        "call to a tool one registers, by its name and arguments."
    )
    more = f"cordis's design in full is {reference}; " if reference else ""
    lines = [
        "You can extend bh-02 yourself, while it runs. An extension is a Python module you "
        f"write at {where}/NAME.py (NAME: lowercase letters, digits and _). bh-02 loads it "
        "within a second of the write, loads it afresh whenever you change it, and unloads it "
        "when you delete the file; it stays with the project, so it loads again in every later "
        f"session here. {consent}",
        "",
        "An extension is cordis components, the same kind of part bh-02 itself is made of. A "
        "component is an async generator function marked @component: its keyword-only "
        "parameters are the keys it needs, and it yields effects. It runs only while every key "
        "it needs is bound, and starts again when one is replaced. When it leaves (its module "
        "changed or was deleted, a key it needs went), its effects are undone in reverse; a "
        "setup that raises undoes what it had done. So what it keeps in memory starts afresh "
        "then: keep what must last in a file. For example:",
        "",
        _EXAMPLE,
        "",
        "The effects, all from cordis, each yielded:",
        "- `acquire(fn, *args)` calls `fn` and keeps the remover it returns, called when the "
        "component leaves: how you register anything.",
        "- `bind(key, value)` provides `value` under `key`, for another extension's component to "
        "depend on by naming a parameter `key`.",
        "- `enter(cm)` enters an async context manager and holds it while the component lives.",
        "- `background(coro)` runs work the component owns, cancelled when it leaves: anything "
        "that keeps going, such as a status field it updates.",
        "Annotate a parameter with a typing Protocol and cordis checks the value against it "
        "before the component starts.",
        "",
        "What an extension reaches of bh-02, each only to add to it, each call returning its remover:",
        "- `commands.register(spec, run)`: a slash command for the person. `spec` has `name` "
        "(lowercase, no slash), `help` and `usage`; `run` is async, the command's argument text "
        "in, the text to show the person out. What a command shows reaches the person, not you.",
        "- `frame.status(field, text)`: text in the status bar. The latest push of a field shows: "
        "to change it from background work, push the new text, then call the old remover.",
        "- `system.add(text)`: text added to this prompt for your later turns.",
        "- `tools.register(spec, run)`: a tool offered to you, as `python` is. `spec` has `name` "
        "(lowercase letters, digits and _; not one of bh-02's own tools), `description` (what it "
        'does and when to call it) and `parameters` (a JSON Schema object: `type` "object", '
        "`properties`, `required`); `run` is async, the call's arguments as a dict in, the text "
        "you read out. Its calls run in the extension's jail, not in your REPL, and it lasts as "
        "the file does, across sessions, unlike a function in your REPL. You are told when one "
        "is added, changed or removed; whether a tool added mid-conversation can be called "
        "before the next conversation (/clear, /compact) is your model's, and the aside says. "
        "One bh-02 refuses is in status.json's `problems`, saying why.",
        "Whatever an extension added leaves with it, through `acquire` or not.",
        "",
        "Try a component in your REPL before you write its file: cordis is importable there "
        "(`import asyncio, cordis.testing`), and "
        "`asyncio.run(cordis.testing.drive(todo(commands=fake, system=fake)))` runs it with the "
        "fakes you pass (any object with the methods it calls: a types.SimpleNamespace will do) "
        "and returns the effects it yielded, unperformed (an effect's `.name` and `.args`). "
        f"{more}help(cordis.background) and the like say more. Whether each extension "
        f"loaded, and each component's traceback when one failed, is in {where}/status.json a "
        "moment after your write.",
    ]
    if statuses:
        # Names only: how each one is goes in status.json, so a load ending, or failing, does not
        # change this prompt: each change is an aside the loop sends the model with its next message.
        lines += [
            "",
            f"Extensions here: {', '.join(sorted(statuses))}. How each one is, is in {where}/status.json.",
        ]
    if refused:
        lines += ["", refused]
    return "\n".join(lines)


def status_forms(statuses: Mapping[str, Status]) -> tuple[str, ...]:
    """The status bar's extensions field, fullest form first (`ext: todo ✓ keep ✗`), then the
    count (`ext: 2, 1 ✗`); nothing when there are none."""
    if not statuses:
        return ()
    marks = [f"{name} {'…' if s.loading else '✓' if s.ok else '✗'}" for name, s in sorted(statuses.items())]
    bad = sum(1 for s in statuses.values() if not s.loading and not s.ok)
    return f"ext: {' '.join(marks)}", f"ext: {len(statuses)}" + (f", {bad} ✗" if bad else "")


def status_file(statuses: Mapping[str, Status]) -> dict[str, Any]:
    """`status.json`'s content: each extension's state, for the model to read in an input."""
    return {
        name: {
            "state": "loading" if s.loading else "active" if s.ok else "failed" if s.error else "partly up",
            "rows": dict(s.rows),
            "error": s.error,
            "commands": list(s.commands),
            "tools": list(s.tools),
            "problems": list(s.problems),
        }
        for name, s in sorted(statuses.items())
    }
