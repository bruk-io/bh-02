"""`/clear` and `/compact`: a new conversation, empty or begun from the model's summary of the
one so far, written over the transcript row's file in one step, the old kept beside it.

A long conversation makes every request longer: a local model processes more prompt before its
first token, and any model nears its context window. `/compact` asks the model for a summary
and begins a new conversation from it. The request is the loop's own (`request_for`: the prompt
the conversation began with, then the conversation, the registered tools offered as with every
step), so a model server reuses its work on the conversation, followed by bh-02 asking for the
summary in plain text: whatever the model calls is never run, and a step that calls rather than
answers gives no summary. A call a crash left unanswered, in a session resumed and compacted before
its next message (the loop answers it at the next reply, which /compact never goes through), is
answered in the request as the loop would answer it (`loop.lost_answers`, `asked`), so the model is
never sent a call with no result after it; the file's entries are never changed. The summary then
seeds the transcript's file (`seeded`, written whole by `transcript.rewrite`, the old file kept
beside it), and the loop and its transcript restart: the new conversation holds no prompt yet, so
the loop reads it afresh, folding in whatever changed since the old one began, and tells the date
again. The python row is left alone, and what it keeps is told: each function in the `carried` broker
is called as /compact runs (`carried`, off the event loop; one that raises is left out, never
failing /compact), and the lines they give go under the summary request, so the summary is
written knowing the real names, and into the new conversation's first message, worded as what was
held when it was compacted, since that message stays for good and a resume's REPL is empty. `/clear` is
the same rewrite with an empty conversation, and restarts the python row too (`clear`): nothing is
lost for good, the old conversation is the `.bak` beside the file.

The seed is also the record of the summary step (decision-0009, Conversations): its `user` entry
says when the new conversation began (`at`) and what the person asked the summary to keep
(`seed`, `""` for nothing), so no reader matches its wording, and its `assistant` entry, the
summary, carries the step's record. The step is collected and recorded by the loop's own `Step`
over the loop's own `Clock`, with the model's settings read as the loop reads them, so the
trajectory shows the boundary with its time and cost like any other step.

A command runs in the chat row's task, and Ctrl-C stops only a reply, so the model has `timeout`
seconds to answer, and a note says so as the step begins; the person leaving cancels the
command (`chat:converse`), and nothing is written until the summary is whole. The restart is
queued in `jobs` (CONTRACTS.md: jobs), never run in the chat row's task, which it reloads, and
a restart that fails is told to the person, since the new conversation is written by then; the
chat row reads its next line only once the restart is done, so the line reaches the new loop. The
transcript left mounted by a restart that failed is the old conversation's over the new one's file,
and refuses the next reply before the model is asked (`transcript.TranscriptReplaced`, naming
`/restart transcript`) rather than write it into either.
The pure parts (`asked`, `seeded`, `kept_in`, `_gathered`, `_is_seed`, `_unsaid`, `_unusable`, `_summed`,
`_answer`, `_unchanged`, `_cleared`, `unrestarted`) decide; the rest reads, writes and asks.
"""

import asyncio
import datetime
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agent_cordis_plugin.loop import Model, Step, lost_answers, request_for
from agent_cordis_plugin.records import Clock, StepRecord, settings_to_record, summed
from agent_cordis_plugin.stops import ACT, ANSWERED, REFUSED, SILENT, TRUNCATED, UNDECODABLE, classify
from agent_cordis_plugin.toolset import mode_of
from agent_cordis_plugin.transcript import FileTranscript, rewrite
from cordis_helpers import Job

__all__ = [
    "CLEAR",
    "COMPACT",
    "ConversationConfig",
    "Kept",
    "Offered",
    "Queue",
    "Rows",
    "Shown",
    "Unchanged",
    "asked",
    "clear_conversation",
    "compact_conversation",
    "kept_in",
    "seeded",
    "summarise",
    "unrestarted",
]

type Json = Mapping[str, Any]

COMPACT: Json = {
    "name": "compact",
    "help": "a new conversation from the model's summary of this one; the Python process is kept",
    "usage": "[WHAT TO KEEP]",
}
CLEAR: Json = {
    "name": "clear",
    "help": "a new conversation and a new Python process (the old one kept as .bak)",
}

# The component whose file /clear and /compact write the new conversation to: a row another
# fills may keep its file in another shape, which they must not write over.
_TRANSCRIPT = "agent:transcript"

# What the model is asked, after the conversation: what the summary is for, what it must carry,
# and that it is text, not a call.
_ASK = (
    "(bh-02: the person asked to compact this conversation (/compact). A new conversation begins "
    "from your summary of it, in place of everything above, so what the summary leaves out is "
    "gone. Write it for yourself, to carry on the work from: what the person asked for and still "
    "wants, in their words where those matter; what has been done, and what is left; the files "
    "read, written or changed, and why; what was decided, and why; the errors met and how they "
    "were fixed; and what you were about to do next. {namespace} Do not call python: "
    "answer with the summary alone, in plain text.)"
)
# The summary's sentence about the namespace: what it names, and, when bh-02 lists the names
# (`_LISTED`), that the list is below.
_NAMESPACE = (
    "Your Python namespace is kept: name what in it the work needs (variables, functions, imports) "
    "and what each holds."
)
_NAMESPACE_LISTED = (
    "Your Python namespace is kept, and bh-02 lists its names below, read from the Python process: "
    "name what in it the work needs (variables, functions, imports) and what each holds, "
    "which the list does not."
)
_KEEP = "(The person asks that the summary keep, in particular: {})"
# What the rows that keep something across /compact say of it, read as /compact runs.
_LISTED = "(bh-02, read just now:\n{lines})"
# The new conversation's first message, before the summary (the model's own, as its answer). It
# stays at the conversation's start for good, a resume's included, so it says only what stays
# true: the namespace was kept when the conversation was compacted, and empties as the python
# tool's instructions say.
_SEEDED = (
    "(bh-02: this conversation carries on from an earlier one, compacted (/compact) to the summary "
    "of it you wrote, which follows. Your Python namespace was kept when it was compacted, holding "
    "what the earlier inputs defined; it empties as your instructions about python say (bh-02 "
    "starting again, a resumed session too), so check that a name is still there before relying on it.)"
)
# After _SEEDED, when rows reported what they kept: past tense, because this message stays at the
# conversation's start for good and a resumed session's REPL is empty.
_SEEDED_LISTED = (
    "(bh-02, read when the conversation was compacted, so what was held then and not necessarily "
    "now:\n{lines})"
)
# Shown as the summary step begins: a command shows nothing until it answers.
_ASKING = (
    "compacting: the model is writing a summary of the conversation, in up to {timeout:g} seconds "
    "(the conversation row's `timeout`). Nothing changes until it is written; Ctrl-C doesn't stop it, "
    "leaving bh-02 does."
)
_NOTE = (
    "the conversation was compacted; a new one begins from the model's summary of it, below "
    "(the Python process and its variables are kept; the old transcript is {backup}):\n\n{summary}"
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
    """Why /compact changed nothing, said for the person. `usage`: the usage events the summary
    step sent before it gave none, which still count in the session's totals."""

    def __init__(self, why: str, usage: Sequence[Json] = ()) -> None:
        super().__init__(why)
        self.usage = list(usage)


@runtime_checkable
class Offered(Protocol):
    """What /compact needs of the `tools` value: the specs the loop offers (in name order),
    offered with the summary request as with every step, so the request reads as the loop's
    would."""

    def specs(self) -> Sequence[Json]: ...


@runtime_checkable
class Kept(Protocol):
    """What /compact needs of the `carried` value: the functions rows add, each called as
    `fn() -> str` as /compact runs, for one line of what the row keeps across it ('' for none)."""

    def __iter__(self) -> Iterator[Callable[[], str]]: ...


@runtime_checkable
class Rows(Protocol):
    """What /compact needs of the `loader` value (cordis.loader.Loader): the rows' states, each
    row as the loader mounted it (`rows`: its `entry`, so the transcript row's file is the one
    the running row writes, whatever the layer files say now), and a restart of several
    together."""

    def status(self) -> Mapping[str, str]: ...
    @property
    def rows(self) -> Mapping[str, Any]: ...
    async def restart(self, *rids: str) -> None: ...


@runtime_checkable
class Queue(Protocol):
    """What /clear and /compact need of the `jobs` value: a restart queued, and what the person
    is told if it fails."""

    def put(self, job: Job, failed: Callable[[str], str]) -> None: ...


@runtime_checkable
class Shown(Protocol):
    """What /compact needs of the `output` value: to show a note as the summary step begins, and
    to tell the person a restart it queued failed after the new conversation was written."""

    async def show(self, events: AsyncIterator[Json]) -> None: ...
    async def notice(self, message: str) -> None: ...


@dataclass(frozen=True, slots=True)
class ConversationConfig:
    """`timeout`: the seconds the model has to write `/compact`'s summary (Ctrl-C stops only a
    reply, so this is the longest /compact keeps the person waiting). `loop` and `transcript`:
    the rows /compact restarts, together; the transcript row's config `path` is the file the new
    conversation is written to. The python row is not among them: the summary refers to its
    namespace. `clear`: the rows /clear restarts, together (the python row among them, so the
    namespace empties with the conversation)."""

    timeout: float = 300.0
    loop: str = "loop"
    transcript: str = "transcript"
    clear: Sequence[str] = ("loop", "transcript", "python")


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


def asked(
    messages: Sequence[Json], keep: str = "", *, at: datetime.datetime, carried: Sequence[str] = ()
) -> list[Json]:
    """The summary request over a transcript's `messages`: the conversation as the loop sends it,
    then bh-02 asking for the summary (and for what the person asks it to keep, if anything).
    A call the transcript leaves unanswered (a process died mid-call) is answered in the request
    as the loop answers it at its next reply, `loop.lost_answers` made at `at`, so every call has
    a result; `messages` themselves are not changed. `carried` are the lines rows give of what
    they keep (`_gathered`), last in the request, and the request then says its list is there."""
    ask = "\n\n".join(
        [
            _ASK.format(namespace=_NAMESPACE_LISTED if carried else _NAMESPACE),
            *([_KEEP.format(keep.strip())] if keep.strip() else []),
            *([_LISTED.format(lines="\n".join(carried))] if carried else []),
        ]
    )
    whole = [*messages, *lost_answers(messages, at)]
    return [*request_for(whole), {"role": "user", "content": ask}]


def seeded(summary: str, keep: str, step: StepRecord, carried: Sequence[str] = ()) -> list[Json]:
    """The new conversation, before its first message: bh-02 saying what it carries on from,
    then the summary as the model's answer, so the roles still alternate. No prompt: the loop
    reads it afresh for the first message and keeps it as the conversation's first `system`
    entry, and no date, so it tells today's.

    The first entry says when the conversation began (`at`, the moment the summary step's request
    was handed to the model) and carries `seed`: `keep`, the text the person asked the summary to
    keep (`""` for none). The second carries the summary `step`'s record (`at`, `first_chunk`,
    `took`, `model`, `usage`, `settings`), the first step of the conversation. The first entry's
    text ends with the `carried` lines when there are any (`_SEEDED_LISTED`)."""
    told = "\n\n".join([_SEEDED, *([_SEEDED_LISTED.format(lines="\n".join(carried))] if carried else [])])
    return [
        {"role": "user", "content": told, "at": step["at"], "seed": {"keep": keep.strip()}},
        {"role": "assistant", "content": summary.strip(), "step": step},
    ]


def _gathered(lines: Sequence[object]) -> list[str]:
    """What rows gave of what they keep (`Kept`), as lines: each non-empty text, stripped; the
    entries that raised are already gone (`_carried_by`), and anything but text is left out."""
    return [each.strip() for each in lines if isinstance(each, str) and each.strip()]


def _carried_by(entries: Iterator[Callable[[], str]]) -> list[object]:
    """Call each entry of `carried`: what it returned, or nothing if it raised (a row's line
    about itself never fails /compact). Blocking calls: run off the event loop."""
    said: list[object] = []
    for entry in entries:
        try:
            said.append(entry())
        except Exception:
            continue
    return said


def _is_seed(message: Json) -> bool:
    """Whether `message` is the first entry of a compacted conversation: it carries `seed`."""
    return "seed" in message


def _unsaid(messages: Sequence[Json]) -> str | None:
    """Why `messages` hold nothing to compact, or None: an empty conversation, or one that is only
    a summary's seed (`seeded`), nothing said since (compacting it again would summarise a
    summary, with no prompt to begin the request, and replace the backup of the conversation
    before it). A seed is known by its `seed` field alone, never by its wording."""
    said = [m for m in messages if m.get("role") not in ("system", "tools")]
    if not said:
        return "nothing to compact: the conversation is empty"
    if len(said) == 2 and _is_seed(said[0]):
        return (
            "nothing to compact: nothing has been said since the last /compact, whose summary is "
            "the whole conversation"
        )
    return None


def _unusable(stop: str) -> str | None:
    """Why a summary step that ended `stop` (`stops.classify`) gave no summary; None when it
    answered."""
    if stop == ANSWERED:
        return None
    return _UNUSABLE.get(stop, f"the model's step ended {stop!r}, {_AGAIN}")


def _summed(usage: Sequence[Json]) -> list[Json]:
    """A step's usage events as one, or none (`records.summed`, which the loop records a step's
    usage with too). One event, so the length of /compact's answer never depends on how many
    parts a provider sends."""
    total = summed(usage)
    return [] if total is None else [{"type": "usage", **total}]


async def summarise(
    model: Model,
    messages: Sequence[Json],
    tools: Sequence[Json],
    timeout: float,
    clock: Clock | None = None,
) -> tuple[str, list[Json], StepRecord]:
    """The model's summary, from one step over `messages` (`asked`), the usage events that step
    sent, and the step's record (CONTRACTS.md: step record). The step is collected as the loop's
    are (`loop.Step`, over `clock`, the real one unless a test gives its own), begun as the
    request is handed to the model. Its settings are the model's, read as the loop reads them, and
    recorded whatever the old conversation recorded, since the summary is the first step of the
    conversation it begins (`seeded`). Raises `Unchanged` saying why there is none, with the usage
    sent before then: the step took longer than `timeout` seconds (it is closed, so its provider
    stops), it called rather than answered, or the model failed as a `loop` may (an exception
    with `kind` and `message`). Cancelled (the person left), it is closed too, and nothing is
    said."""
    step = Step(
        clock if clock is not None else Clock(),
        settings_to_record(getattr(model, "settings", None), ()),
        mode_of(model),
    )
    chunks = model.complete(messages, tools)
    limit = asyncio.timeout(timeout)
    try:
        async with limit:
            async for chunk in chunks:
                step.take(chunk)
    except TimeoutError:
        if not limit.expired():
            raise  # the model's own, not the time it had: a bug
        raise Unchanged(
            f"the model wrote no summary within {timeout:g} seconds, so nothing changed; try again, "
            "or give the conversation row a longer `timeout`",
            step.usage,
        ) from None
    except Exception as error:
        message = getattr(error, "message", None)
        if not isinstance(message, str) or not isinstance(getattr(error, "kind", None), str):
            raise  # not a failure the model reports for the person: a bug
        raise Unchanged(f"{message} (so nothing changed)", step.usage) from error
    finally:
        # a step left early (the timeout, or the person leaving) closes now, so its provider
        # stops what it runs
        if isinstance(chunks, AsyncGenerator):
            await chunks.aclose()
    if (why := _unusable(classify(step.finish, step.text, step.calls))) is not None:
        raise Unchanged(why, step.usage)
    return step.text.strip(), list(step.usage), step.record()


def _answer(summary: str, usage: Sequence[Json], backup: str, rows: Sequence[str]) -> list[Json]:
    """/compact's answer (CONTRACTS.md: event): `cleared` (the ui drops the old conversation, and
    a resume's replay starts here; `compacted`, so what commands hold for the model's next
    message is kept, since the summary could not carry what the model never read), the note
    carrying the summary, what the summary cost (`usage`, as one event, counted in the session's
    totals), then `restarting` the `rows`, last. The restart is queued before the chat row shows
    this, and may stop it showing the rest: the note is what must not be lost, so it comes
    second whatever the provider sent, as `/clear`'s does."""
    return [
        {"type": "cleared", "compacted": True},
        {"type": "note", "text": _NOTE.format(backup=backup, summary=summary)},
        *_summed(usage),
        *([{"type": "restarting", "rows": list(rows)}] if rows else []),
    ]


def _unchanged(why: str, usage: Sequence[Json]) -> str | list[Json]:
    """/compact's answer when nothing changed: `why`, then what the step cost if it sent usage
    (as one event), which still counts in the session's totals."""
    return [{"type": "note", "text": why}, *_summed(usage)] if usage else why


def unrestarted(config: ConversationConfig, why: str) -> str:
    """What the person is told when the restart /clear or /compact queued failed (`why`), after
    the new conversation was written: the loop may still hold the old one, and how to begin the
    new."""
    return (
        f"a new conversation was written, but restarting its rows failed ({why}), so the loop may "
        f"still hold the old one; /rows shows what is running, and /restart {config.transcript} "
        "begins the new one"
    )


def _cleared(backup: str | None, rows: Sequence[str]) -> list[Json]:
    """/clear's answer (CONTRACTS.md: event): `cleared` (the ui drops the old conversation, and
    what commands hold for the model is dropped with it), a note saying so and where the old
    conversation is kept, then `restarting` the `rows`, last: the restart may stop the chat row
    showing this answer, and the note is what must not be lost."""
    kept = f" (the old one is kept as {backup})" if backup else ""
    started = f"; starting afresh: {', '.join(rows)}" if rows else ""
    return [
        {"type": "cleared"},
        {"type": "note", "text": f"the conversation was cleared{kept}{started}"},
        *([{"type": "restarting", "rows": list(rows)}] if rows else []),
    ]


async def _once(event: Json) -> AsyncIterator[Json]:
    yield event


async def compact_conversation(
    args: str,
    *,
    model: Model,
    tools: Offered,
    carried: Kept,
    loader: Rows,
    output: Shown,
    config: ConversationConfig,
    jobs: Queue,
    clock: Clock | None = None,
) -> str | list[Json]:
    """`/compact [WHAT TO KEEP]`: ask the model for a summary of the conversation (a note says so
    as it begins), write the new conversation it begins in the transcript row's file (the old
    kept beside it, the new one holding what the person asked to keep and the summary step's
    record: `seeded`), and queue the restart of the loop and the transcript; answer `_answer`'s
    events, or why nothing changed (`_unchanged`). `jobs` is the conversation row's queue and
    `worker` the work that runs it, which a restart of the row ends: then nothing is written,
    since nothing would restart the rows. `clock` times the summary step (`summarise`) and dates the
    answers the request gives a call a crash left unanswered (`asked`). `carried`: asked once the
    conversation is known to be worth compacting, in a thread, and its lines are told in the
    request and the new conversation's first message; an entry that raises is left out."""
    row = config.transcript
    clock = clock if clock is not None else Clock()
    try:
        path = kept_in(row, loader.rows.get(row), loader.status().get(row))
    except Unchanged as why:
        return str(why)
    try:
        # in a thread: a long session's file takes a while to parse, and the TUI shares this loop
        messages = await asyncio.to_thread(lambda: FileTranscript(path).messages)
    except (OSError, ValueError) as error:
        return (
            f"the conversation in {path} can't be read ({error}), so nothing changed; it is the "
            f"{row!r} row's file, one JSON message per line"
        )
    if (nothing := _unsaid(messages)) is not None:
        return nothing
    await output.show(_once({"type": "note", "text": _ASKING.format(timeout=config.timeout)}))
    # in a thread: a row's function may do more than read a field, and the TUI shares this loop
    lines = _gathered(await asyncio.to_thread(_carried_by, iter(carried)))
    try:
        summary, usage, step = await summarise(
            model,
            asked(messages, args, at=clock.now(), carried=lines),
            list(tools.specs()),
            config.timeout,
            clock,
        )
    except Unchanged as why:
        return _unchanged(str(why), why.usage)
    try:
        # on the loop, not in a thread: from the rewrite to queueing the restart nothing may
        # cancel it (the person leaving), or the file would hold the new conversation and the
        # ui's history the old; the seed is small, and copying the old file to its backup is fast
        backup = rewrite(path, seeded(summary, args, step, lines))
    except OSError as error:
        return _unchanged(
            f"the new conversation could not be written to {path} ({error.strerror or error}), so "
            "nothing changed; check the directory's space and permissions",
            usage,
        )
    running = loader.status()
    rows = [rid for rid in (config.loop, config.transcript) if rid in running]
    if rows:
        # together: a row depending on both (the chat row, through `loop`) reloads once
        jobs.put(partial(loader.restart, *rows), partial(unrestarted, config))
    return _answer(summary, usage, backup, rows)


async def clear_conversation(
    args: str, *, loader: Rows, config: ConversationConfig, jobs: Queue
) -> str | list[Json]:
    """`/clear`: write an empty conversation over the transcript row's file (the old kept beside
    it, as /compact keeps it) and queue the restart of the `clear` rows that are running; answer
    `_cleared`'s events. A transcript that keeps the conversation in memory, or is filled by
    another component (whose file may be another shape), or has no file yet, is not written:
    its restart is the new conversation."""
    row, running = config.transcript, loader.status()
    try:
        path: str | None = kept_in(row, loader.rows.get(row), running.get(row))
    except Unchanged:
        path = None
    backup = None
    if path is not None and Path(path).is_file() and Path(path).stat().st_size:
        try:
            # on the loop, not in a thread: from the rewrite to queueing the restart nothing may
            # cancel it (the person leaving), or the file would be empty and the loop hold the old
            backup = rewrite(path, [])
        except OSError as error:
            return (
                f"the conversation in {path} could not be cleared ({error.strerror or error}), so "
                "nothing changed; check the directory's space and permissions"
            )
    rows = [rid for rid in config.clear if rid in running]
    if rows:
        # together: a row depending on several of them (the chat row, on `loop`) reloads once
        jobs.put(partial(loader.restart, *rows), partial(unrestarted, config))
    return _cleared(backup, rows)
