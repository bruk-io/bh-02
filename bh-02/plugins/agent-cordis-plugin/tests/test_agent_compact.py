"""/compact over fake models, a fake loader and a temporary session's transcript file: the summary
request, the new conversation, the file written in one step, the answer as it streams, and the
restart it queues once the answer is read."""

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agent_cordis_plugin import (
    CompactConfig,
    FileTranscript,
    Unchanged,
    asked,
    compact,
    compact_conversation,
    kept_in,
    rewrite,
    seeded,
    summary_in,
    summary_step,
    unrestarted,
)
from cordis import Effects, Runtime, bind, component
from cordis.composition import Entry
from cordis.loader import resolve
from cordis_helpers import Job

type Json = Mapping[str, Any]

PYTHON: Json = {"name": "python", "description": "Run Python.", "parameters": {"type": "object"}}

# A conversation as the loop keeps it: the prompt it began with, a dated message, an input and
# its result, the answer, then a later prompt (a change, told as a note on the next message).
CONVERSATION: list[Json] = [
    {"role": "system", "content": "the prompt the conversation began with"},
    {"role": "user", "content": "(Today's date: 2026-10-06.)\n\nfind the answer", "today": "2026-10-06"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "name": "python", "input": {"code": "x = 6 * 7"}}],
    },
    {"role": "tool", "content": "", "call_id": "c1"},
    {"role": "assistant", "content": "x holds 42"},
    {"role": "system", "content": "the prompt as it read later"},
]


class Scripted:
    """A `model` that plays one scripted step per call and records what it was asked; `closed`
    says whether its last step was closed (left early, or read to its end)."""

    def __init__(self, *steps: Sequence[Json], hang: bool = False) -> None:
        self.steps = list(steps)
        self.hang = hang
        self.requests: list[tuple[list[Json], list[Json]]] = []
        self.closed = False

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        self.requests.append((list(messages), list(tools)))
        self.closed = False
        try:
            for chunk in self.steps.pop(0):
                yield chunk
            if self.hang:
                await asyncio.Event().wait()
        finally:
            self.closed = True


class Failing:
    """A `model` whose step fails: as a provider says a failure for the person (`kind`,
    `message`), or with `error` as it is."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        raise self.error
        yield  # pragma: no cover


class Limited(Exception):
    def __init__(self) -> None:
        super().__init__("rate limited; wait a minute")
        self.kind, self.message = "rate_limit", "rate limited; wait a minute"


class Tool:
    """The `kernel` value as /compact needs it: the one tool's spec."""

    @property
    def spec(self) -> Json:
        return PYTHON


@dataclass(frozen=True, slots=True)
class Mounted:
    """A row as the loader mounted it (one of `loader.rows`): its entry."""

    entry: Entry


class Loader:
    """The `loader` value: the rows' states, the rows as mounted, and restarts recorded (or
    failing with `fails`)."""

    def __init__(self, path: str | None) -> None:
        self.states = {rid: "active" for rid in ("loop", "transcript", "kernel", "chat", "model")}
        self.rows = {
            "loop": Mounted(Entry("loop", "agent:loop")),
            "transcript": Mounted(Entry("transcript", "agent:transcript", {"path": path} if path else {})),
            "kernel": Mounted(Entry("kernel", "kernel:kernel")),
        }
        self.batches: list[tuple[str, ...]] = []
        self.fails: Exception | None = None

    def status(self) -> dict[str, str]:
        return dict(self.states)

    async def restart(self, *rids: str) -> None:
        if self.fails is not None:
            raise self.fails
        self.batches.append(rids)


def text(s: str) -> Json:
    return {"type": "text", "text": s}


def stop(reason: str) -> Json:
    return {"type": "stop", "reason": reason}


USAGE: Json = {"type": "usage", "input_tokens": 1200, "output_tokens": 80}


def _session(tmp_path: Path, messages: Sequence[Json] = CONVERSATION) -> Path:
    """A temporary session's transcript file, holding `messages`."""
    path = tmp_path / "transcript.jsonl"
    path.write_text("".join(json.dumps(m) + "\n" for m in messages))
    return path


async def _drain(jobs: asyncio.Queue[Job]) -> None:
    while not jobs.empty():
        await (await jobs.get())()


def _working() -> asyncio.Future[None]:
    """The compact row's work, still running (a restart of the row would end it)."""
    return asyncio.get_running_loop().create_future()


async def _compact(
    loader: Loader,
    model: object,
    jobs: asyncio.Queue[Job] | None = None,
    worker: asyncio.Future[None] | None = None,
    args: str = "",
    timeout: float = 5,
) -> str | AsyncIterator[Json]:
    return await compact_conversation(
        args,
        model=model,  # type: ignore[arg-type]
        kernel=Tool(),
        loader=loader,
        config=CompactConfig(timeout=timeout),
        jobs=jobs if jobs is not None else asyncio.Queue(),
        worker=worker if worker is not None else _working(),
    )


async def _events(answer: str | AsyncIterator[Json]) -> list[Json]:
    assert not isinstance(answer, str), answer
    return [event async for event in answer]


ASKING = (
    "compacting: the model is writing a summary of the conversation, in up to 5 seconds (Ctrl-C "
    "stops it; nothing changes until the summary is written)"
)


def test_the_transcript_s_file_is_the_mounted_row_s_path() -> None:
    """Read from the row as the loader mounted it, never the layer files: only a running
    `agent:transcript` row's `path` is a file /compact may write the new conversation to."""
    mounted = Mounted(Entry("transcript", "agent:transcript", {"path": "/s/t.jsonl"}))
    assert kept_in("transcript", mounted, "active") == "/s/t.jsonl"
    refused = [
        ("transcript", None, None, "no 'transcript' row is running"),  # no such row
        (
            "transcript",
            Mounted(Entry("transcript", "agent:transcript", {}, True)),
            "disabled",
            "no 'transcript'",
        ),
        ("transcript", mounted, "unresolved: ImportError: x", "no 'transcript' row is running"),
        (
            "transcript",
            Mounted(Entry("transcript", "mine:transcript", {"path": "/s/t.db"})),
            "active",
            "the 'transcript' row is filled by mine:transcript, not agent:transcript",
        ),
        (
            "transcript",
            Mounted(Entry("transcript", "agent:transcript")),
            "active",
            "the 'transcript' row keeps the conversation in memory, not in a file",
        ),
    ]
    for row, entry, state, why in refused:
        with pytest.raises(Unchanged, match=re.escape(why)):
            kept_in(row, entry, state)


def test_rewrite_replaces_the_file_in_one_step_and_keeps_the_old_one_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _session(tmp_path)
    old = path.read_bytes()
    new = seeded("x holds 42")
    renames: list[tuple[str, str]] = []
    real = os.replace

    def watched(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        # the one step: the new conversation is whole beside the file, the old one still there
        assert Path(dst).read_bytes() == old
        assert [json.loads(line) for line in Path(src).read_text().splitlines()] == new
        renames.append((str(src), str(dst)))
        real(src, dst)

    monkeypatch.setattr(os, "replace", watched)
    backup = rewrite(str(path), new)
    assert renames == [(f"{path}.new", str(path))]
    assert FileTranscript(str(path)).messages == tuple(new)
    assert backup == f"{path}.bak" and Path(backup).read_bytes() == old
    assert sorted(p.name for p in tmp_path.iterdir()) == ["transcript.jsonl", "transcript.jsonl.bak"]


def test_a_later_rewrite_keeps_every_earlier_backup(tmp_path: Path) -> None:
    """Each conversation replaced is kept: the first as `.bak`, the next as `.bak.2`, ..."""
    path = _session(tmp_path)
    first = path.read_bytes()
    assert rewrite(str(path), seeded("one")) == f"{path}.bak"
    second = path.read_bytes()
    assert rewrite(str(path), seeded("two")) == f"{path}.bak.2"
    assert Path(f"{path}.bak").read_bytes() == first and Path(f"{path}.bak.2").read_bytes() == second
    assert FileTranscript(str(path)).messages == tuple(seeded("two"))


def test_a_rewrite_that_fails_leaves_the_transcript_as_it_was_and_no_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _session(tmp_path)
    old = path.read_bytes()

    def full(src: object, dst: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", full)
    with pytest.raises(OSError):
        rewrite(str(path), seeded("x holds 42"))
    assert path.read_bytes() == old
    assert sorted(p.name for p in tmp_path.iterdir()) == ["transcript.jsonl"]


async def test_the_summary_step_passes_its_chunks_on_and_the_summary_is_its_text() -> None:
    chunks = [text("x holds "), text("42."), {"type": "thinking", "text": "hm"}, USAGE, stop("end_turn")]
    model = Scripted(chunks)
    read = [c async for c in summary_step(model, asked(CONVERSATION), [PYTHON], 5)]
    assert read == chunks and model.closed
    assert model.requests == [(asked(CONVERSATION), [PYTHON])]  # the tool offered as the loop offers it
    assert summary_in(read) == "x holds 42."


@pytest.mark.parametrize(
    ("step", "why"),
    [
        (
            [{"type": "tool_call", "id": "c9", "name": "python", "input": {"code": "x"}}, stop("tool_use")],
            "the model called python instead of writing a summary (nothing ran), so nothing changed",
        ),
        ([text("x holds"), stop("max_tokens")], "the model's summary was cut off at its output limit"),
        ([stop("end_turn")], "the model's answer was empty, so nothing changed"),
        (
            [text("no"), stop("refusal")],
            "the model declined to summarise the conversation, so nothing changed; try /compact "
            "WHAT TO KEEP, naming what matters, or /clear to start afresh without a summary",
        ),
    ],
)
def test_a_step_that_did_not_answer_gives_no_summary_and_says_why(step: list[Json], why: str) -> None:
    with pytest.raises(Unchanged, match=re.escape(why)):
        summary_in(step)


async def test_a_summary_not_written_in_time_closes_the_step_and_says_so() -> None:
    """The step has `timeout` seconds; then it is closed, so its provider stops what it runs."""
    model = Scripted([text("x holds")], hang=True)
    with pytest.raises(Unchanged, match=r"no summary within 0\.05 seconds, so nothing changed"):
        await asyncio.wait_for(_read(summary_step(model, asked(CONVERSATION), [PYTHON], 0.05)), 5)
    assert model.closed


async def test_the_time_limit_never_cancels_whoever_reads_the_chunks() -> None:
    """The limit bounds the waits on the model only: a reader slower than it (a ui drawing
    each event) is never cancelled mid-wait; the next wait on the model then says the time ran
    out."""
    model = Scripted([text("x holds")], hang=True)
    step = summary_step(model, asked(CONVERSATION), [PYTHON], 0.05)
    assert await anext(step) == text("x holds")
    await asyncio.sleep(0.1)  # past the limit, in the reader: not cancelled
    with pytest.raises(Unchanged, match="no summary within"):
        await anext(step)
    assert model.closed


async def test_a_model_failure_is_said_for_the_person_and_a_bug_is_not_hidden() -> None:
    with pytest.raises(Unchanged, match=r"rate limited; wait a minute \(so nothing changed\)"):
        await _read(summary_step(Failing(Limited()), asked(CONVERSATION), [PYTHON], 5))
    with pytest.raises(KeyError):
        await _read(summary_step(Failing(KeyError("bug")), asked(CONVERSATION), [PYTHON], 5))


async def _read(chunks: AsyncIterator[Json]) -> list[Json]:
    return [c async for c in chunks]


async def test_compact_streams_its_answer_and_queues_the_restart_once_it_is_read(tmp_path: Path) -> None:
    """A note that the model is writing the summary, the step's usage as it comes, `cleared`,
    the note carrying the summary, then `restarting` the loop and the transcript; the kernel is
    not restarted. The file holds the new conversation, the old one is its `.bak`, and the
    restart is queued only once the answer is read to its end (the restart stops the chat row
    showing it), for the row's own work."""
    path = _session(tmp_path)
    old = path.read_bytes()
    loader, jobs = Loader(str(path)), asyncio.Queue[Job]()
    model = Scripted([USAGE, text("x holds 42; next, write it to answer.txt"), USAGE, stop("end_turn")])
    answer = await _compact(loader, model, jobs)
    assert not isinstance(answer, str)
    assert await anext(answer) == {"type": "note", "text": ASKING}
    assert model.requests == []  # asked only as the answer is read
    summary = "x holds 42; next, write it to answer.txt"
    read = [await anext(answer) for _ in range(5)]
    assert read == [
        USAGE,
        USAGE,
        {"type": "cleared"},
        {
            "type": "note",
            "text": "the conversation was compacted; a new one begins from the model's summary of it, "
            f"below (the kernel and its variables are kept; the old transcript is {path}.bak):\n\n{summary}",
        },
        {"type": "restarting", "rows": ["loop", "transcript"]},
    ]
    assert model.requests == [(asked(CONVERSATION), [PYTHON])]
    assert FileTranscript(str(path)).messages == tuple(seeded(summary))
    assert Path(f"{path}.bak").read_bytes() == old
    assert jobs.empty()  # `restarting` read, the answer not yet ended
    with pytest.raises(StopAsyncIteration):
        await anext(answer)
    assert loader.batches == []  # queued, not run in the caller's task
    await _drain(jobs)
    assert loader.batches == [("loop", "transcript")]  # together, and never the kernel


async def test_an_answer_abandoned_after_the_file_was_written_still_restarts(tmp_path: Path) -> None:
    """Stopped once the new conversation is written (Ctrl-C while `cleared` is shown), the
    restart is queued anyway, so the rows never keep the old conversation over the new file."""
    path = _session(tmp_path)
    loader, jobs = Loader(str(path)), asyncio.Queue[Job]()
    answer = await _compact(loader, Scripted([text("x holds 42"), stop("end_turn")]), jobs)
    assert not isinstance(answer, str) and isinstance(answer, AsyncIterator)
    while (await anext(answer))["type"] != "cleared":
        pass
    await answer.aclose()  # type: ignore[attr-defined]
    await _drain(jobs)
    assert loader.batches == [("loop", "transcript")]
    assert FileTranscript(str(path)).messages == tuple(seeded("x holds 42"))


async def test_stopped_while_the_model_writes_the_summary_nothing_changes(tmp_path: Path) -> None:
    """Ctrl-C, or the ui ending, closes the answer while the step runs: the step is closed (its
    provider stops), nothing is written and nothing restarts."""
    path = _session(tmp_path)
    old = path.read_bytes()
    loader, jobs = Loader(str(path)), asyncio.Queue[Job]()
    model = Scripted([USAGE], hang=True)
    answer = await _compact(loader, model, jobs)
    assert not isinstance(answer, str)
    assert [await anext(answer), await anext(answer)] == [{"type": "note", "text": ASKING}, USAGE]
    waiting = asyncio.ensure_future(anext(answer))
    await asyncio.sleep(0.01)
    waiting.cancel()  # the chat row's task cancelled mid-step
    await asyncio.gather(waiting, return_exceptions=True)
    await answer.aclose()  # type: ignore[attr-defined]
    assert model.closed
    assert path.read_bytes() == old and jobs.empty()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["transcript.jsonl"]


def _gone(loader: Loader, path: Path) -> None:
    loader.states.pop("transcript")
    loader.rows.pop("transcript")


@pytest.mark.parametrize(
    ("setup", "said"),
    [
        (_gone, "no 'transcript' row is running"),
        (lambda loader, path: loader.states.update(transcript="disabled"), "no 'transcript' row is running"),
        (
            lambda loader, path: loader.rows.update(
                transcript=Mounted(Entry("transcript", "agent:transcript"))
            ),
            "the 'transcript' row keeps the conversation in memory, not in a file",
        ),
        (lambda loader, path: path.write_text(json.dumps(CONVERSATION[0]) + "\n"), "nothing to compact"),
        (
            # only the seed of an earlier /compact: a summary of a summary, with no prompt
            lambda loader, path: path.write_text("".join(json.dumps(m) + "\n" for m in seeded("x holds 42"))),
            "nothing to compact: nothing has been said since the last /compact",
        ),
        (lambda loader, path: path.write_text("{not json\n"), "the conversation in "),
    ],
)
async def test_compact_with_nothing_to_compact_says_so_and_asks_nothing(
    tmp_path: Path, setup: Callable[[Loader, Path], object], said: str
) -> None:
    path = _session(tmp_path)
    loader, jobs, model = Loader(str(path)), asyncio.Queue[Job](), Scripted()
    setup(loader, path)
    answer = await _compact(loader, model, jobs)
    assert isinstance(answer, str) and answer.startswith(said), answer
    assert model.requests == [] and jobs.empty() and not Path(f"{path}.bak").exists()


async def test_a_conversation_carried_on_from_a_summary_compacts_again(tmp_path: Path) -> None:
    """Once something is said after the seed (the loop keeps the prompt with it), it compacts,
    and the earlier backup is kept."""
    path = _session(tmp_path)
    Path(f"{path}.bak").write_text("the conversation before the first /compact\n")
    carried = [
        *seeded("x holds 42"),
        {"role": "system", "content": "the prompt"},
        {"role": "user", "content": "go on"},
        {"role": "assistant", "content": "done"},
    ]
    path.write_text("".join(json.dumps(m) + "\n" for m in carried))
    loader, model = Loader(str(path)), Scripted([text("x holds 42, and it is done"), stop("end_turn")])
    events = await _events(await _compact(loader, model))
    assert events[-1] == {"type": "restarting", "rows": ["loop", "transcript"]}
    ((request, _),) = model.requests
    assert request[0] == {"role": "system", "content": "the prompt"}
    assert Path(f"{path}.bak").read_text() == "the conversation before the first /compact\n"
    assert [json.loads(line) for line in Path(f"{path}.bak.2").read_text().splitlines()] == carried


async def test_compact_without_a_summary_counts_its_usage_and_says_why_nothing_changed(
    tmp_path: Path,
) -> None:
    """The step's usage is passed on as it comes, so what a failed step cost still counts; then
    a note says why nothing changed."""
    path = _session(tmp_path)
    old = path.read_bytes()
    loader, jobs = Loader(str(path)), asyncio.Queue[Job]()
    model = Scripted([USAGE, text("x hol"), stop("max_tokens")])
    events = await _events(await _compact(loader, model, jobs))
    assert events[:2] == [{"type": "note", "text": ASKING}, USAGE]
    assert [e["type"] for e in events[2:]] == ["note"]
    assert str(events[2]["text"]).startswith("the model's summary was cut off at its output limit")
    assert path.read_bytes() == old and jobs.empty() and not Path(f"{path}.bak").exists()


async def test_compact_writes_nothing_once_its_row_has_restarted(tmp_path: Path) -> None:
    """The row restarted while the model wrote (its work, which would run the restart, ended):
    nothing is written, since nothing would restart the rows over the new file."""
    path = _session(tmp_path)
    old = path.read_bytes()
    worker = _working()
    worker.cancel()
    answer = await _compact(
        Loader(str(path)), Scripted([text("x holds 42"), stop("end_turn")]), worker=worker
    )
    events = await _events(answer)
    assert events[-1] == {
        "type": "note",
        "text": "the compact row restarted while the model wrote the summary, so nothing changed; "
        "try /compact again",
    }
    assert path.read_bytes() == old and not Path(f"{path}.bak").exists()


async def test_the_new_conversation_not_written_says_so_and_restarts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _session(tmp_path)
    jobs = asyncio.Queue[Job]()

    def full(src: object, dst: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", full)
    events = await _events(await _compact(Loader(str(path)), Scripted([text("x"), stop("end_turn")]), jobs))
    assert events[-1] == {
        "type": "note",
        "text": f"the new conversation could not be written to {path} (No space left on device), so "
        "nothing changed; check the directory's space and permissions",
    }
    assert jobs.empty()


class Registry:
    """The `commands` value as a row that offers commands needs it."""

    def __init__(self) -> None:
        self.commands: dict[str, tuple[Json, Callable[[str], Any]]] = {}

    def register(self, spec: Json, run: Callable[[str], Any]) -> Callable[[], None]:
        name = str(spec["name"])
        self.commands[name] = (spec, run)

        def remove() -> None:
            self.commands.pop(name, None)

        return remove


class Told:
    """The `output` value as the compact row needs it: notices recorded."""

    def __init__(self) -> None:
        self.notices: list[str] = []

    async def notice(self, message: str) -> None:
        self.notices.append(message)


async def test_the_compact_row_registers_compact_restarts_as_its_own_work_and_tells_a_failure(
    tmp_path: Path,
) -> None:
    """It depends on the model, the kernel's spec, the loader, `commands` and `output`, never on
    the loop or the transcript, which it restarts: the restart would reload it, cancelling its
    own work. A restart that fails, after the new conversation is written, is told."""
    assert resolve("agent:compact").inject == {"model", "kernel", "loader", "commands", "output"}
    path = _session(tmp_path)
    loader, commands, told = Loader(str(path)), Registry(), Told()
    model = Scripted([text("x holds 42"), stop("end_turn")], [text("x holds 42 still"), stop("end_turn")])

    @component(provides=("model", "kernel", "loader", "commands", "output"))
    async def values() -> Effects:
        yield bind("model", model)
        yield bind("kernel", Tool())
        yield bind("loader", loader)
        yield bind("commands", commands)
        yield bind("output", told)

    rt = Runtime()
    rt.mount(values, id="values")
    row = rt.mount(compact, id="compact", config=CompactConfig(timeout=5))
    await rt.settle()
    spec, run = commands.commands["compact"]
    assert spec["usage"] == "[WHAT TO KEEP]"
    said = await _events(await run(""))
    assert said[-1] == {"type": "restarting", "rows": ["loop", "transcript"]}
    await asyncio.sleep(0.01)
    assert loader.batches == [("loop", "transcript")]  # the row's own background work ran it
    loader.fails = LookupError("no row 'loop'")
    path.write_text(path.read_text() + json.dumps({"role": "user", "content": "more"}) + "\n")
    await _events(await run(""))
    await asyncio.sleep(0.01)
    assert told.notices == [unrestarted(CompactConfig(), "LookupError: no row 'loop'")]
    assert told.notices[0].endswith("/restart transcript begins the new one")
    await row.retire()
    await rt.settle()
    assert commands.commands == {}
    await rt.shutdown()
