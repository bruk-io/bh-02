"""`/compact`: a new conversation, begun from the model's summary of the one so far.

A long conversation makes every request longer: a local model processes more prompt before its
first token, and any model nears its context window. `/compact` asks the model for a summary
and begins a new conversation from it. The request is the loop's own (`request_for`: the prompt
the conversation began with, then the conversation, the kernel's one tool offered as with every
step), so a model server reuses its work on the conversation, followed by bh-02 asking for the
summary in plain text: whatever the model calls is never run, and a step that calls rather than
answers gives no summary. The summary then seeds the transcript's file (`seeded`, written whole
by `transcript.rewrite`, the old file kept beside it), and the loop and its transcript restart:
the new conversation holds no prompt yet, so the loop reads it afresh, folding in whatever
changed since the old one began, and tells the date again. The kernel is left alone, since the
summary names what its namespace holds.

The answer is a stream of events (CONTRACTS.md: commands), which the chat row shows as they
come and stops as it stops a turn (Ctrl-C, or the ui ending): first a note that the model is
writing the summary, then the step's usage as it is sent, then `cleared`, the note carrying the
summary and `restarting`, or a note saying why nothing changed. Nothing is written until the
summary is whole, so a stop before then changes nothing. The restart is queued for the compact
row's own work (cordis-helpers' `perform`), never run in the chat row's task, which it reloads,
and only once the answer has been read to its end: the chat row shows all of it before the
restart can stop it. An answer abandoned after the file was written still queues it, so the
file and the rows never disagree. The pure parts (`asked`, `seeded`, `kept_in`, `summary_in`,
`unrestarted`) decide; the rest reads, writes and asks.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, runtime_checkable

from agent_cordis_plugin.loop import Model, request_for
from agent_cordis_plugin.stops import ACT, ANSWERED, REFUSED, SILENT, TRUNCATED, UNDECODABLE, classify
from agent_cordis_plugin.transcript import FileTranscript, rewrite
from cordis_helpers import Job

__all__ = [
    "SPEC",
    "CompactConfig",
    "Noticed",
    "Offered",
    "Rows",
    "Unchanged",
    "asked",
    "compact_conversation",
    "kept_in",
    "seeded",
    "summary_in",
    "summary_step",
    "unrestarted",
]

type Json = Mapping[str, Any]

SPEC: Json = {
    "name": "compact",
    "help": "a new conversation from the model's summary of this one; the kernel is kept",
    "usage": "[WHAT TO KEEP]",
}

# The component whose file /compact writes the new conversation to: another may keep its file
# in another shape, which /compact must not write over.
_TRANSCRIPT = "agent:transcript"

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
# The new conversation's first message, before the summary (the model's own, as its answer). It
# stays at the start of the conversation for good, so it says only what stays true: the namespace
# was kept when the conversation was compacted, and empties as the kernel's instructions say.
_SEEDED_START = "(bh-02: this conversation carries on from an earlier one"
_SEEDED = (
    f"{_SEEDED_START}, compacted (/compact) to the summary of it you wrote, which follows. Your "
    "Python namespace was kept when it was compacted, holding what the earlier inputs defined; "
    "it empties as your instructions about python say (bh-02 starting again, a resumed session "
    "too), so check that a name is still there before relying on it.)"
)
_ASKING = (
    "compacting: the model is writing a summary of the conversation, in up to {timeout:g} seconds "
    "(Ctrl-C stops it; nothing changes until the summary is written)"
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
    REFUSED: (
        "the model declined to summarise the conversation, so nothing changed; try /compact WHAT "
        "TO KEEP, naming what matters, or /clear to start afresh without a summary"
    ),
}


class Unchanged(Exception):
    """Why /compact changed nothing, said for the person."""


@runtime_checkable
class Offered(Protocol):
    """What /compact needs of the `kernel` value: the one tool's spec, offered with the summary
    request as the loop offers it with every step, so the request reads as the loop's would."""

    @property
    def spec(self) -> Json: ...


@runtime_checkable
class Rows(Protocol):
    """What /compact needs of the `loader` value (cordis.loader.Loader): the rows' states, each
    row as it was mounted (`rows`: its `entry`, so the transcript row's file is the one the
    running row writes), and a restart of several together."""

    def status(self) -> Mapping[str, str]: ...
    @property
    def rows(self) -> Mapping[str, Any]: ...
    async def restart(self, *rids: str) -> None: ...


@runtime_checkable
class Noticed(Protocol):
    """What the compact row needs of the `output` value: a notice, to say a restart it queued
    failed after the new conversation was written."""

    async def notice(self, message: str) -> None: ...


@dataclass(frozen=True, slots=True)
class CompactConfig:
    """`timeout`: the seconds the model has to write the summary (Ctrl-C stops it sooner).
    `loop` and `transcript`: the rows /compact restarts, together; the transcript row's config
    `path` is the file the new conversation is written to. The kernel is not among them: the
    summary refers to its namespace."""

    timeout: float = 300.0
    loop: str = "loop"
    transcript: str = "transcript"


def kept_in(row: str, mounted: object, state: str | None) -> str:
    """The file the transcript row `row` keeps the conversation in, from the row as the loader
    mounted it (`mounted`, one of `loader.rows`: its `entry`) and its `state` (`loader.status()`):
    the config's `path` of a running `agent:transcript` row. Raises `Unchanged` saying why there
    is none: no such row running, one another component fills (its file may be another shape,
    which /compact must not write over), or one that keeps the conversation in memory."""
    entry = getattr(mounted, "entry", None)
    if entry is None or state is None or not state.startswith("active"):
        raise Unchanged(
            f"no {row!r} row is running, so there is no conversation to compact; /rows lists the rows"
        )
    if (use := getattr(entry, "use", None)) != _TRANSCRIPT:
        raise Unchanged(
            f"the {row!r} row is filled by {use}, not {_TRANSCRIPT}, so /compact can't write the "
            "new conversation to its file; nothing changed"
        )
    config = getattr(entry, "config", None)
    path = config.get("path") if isinstance(config, Mapping) else None
    if not isinstance(path, str) or not path:
        raise Unchanged(
            f"the {row!r} row keeps the conversation in memory, not in a file (its `path`, which a "
            "session's layer sets), so it can't begin again from a summary; nothing changed"
        )
    return path


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


def _unsaid(messages: Sequence[Json]) -> str | None:
    """Why `messages` hold nothing to compact, or None: an empty conversation, or one that is
    only a summary's seed (`seeded`), nothing said since (compacting it again would ask for a
    summary of a summary, with no prompt)."""
    said = [m for m in messages if m.get("role") != "system"]
    if not said:
        return "nothing to compact: the conversation is empty"
    if len(said) == 2 and str(said[0].get("content", "")).startswith(_SEEDED_START):
        return (
            "nothing to compact: nothing has been said since the last /compact, whose summary is "
            "the whole conversation"
        )
    return None


def summary_in(chunks: Sequence[Json]) -> str:
    """The summary a step's `chunks` give: the text of a step that answered (`stops.classify`).
    Raises `Unchanged` saying why there is none: it called (nothing ran), was cut off, said
    nothing or refused."""
    said = "".join(str(c.get("text") or "") for c in chunks if c.get("type") == "text")
    calls = [c for c in chunks if c.get("type") == "tool_call"]
    finish = next((c.get("reason") for c in reversed(chunks) if c.get("type") == "stop"), None)
    if (stop := classify(finish, said, calls)) != ANSWERED:
        raise Unchanged(_UNUSABLE.get(stop, f"the model's step ended {stop!r}, {_AGAIN}"))
    return said.strip()


def unrestarted(config: CompactConfig, why: str) -> str:
    """What the person is told when the restart /compact queued failed (`why`), after the new
    conversation was written: the loop may still hold the old one, and how to begin the new."""
    return (
        f"/compact wrote the new conversation, but restarting {config.loop!r} and "
        f"{config.transcript!r} failed ({why}), so the loop may still hold the old one; "
        f"/restart {config.transcript} begins the new one"
    )


async def summary_step(
    model: Model, messages: Sequence[Json], tools: Sequence[Json], timeout: float
) -> AsyncGenerator[Json]:
    """One model step over `messages` (`asked`), its chunks as they come. The step has `timeout`
    seconds in all, which bound only the waits on the model, never a yield, so whoever reads the
    chunks is never cancelled by them. Raises `Unchanged` saying why there is no summary: the
    time ran out, or the model failed as a `loop` may (an exception with `kind` and `message`).
    The step is closed however it ends, so its provider stops what it runs."""
    chunks = model.complete(messages, tools)
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while True:
            limit = asyncio.timeout_at(deadline)
            try:
                async with limit:
                    chunk = await anext(chunks, None)
            except TimeoutError:
                if not limit.expired():
                    raise  # the model's own, not the time it had: a bug
                raise Unchanged(
                    f"the model wrote no summary within {timeout:g} seconds, so nothing changed; try "
                    "again, or give the compact row a longer `timeout`"
                ) from None
            except Exception as error:
                message = getattr(error, "message", None)
                if not isinstance(message, str) or not isinstance(getattr(error, "kind", None), str):
                    raise  # not a failure the model reports for the person: a bug
                raise Unchanged(f"{message} (so nothing changed)") from error
            if chunk is None:
                return
            yield chunk
    finally:
        if isinstance(chunks, AsyncGenerator):
            await chunks.aclose()


async def compact_conversation(
    args: str,
    *,
    model: Model,
    kernel: Offered,
    loader: Rows,
    config: CompactConfig,
    jobs: asyncio.Queue[Job],
    worker: asyncio.Future[None],
) -> str | AsyncIterator[Json]:
    """`/compact [WHAT TO KEEP]`: text saying why there is nothing to compact, or the events of
    compacting (`_compacting`), which the chat row shows as they come. `jobs` is the compact
    row's queue and `worker` the work that runs it, which a restart of the row ends."""
    row = config.transcript
    try:
        path = kept_in(row, loader.rows.get(row), loader.status().get(row))
    except Unchanged as why:
        return str(why)
    try:
        messages = FileTranscript(path).messages
    except (OSError, ValueError) as error:
        return (
            f"the conversation in {path} can't be read ({error}), so nothing changed; it is the "
            f"{row!r} row's file, one JSON message per line, which the row reads again when it restarts"
        )
    if (nothing := _unsaid(messages)) is not None:
        return nothing
    return _compacting(path, messages, args, model, kernel, loader, config, jobs, worker)


async def _compacting(
    path: str,
    messages: Sequence[Json],
    keep: str,
    model: Model,
    kernel: Offered,
    loader: Rows,
    config: CompactConfig,
    jobs: asyncio.Queue[Job],
    worker: asyncio.Future[None],
) -> AsyncIterator[Json]:
    """Ask for the summary, write the new conversation over `path` (the old kept beside it), and
    answer (CONTRACTS.md: event): a note that the model is writing it, the step's `usage` as it
    is sent (counted in the session's totals whatever the step gives), then `cleared` (the ui
    drops the old conversation, and a resume's replay starts here), the note carrying the
    summary and `restarting` the loop and the transcript; or a note saying why nothing changed.
    The restart is queued once the answer has been read to its end, or abandoned after the file
    was written."""
    yield {"type": "note", "text": _ASKING.format(timeout=config.timeout)}
    read: list[Json] = []
    try:
        step = summary_step(model, asked(messages, keep), [kernel.spec], config.timeout)
        async with contextlib.aclosing(step):
            async for chunk in step:
                if chunk.get("type") == "usage":
                    yield chunk
                else:
                    read.append(chunk)
        summary = summary_in(read)
        if worker.done():  # the row restarted meanwhile: nothing would run the restart
            raise Unchanged(f"the compact row restarted while the model wrote the summary, {_AGAIN}")
    except Unchanged as why:
        yield {"type": "note", "text": str(why)}
        return
    try:
        backup = rewrite(path, seeded(summary))
    except OSError as error:
        yield {
            "type": "note",
            "text": f"the new conversation could not be written to {path} ({error.strerror or error}), "
            "so nothing changed; check the directory's space and permissions",
        }
        return
    running = loader.status()
    rows = [rid for rid in (config.loop, config.transcript) if rid in running]
    try:
        yield {"type": "cleared"}
        yield {"type": "note", "text": _NOTE.format(backup=backup, summary=summary)}
        if rows:
            yield {"type": "restarting", "rows": rows}
    finally:
        # together: a row depending on both (the chat row, through `loop`) reloads once
        if rows:
            jobs.put_nowait(partial(loader.restart, *rows))
