"""`/compact`: a new conversation, begun from the model's summary of the one so far.

A long conversation makes every request longer: a local model processes more prompt before its
first token, and any model nears its context window. `/compact` asks the model for a summary
and begins a new conversation from it. The request is the loop's own (`request_for`: the prompt
the conversation began with, then the conversation, the kernel's one tool offered as with every
step), so a model server reuses its work on the conversation, followed by bh-02 asking for the
summary in plain text: whatever the model calls is never run, and a step that calls rather than
answers gives no summary. The summary then seeds the transcript's file (`seeded`, written whole
by `transcript.rewrite`, the old file kept as `.bak`), and the loop and its transcript restart:
the new conversation holds no prompt yet, so the loop reads it afresh, folding in whatever
changed since the old one began, and tells the date again. The kernel is left alone, since the
summary names what its namespace holds.

A command runs in the chat row's task and can't be interrupted, so the model has `timeout`
seconds to answer. The restart is queued for the compact row's own work (cordis-helpers'
`perform`), never run in the chat row's task, which it reloads (the operator's `/clear` does
the same). The pure parts (`asked`, `seeded`, `kept_in`, `_unusable`, `_answer`) decide; the rest
reads, writes and asks.
"""

import asyncio
from collections.abc import AsyncGenerator, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agent_cordis_plugin.loop import Model, request_for
from agent_cordis_plugin.stops import ACT, ANSWERED, REFUSED, SILENT, TRUNCATED, UNDECODABLE, classify
from agent_cordis_plugin.transcript import FileTranscript, rewrite
from cordis_helpers import Job

__all__ = [
    "SPEC",
    "CompactConfig",
    "Offered",
    "Rows",
    "Unsummarised",
    "asked",
    "compact_conversation",
    "kept_in",
    "seeded",
    "summarise",
]

type Json = Mapping[str, Any]

SPEC: Json = {
    "name": "compact",
    "help": "a new conversation from the model's summary of this one; the kernel is kept",
    "usage": "[WHAT TO KEEP]",
}

# What the model is asked, after the conversation: what the summary is for, what it must carry,
# and that it is text, not a call.
_ASK = (
    "(bh-02: the person asked to compact this conversation (/compact). A new conversation begins "
    "from your summary of it, in place of everything above, so what the summary leaves out is "
    "gone. Write it for yourself, to carry on the work from: what the person asked for and still "
    "wants, in their words where those matter; what has been done, and what is left; the files "
    "read, written or changed, and why; what was decided, and why; the errors met and how they "
    "were fixed; and what you were about to do next. Your Python namespace is kept: name what in "
    "it the work needs (variables, functions, imports) and what each holds. Do not call python: "
    "answer with the summary alone, in plain text.)"
)
_KEEP = "(The person asks that the summary keep, in particular: {})"
# The new conversation's first message, before the summary (the model's own, as its answer).
_SEEDED = (
    "(bh-02: this conversation carries on from an earlier one, compacted (/compact) to the "
    "summary of it you wrote, which follows. Your Python namespace is as the earlier "
    "conversation left it: what its inputs defined is still there.)"
)
_NOTE = (
    "the conversation was compacted; a new one begins from the model's summary of it, below "
    "(the kernel and its variables are kept; the old transcript is {backup}):\n\n{summary}"
)
_AGAIN = "so nothing changed; try /compact again"
_CALLED = f"the model called python instead of writing a summary (nothing ran), {_AGAIN}"
# Why a step that did not answer gave no summary, by how it ended (`stops.classify`).
_UNUSABLE: Mapping[str, str] = {
    ACT: _CALLED,
    UNDECODABLE: _CALLED,
    TRUNCATED: (
        f"the model's summary was cut off at its output limit, {_AGAIN}, naming what to keep "
        "(`/compact WHAT TO KEEP`), for a shorter one"
    ),
    SILENT: f"the model's answer was empty, {_AGAIN}",
    REFUSED: "the model declined to summarise the conversation, so nothing changed",
}


class Unsummarised(Exception):
    """Why the model gave no summary, said for the person; nothing was changed."""


@runtime_checkable
class Offered(Protocol):
    """What /compact needs of the `kernel` value: the one tool's spec, offered with the summary
    request as the loop offers it with every step, so the request reads as the loop's would."""

    @property
    def spec(self) -> Json: ...


@runtime_checkable
class Rows(Protocol):
    """What /compact needs of the `loader` value (cordis.loader.Loader): the rows running, the
    rows composed (where the transcript row's file is), and a restart of several together."""

    def status(self) -> Mapping[str, str]: ...
    def entries(self) -> Sequence[Any]: ...
    async def restart(self, *rids: str) -> None: ...


@dataclass(frozen=True, slots=True)
class CompactConfig:
    """`timeout`: the seconds the model has to write the summary (a command can't be
    interrupted, so this is the longest /compact keeps the person waiting). `loop` and
    `transcript`: the rows /compact restarts, together; the transcript row's config `path` is
    the file the new conversation is written to. The kernel is not among them: the summary
    refers to its namespace."""

    timeout: float = 300.0
    loop: str = "loop"
    transcript: str = "transcript"


def kept_in(entries: Iterable[Any], row: str) -> str | None:
    """The file the transcript row `row` keeps the conversation in (its config's `path`, as
    `agent:transcript` takes it), or None: no such row, or one that keeps it in memory."""
    entry = next((e for e in entries if getattr(e, "id", None) == row), None)
    config = getattr(entry, "config", None)
    path = config.get("path") if isinstance(config, Mapping) else None
    return path if isinstance(path, str) and path else None


def asked(messages: Sequence[Json], keep: str = "") -> list[Json]:
    """The summary request over a transcript's `messages`: the conversation as the loop sends it,
    then bh-02 asking for the summary (and for what the person asks it to keep, if anything)."""
    ask = "\n\n".join([_ASK, *([_KEEP.format(keep.strip())] if keep.strip() else [])])
    return [*request_for(messages), {"role": "user", "content": ask}]


def seeded(summary: str) -> list[Json]:
    """The new conversation, before its first message: bh-02 saying what it carries on from,
    then the summary as the model's answer, so the roles still alternate. No prompt: the loop
    reads it afresh for the first message and keeps it as the conversation's first `system`
    entry, and no date, so it tells today's."""
    return [{"role": "user", "content": _SEEDED}, {"role": "assistant", "content": summary.strip()}]


def _unusable(stop: str) -> str | None:
    """Why a summary step that ended `stop` (`stops.classify`) gave no summary; None when it
    answered."""
    if stop == ANSWERED:
        return None
    return _UNUSABLE.get(stop, f"the model's step ended {stop!r}, {_AGAIN}")


async def summarise(
    model: Model, messages: Sequence[Json], tools: Sequence[Json], timeout: float
) -> tuple[str, list[Json]]:
    """The model's summary, from one step over `messages` (`asked`), and the usage events that
    step sent. Raises `Unsummarised` saying why there is none: the step took longer than
    `timeout` seconds (it is closed, so its provider stops), it called rather than answered, or
    the model failed as a `loop` may (an exception with `kind` and `message`)."""
    text: list[str] = []
    calls: list[Json] = []
    usage: list[Json] = []
    finish: str | None = None
    chunks = model.complete(messages, tools)
    limit = asyncio.timeout(timeout)
    try:
        async with limit:
            async for chunk in chunks:
                match chunk.get("type"):
                    case "text":
                        text.append(str(chunk.get("text") or ""))
                    case "tool_call":
                        calls.append(chunk)
                    case "usage":
                        usage.append(chunk)
                    case "stop":
                        finish = chunk.get("reason")
    except TimeoutError:
        if not limit.expired():
            raise  # the model's own, not the time it had: a bug
        raise Unsummarised(
            f"the model wrote no summary within {timeout:g} seconds, so nothing changed; try again, "
            "or give the compact row a longer `timeout`"
        ) from None
    except Exception as error:
        message = getattr(error, "message", None)
        if not isinstance(message, str) or not isinstance(getattr(error, "kind", None), str):
            raise  # not a failure the model reports for the person: a bug
        raise Unsummarised(f"{message} (so nothing changed)") from error
    finally:
        # a step left early (the timeout) closes now, so its provider stops what it runs
        if isinstance(chunks, AsyncGenerator):
            await chunks.aclose()
    said = "".join(text)
    if (why := _unusable(classify(finish, said, calls))) is not None:
        raise Unsummarised(why)
    return said.strip(), usage


def _answer(summary: str, usage: Sequence[Json], backup: str, rows: Sequence[str]) -> list[Json]:
    """/compact's answer (CONTRACTS.md: event): what the summary cost (`usage`, counted in the
    session's totals), `cleared` (the ui drops the old conversation, and a resume's replay
    starts here), the note carrying the summary, then `restarting` the `rows`, last: the restart
    may stop the session showing this answer, and the note is what must not be lost."""
    return [
        *usage,
        {"type": "cleared"},
        {"type": "note", "text": _NOTE.format(backup=backup, summary=summary)},
        *([{"type": "restarting", "rows": list(rows)}] if rows else []),
    ]


async def compact_conversation(
    args: str, *, model: Model, kernel: Offered, loader: Rows, config: CompactConfig, jobs: asyncio.Queue[Job]
) -> str | list[Json]:
    """`/compact [WHAT TO KEEP]`: ask the model for a summary of the conversation, write the new
    conversation it begins in the transcript row's file (the old kept as `.bak`), and queue the
    restart of the loop and the transcript; answer `_answer`'s events, or text saying why
    nothing changed."""
    running = loader.status()
    if config.transcript not in running:
        return (
            f"no {config.transcript!r} row is running, so there is no conversation to compact; "
            "/rows lists the rows"
        )
    path = kept_in(loader.entries(), config.transcript)
    if path is None:
        return (
            f"the {config.transcript!r} row keeps the conversation in memory, not in a file (its "
            "`path`, which a session's layer sets), so it can't begin again from a summary; nothing changed"
        )
    messages = FileTranscript(path).messages
    if not any(m.get("role") != "system" for m in messages):
        return "nothing to compact: the conversation is empty"
    summary, usage = await summarise(model, asked(messages, args), [kernel.spec], config.timeout)
    try:
        backup = rewrite(path, seeded(summary))
    except OSError as error:
        return (
            f"the new conversation could not be written to {path} ({error.strerror or error}), so "
            "nothing changed; check the directory's space and permissions"
        )
    rows = [rid for rid in (config.loop, config.transcript) if rid in running]

    async def job() -> None:
        # together: a row depending on both (the chat row, through `loop`) reloads once
        await loader.restart(*rows)

    await jobs.put(job)
    return _answer(summary, usage, backup, rows)
