"""The `commands` value: slash commands by name, and line prefixes, from whichever rows offer them.

The broker pattern (paper 6.2): one row binds the registry, rows `acquire` a registration whose
return value is its remover, so a row that leaves takes its commands with it and nothing else
notices. A line is the harness's, not the model's, when it looks like a slash command (`/name`
then whitespace or the end), so a pasted `/tmp/app.py is broken` still reaches the model; or
when it starts with a prefix a row claimed (`!`, `commands:shell_command`'s): one character
each, kept in a registry of their own, so two rows can't claim the same one. `claims(line)` is
how the chat row asks which lines are the harness's, so what counts is decided here alone.

What a command leaves for the model (a `for_model` event in its answer: `!`'s output) is held
here, not shown, until the chat row takes it for the person's next message
(`take_for_model`). This row depends on nothing, so a restart of the chat row (`/model`
reloads the loop, and the chat row with it) keeps it; a new conversation (`cleared`, `/clear`'s
answer) drops it, and says so, but one carried on from a summary (`/compact`'s, `compacted`)
keeps it.
"""

import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, NotRequired, TypedDict

from cordis_helpers import Registry

__all__ = ["Answer", "Choice", "CommandSpec", "Commands", "Run", "parse"]

_COMMAND = re.compile(r"/([a-z][a-z-]*)(?:\s+(.*))?", re.S)


class Choice(TypedDict):
    """One way to call a command the palette offers as its own entry: `/NAME ARGS`."""

    args: str
    help: str


class CommandSpec(TypedDict):
    """What `/help` shows: the name (no slash), what it does, and how to call it; `choices`,
    if any, the arguments the palette offers as entries of their own, read each time it opens
    (`/model`'s models)."""

    name: str
    help: str
    usage: str
    choices: NotRequired[Callable[[], Sequence[Mapping[str, str]]]]


type Answer = str | Sequence[Mapping[str, Any]]
"""What a command answers (CONTRACTS.md: commands): text, shown as one note, or events shown
as they are (`/clear`'s `cleared`, then a note saying so), but for `for_model`, which the
`commands` value holds for the person's next message instead of answering it."""

type Run = Callable[[str], Awaitable[Answer]]
"""A command: its argument text in, what to show the person out."""


def parse(line: str) -> tuple[str, str] | None:
    """`(name, arguments)` when `line` is a command, else None."""
    match = _COMMAND.fullmatch(line.strip())
    return (match.group(1), (match.group(2) or "").strip()) if match else None


def _looks_like_command(line: str) -> bool:
    """Whether a line is meant as a slash command: `/name`, then whitespace or the end. A
    pasted `/tmp/app.py is broken` is not; `/Model` is (it is answered that it is no command,
    rather than sent to the model)."""
    head = line.strip().split(maxsplit=1)[0] if line.strip() else ""
    return (
        len(head) > 1
        and head[0] == "/"
        and head[1].isalpha()
        and all(c.isalpha() or c == "-" for c in head[1:])
    )


def _prefix_problem(prefix: object) -> str | None:
    """Why `prefix` can't be claimed, or None. A prefix takes every line that starts with it
    from the model, so it is one character, and never one that ordinary words start with (a
    letter, a digit), a space or `/`. Any other symbol is accepted: which one messages don't
    start with is the layer's author's choice (`$` starts a price, `#` and `-` Markdown, `>` a
    quote, `{` pasted JSON), and `!` is the shipped one."""
    if not isinstance(prefix, str) or len(prefix) != 1:
        return f"a prefix is one character, such as '!'; got {prefix!r}"
    if prefix == "/":
        return "'/' starts the slash commands; claim another character, such as '!'"
    if prefix.isalnum() or not prefix.isprintable() or prefix.isspace():
        return (
            f"a line can start with {prefix!r} by chance, so claiming it would take ordinary "
            "messages from the model; claim a symbol no message starts with, such as '!'"
        )
    return None


def _held_after(held: Sequence[str], answer: Answer) -> tuple[list[str], Answer]:
    """What is held for the model after a command's `answer`, and what of it to answer: a
    `for_model` event's text is held (and not answered); a `cleared` drops what was held,
    since a new conversation starts without it, and a note after the answer says so. A
    `cleared` that carries the conversation on from a summary (`compacted`, `/compact`'s)
    keeps it: the model never read it, so the summary can't hold it, and it still goes with
    the person's next message."""
    if isinstance(answer, str):
        return list(held), answer
    kept, dropped = list(held), 0
    shown: list[Mapping[str, Any]] = []
    for event in answer:
        if event.get("type") == "for_model":
            kept.append(str(event.get("text", "")))
            continue
        if event.get("type") == "cleared" and not event.get("compacted"):
            dropped, kept = dropped + len(kept), []
        shown.append(event)
    if dropped:
        what = "a command's output" if dropped == 1 else f"{dropped} commands' output"
        said = f"{what}, which was waiting for your next message, is dropped with the old conversation"
        shown.append({"type": "note", "text": said})
    return kept, shown


class Commands:
    """The broker: bound once, registered into by many; `/help` is its own."""

    def __init__(self) -> None:
        self._commands: Registry[tuple[CommandSpec, Run]] = Registry("command")
        self._prefixes: Registry[tuple[CommandSpec, Run]] = Registry("prefix")
        self._for_model: list[str] = []  # what commands left for the person's next message

    def register(self, spec: CommandSpec, run: Run) -> Callable[[], None]:
        """Offer `/NAME` (`spec`: name, help, usage) until the remover is called."""
        return self._commands.register(spec["name"], (spec, run))

    def claim(self, prefix: str, spec: CommandSpec, run: Run) -> Callable[[], None]:
        """Take every line that starts with `prefix` (one character, such as `!`) until the
        remover is called: `run` is given the rest of the line, and `/help` lists it as the
        prefix then `spec`'s usage. A prefix another row holds is refused."""
        if (problem := _prefix_problem(prefix)) is not None:
            raise ValueError(problem)
        return self._prefixes.register(prefix, (spec, run))

    def specs(self) -> list[CommandSpec]:
        """The slash commands (the palette's): a prefix is typed, not chosen."""
        return [spec for spec, _ in self._commands.values]

    def claims(self, line: str) -> bool:
        """Whether `line` is the harness's rather than the model's: a slash command (an unknown
        one included, so a typo never reaches the model), or a line that starts with a claimed
        prefix."""
        stripped = line.strip()
        return _looks_like_command(stripped) or (bool(stripped) and stripped[0] in self._prefixes)

    async def run(self, line: str) -> Answer:
        """Run what `line` names: the prefix it starts with, given the rest of the line, or the
        slash command; an unknown command says so, and never reaches the model. Answer what to
        show the person: what the command left for the model (`for_model`) is held instead,
        until `take_for_model`."""
        answer = await self._answer(line)
        self._for_model, shown = _held_after(self._for_model, answer)
        return shown

    def take_for_model(self) -> list[str]:
        """What commands left for the model since this was last asked, in the order they ran
        (`!`'s output, framed for the model); taking it empties it. The chat row puts it in
        front of the person's next message."""
        taken, self._for_model = self._for_model, []
        return taken

    async def _answer(self, line: str) -> Answer:
        """What the command `line` names answers, `for_model` and all."""
        stripped = line.strip()
        if stripped and (claimed := self._prefixes.get(stripped[0])) is not None:
            spec, run = claimed
            try:
                return await run(stripped[1:].strip())
            except Exception as error:
                return f"{stripped[0]} ({spec['name']}) failed: {error}"
        parsed = parse(line)
        if parsed is None:
            return f"{stripped!r} is not a command; /help lists them"
        name, args = parsed
        if name == "help":
            return self._help()
        entry = self._commands.get(name)
        if entry is None:
            return f"unknown command /{name}; /help lists them"
        try:
            return await entry[1](args)
        except Exception as error:
            return f"/{name} failed: {error}"

    def _help(self) -> str:
        rows = [("/help", "list the commands")]
        rows += [
            (f"/{s['name']}" + (f" {s['usage']}" if s["usage"] else ""), s["help"]) for s in self.specs()
        ]
        rows += [(f"{prefix}{spec['usage']}", spec["help"]) for prefix, (spec, _) in self._prefixes]
        # no key to leave by: that is each ui's own (the app's Ctrl-Q; another ui would name its
        # own), and each ui says it; Ctrl-C stops a reply in every ui (CONTRACTS.md: input.interrupted)
        rows += [("/exit", "leave; Ctrl-C stops a reply")]
        width = max(len(call) for call, _ in rows)
        return "\n".join(f"{call.ljust(width)}  {what}" for call, what in sorted(rows))
