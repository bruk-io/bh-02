"""/compact over fake models, a fake loader and a temporary session's transcript file: the summary
request, the new conversation, the file written in one step, and the restart it queues."""

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_cordis_plugin import (
    CompactConfig,
    FileTranscript,
    LoopModel,
    MemoryTranscript,
    Unsummarised,
    asked,
    compact,
    compact_conversation,
    kept_in,
    rewrite,
    seeded,
    summarise,
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


class Loader:
    """The `loader` value: the rows running, the rows composed, and restarts recorded."""

    def __init__(self, path: str | None) -> None:
        self.rows = {rid: "active" for rid in ("loop", "transcript", "kernel", "chat", "model")}
        self.composed = [
            Entry("loop", "agent:loop"),
            Entry("transcript", "agent:transcript", {"path": path} if path else {}),
            Entry("kernel", "kernel:kernel"),
        ]
        self.batches: list[tuple[str, ...]] = []

    def status(self) -> dict[str, str]:
        return dict(self.rows)

    def entries(self) -> list[Entry]:
        return list(self.composed)

    async def restart(self, *rids: str) -> None:
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


def test_the_summary_request_is_the_loop_s_request_then_the_ask() -> None:
    """The prompt the conversation began with, the conversation (the later prompt told as a
    note, so not sent), then bh-02 asking for the summary in plain text; what the person asks
    the summary to keep goes with it."""
    request = asked(CONVERSATION)
    assert request[:-1] == [{"role": "system", "content": "the prompt the conversation began with"}] + [
        m for m in CONVERSATION if m["role"] != "system"
    ]
    ask = str(request[-1]["content"])
    assert request[-1]["role"] == "user" and ask.startswith("(bh-02: the person asked to compact")
    assert "Your Python namespace is kept" in ask and "Do not call python" in ask
    kept = asked(CONVERSATION, "  the names of the API's endpoints ")
    assert str(kept[-1]["content"]) == (
        f"{ask}\n\n(The person asks that the summary keep, in particular: the names of the API's endpoints)"
    )


async def test_the_new_conversation_is_bh_02_s_note_then_the_summary_and_the_loop_starts_it_afresh() -> None:
    """The seed holds no prompt and no date, so the loop's first message after it keeps the
    prompt as it reads now as the conversation's start (no note of a change) and tells the date."""
    seed = seeded("  x holds 42.  ")
    assert [m["role"] for m in seed] == ["user", "assistant"] and seed[1]["content"] == "x holds 42."
    assert str(seed[0]["content"]).startswith("(bh-02: this conversation carries on from an earlier one")
    history = MemoryTranscript()
    for message in seed:
        history.append(message)
    model = Scripted([text("carrying on"), stop("end_turn")])

    class Prompt:
        def text(self) -> str:
            return "the prompt as it reads now"

    class Approved:
        async def approve(self, request: Json) -> bool:
            return True

    class Kernel(Tool):
        def instructions(self) -> str:
            return ""

        async def run(self, code: str) -> str:
            return ""

        def touched(self) -> tuple[str, ...]:
            return ()

    loop = LoopModel(model, Kernel(), history, Approved(), system=Prompt(), today=lambda: "2026-10-07")
    events = [e async for e in loop.reply("next")]
    assert not [e for e in events if e["type"] == "note"]  # nothing told as changed
    ((messages, _),) = model.requests
    assert messages == [
        {"role": "system", "content": "the prompt as it reads now"},
        *seed,
        {"role": "user", "content": "(Today's date: 2026-10-07.)\n\nnext", "today": "2026-10-07"},
    ]


def test_the_transcript_s_file_is_its_row_s_path() -> None:
    entries = [Entry("loop", "agent:loop"), Entry("transcript", "agent:transcript", {"path": "/s/t.jsonl"})]
    assert kept_in(entries, "transcript") == "/s/t.jsonl"
    assert kept_in(entries, "history") is None  # no such row
    assert kept_in([Entry("transcript", "agent:transcript")], "transcript") is None  # in memory


def test_rewrite_replaces_the_file_in_one_step_and_keeps_the_old_one_as_bak(
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


def test_a_rewrite_that_fails_leaves_the_transcript_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _session(tmp_path)
    old = path.read_bytes()

    def full(src: object, dst: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", full)
    with pytest.raises(OSError):
        rewrite(str(path), seeded("x holds 42"))
    assert path.read_bytes() == old and not Path(f"{path}.new").exists()


async def test_a_summary_is_the_text_of_a_step_that_answered_with_its_usage() -> None:
    model = Scripted(
        [text("x holds "), text("42."), {"type": "thinking", "text": "hm"}, USAGE, stop("end_turn")]
    )
    assert await summarise(model, asked(CONVERSATION), [PYTHON], 5) == ("x holds 42.", [USAGE])
    assert model.requests == [(asked(CONVERSATION), [PYTHON])]  # the tool offered as the loop offers it


@pytest.mark.parametrize(
    ("step", "why"),
    [
        (
            [{"type": "tool_call", "id": "c9", "name": "python", "input": {"code": "x"}}, stop("tool_use")],
            "the model called python instead of writing a summary (nothing ran), so nothing changed",
        ),
        ([text("x holds"), stop("max_tokens")], "the model's summary was cut off at its output limit"),
        ([stop("end_turn")], "the model's answer was empty, so nothing changed"),
        ([text("no"), stop("refusal")], "the model declined to summarise the conversation"),
    ],
)
async def test_a_step_that_did_not_answer_gives_no_summary_and_says_why(step: list[Json], why: str) -> None:
    with pytest.raises(Unsummarised, match=re.escape(why)):
        await summarise(Scripted(step), asked(CONVERSATION), [PYTHON], 5)


async def test_a_summary_not_written_in_time_closes_the_step_and_says_so() -> None:
    """A command can't be interrupted, so the step has `timeout` seconds; then it is closed, so
    its provider stops what it runs."""
    model = Scripted([text("x holds")], hang=True)
    with pytest.raises(Unsummarised, match=r"no summary within 0\.05 seconds, so nothing changed"):
        await asyncio.wait_for(summarise(model, asked(CONVERSATION), [PYTHON], 0.05), 5)
    assert model.closed


async def test_a_model_failure_is_said_for_the_person_and_a_bug_is_not_hidden() -> None:
    with pytest.raises(Unsummarised, match=r"rate limited; wait a minute \(so nothing changed\)"):
        await summarise(Failing(Limited()), asked(CONVERSATION), [PYTHON], 5)
    with pytest.raises(KeyError):
        await summarise(Failing(KeyError("bug")), asked(CONVERSATION), [PYTHON], 5)


async def test_compact_writes_the_new_conversation_and_queues_the_loop_and_transcript_restart(
    tmp_path: Path,
) -> None:
    """The answer is the summary's usage, `cleared`, a note carrying the summary, then
    `restarting` the loop and the transcript; the kernel is not restarted. The file holds the
    new conversation, the old one is its `.bak`, and the restart waits for the row's own work."""
    path = _session(tmp_path)
    old = path.read_bytes()
    loader, jobs = Loader(str(path)), asyncio.Queue[Job]()
    model = Scripted([text("x holds 42; next, write it to answer.txt"), USAGE, stop("end_turn")])
    said = await compact_conversation(
        "", model=model, kernel=Tool(), loader=loader, config=CompactConfig(), jobs=jobs
    )
    summary = "x holds 42; next, write it to answer.txt"
    assert said == [
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
    assert loader.batches == []  # queued, not run in the caller's task
    await _drain(jobs)
    assert loader.batches == [("loop", "transcript")]  # together, and never the kernel


@pytest.mark.parametrize(
    ("setup", "said"),
    [
        (lambda loader, path: loader.rows.pop("transcript"), "no 'transcript' row is running"),
        (
            lambda loader, path: loader.composed.__setitem__(1, Entry("transcript", "agent:transcript")),
            "the 'transcript' row keeps the conversation in memory, not in a file",
        ),
        (lambda loader, path: path.write_text(json.dumps(CONVERSATION[0]) + "\n"), "nothing to compact"),
    ],
)
async def test_compact_with_nothing_to_compact_says_so_and_asks_nothing(
    tmp_path: Path, setup: Callable[[Loader, Path], object], said: str
) -> None:
    path = _session(tmp_path)
    loader, jobs, model = Loader(str(path)), asyncio.Queue[Job](), Scripted()
    setup(loader, path)
    answer = await compact_conversation(
        "", model=model, kernel=Tool(), loader=loader, config=CompactConfig(), jobs=jobs
    )
    assert isinstance(answer, str) and answer.startswith(said)
    assert model.requests == [] and jobs.empty() and not Path(f"{path}.bak").exists()


async def test_compact_without_a_summary_changes_nothing(tmp_path: Path) -> None:
    path = _session(tmp_path)
    old = path.read_bytes()
    loader, jobs = Loader(str(path)), asyncio.Queue[Job]()
    with pytest.raises(Unsummarised, match="called python"):
        await compact_conversation(
            "",
            model=Scripted(
                [{"type": "tool_call", "id": "c", "name": "python", "input": {}}, stop("tool_use")]
            ),
            kernel=Tool(),
            loader=loader,
            config=CompactConfig(),
            jobs=jobs,
        )
    assert path.read_bytes() == old and jobs.empty() and not Path(f"{path}.bak").exists()


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


async def test_the_compact_row_registers_compact_and_restarts_as_its_own_work(tmp_path: Path) -> None:
    """It depends on the model, the kernel's spec, the loader and `commands`, never on the loop
    or the transcript, which it restarts: the restart would reload it, cancelling its own work."""
    assert resolve("agent:compact").inject == {"model", "kernel", "loader", "commands"}
    path = _session(tmp_path)
    loader, commands = Loader(str(path)), Registry()
    model = Scripted([text("x holds 42"), stop("end_turn")])

    @component(provides=("model", "kernel", "loader", "commands"))
    async def values() -> Effects:
        yield bind("model", model)
        yield bind("kernel", Tool())
        yield bind("loader", loader)
        yield bind("commands", commands)

    rt = Runtime()
    rt.mount(values, id="values")
    row = rt.mount(compact, id="compact", config=CompactConfig(timeout=5))
    await rt.settle()
    spec, run = commands.commands["compact"]
    assert spec["usage"] == "[WHAT TO KEEP]"
    said = await run("")
    assert said[-1] == {"type": "restarting", "rows": ["loop", "transcript"]}
    await asyncio.sleep(0.01)
    assert loader.batches == [("loop", "transcript")]  # the row's own background work ran it
    await row.retire()
    await rt.settle()
    assert commands.commands == {}
    await rt.shutdown()
