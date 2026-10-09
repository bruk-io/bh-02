"""/clear and /compact over fake models, a fake loader and a temporary session's transcript file: the summary
request, the new conversation, the file written in one step, and the restart it queues."""

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
    ConversationConfig,
    FileTranscript,
    LoopModel,
    MemoryTranscript,
    ToolBroker,
    Unchanged,
    asked,
    clear_conversation,
    compact_conversation,
    conversation,
    kept_in,
    rewrite,
    seeded,
    summarise,
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


class Offered:
    """The `tools` value as /compact needs it: the specs the loop offers."""

    def specs(self) -> list[Json]:
        return [PYTHON]


class Loader:
    """The `loader` value: the rows' states, each row as mounted (`rows`: its `entry`), and
    restarts recorded; `fails` makes a restart raise, as the loader's does for a row gone."""

    def __init__(self, path: str | None) -> None:
        self.states = {rid: "active" for rid in ("loop", "transcript", "python", "chat", "model")}
        self.rows: dict[str, Any] = {
            "loop": Mounted(Entry("loop", "agent:loop")),
            "transcript": Mounted(Entry("transcript", "agent:transcript", {"path": path} if path else {})),
            "python": Mounted(Entry("python", "python:tool")),
        }
        self.batches: list[tuple[str, ...]] = []
        self.fails = False

    def status(self) -> dict[str, str]:
        return dict(self.states)

    async def restart(self, *rids: str) -> None:
        if self.fails:
            raise LookupError("no row 'transcript'; the rows are loop")
        self.batches.append(rids)


@dataclass(frozen=True)
class Mounted:
    """A row as the loader mounted it (cordis.loader's `Live`, `Disabled`, ...): its entry."""

    entry: Entry


class Screen:
    """The `output` value as /compact needs it: what it was shown, and noticed."""

    def __init__(self) -> None:
        self.shown: list[Json] = []
        self.notices: list[str] = []

    async def show(self, events: AsyncIterator[Json]) -> None:
        self.shown += [e async for e in events]

    async def notice(self, message: str) -> None:
        self.notices.append(message)


class Jobs:
    """The `jobs` value as /clear and /compact need it: each restart queued, with what the person
    would be told if it failed; `drain` runs them, as the jobs row would after the answer."""

    def __init__(self) -> None:
        self.queued: list[tuple[Job, Callable[[str], str]]] = []
        self.told: list[str] = []

    def put(self, job: Job, failed: Callable[[str], str]) -> None:
        self.queued.append((job, failed))

    def empty(self) -> bool:
        return not self.queued


async def _compact(
    path: Path | None,
    model: Any,
    args: str = "",
    *,
    loader: Loader | None = None,
    screen: Screen | None = None,
    jobs: Jobs | None = None,
) -> Any:
    """`/compact ARGS` over the session's file at `path`, as the conversation row runs it."""
    return await compact_conversation(
        args,
        model=model,
        tools=Offered(),
        loader=loader or Loader(str(path) if path else None),
        output=screen or Screen(),
        config=ConversationConfig(),
        jobs=jobs if jobs is not None else Jobs(),
    )


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


async def _drain(jobs: Jobs) -> None:
    """Run what was queued, one at a time, a failure told as the jobs row tells it."""
    while jobs.queued:
        job, failed = jobs.queued.pop(0)
        try:
            await job()
        except Exception as error:
            jobs.told.append(failed(f"{type(error).__name__}: {error}"))


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

    async def nothing(input: Json) -> Json:
        return {"content": ""}

    tools = ToolBroker()
    tools.register(PYTHON, nothing)
    loop = LoopModel(model, tools, history, Approved(), system=Prompt(), today=lambda: "2026-10-07")
    events = [e async for e in loop.reply("next")]
    assert not [e for e in events if e["type"] == "note"]  # nothing told as changed
    ((messages, _),) = model.requests
    assert messages == [
        {"role": "system", "content": "the prompt as it reads now"},
        *seed,
        {"role": "user", "content": "(Today's date: 2026-10-07.)\n\nnext", "today": "2026-10-07"},
    ]


def test_the_transcript_s_file_is_the_running_agent_transcript_row_s_path() -> None:
    """From the row as the loader mounted it, not the layer files as they read now."""
    row = Mounted(Entry("transcript", "agent:transcript", {"path": "/s/t.jsonl"}))
    assert kept_in("transcript", row, "active") == "/s/t.jsonl"
    with pytest.raises(Unchanged, match="no 'transcript' row is running"):
        kept_in("transcript", None, None)
    with pytest.raises(Unchanged, match="no 'transcript' row is running"):
        kept_in("transcript", row, "disabled")
    other = Mounted(Entry("transcript", "mine:transcript", {"path": "/s/t.db"}))
    with pytest.raises(Unchanged, match="filled by mine:transcript, not agent:transcript"):
        kept_in("transcript", other, "active")
    with pytest.raises(Unchanged, match="keeps the conversation in memory, not in a file"):
        kept_in("transcript", Mounted(Entry("transcript", "agent:transcript")), "active")


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


def test_a_later_rewrite_keeps_every_earlier_backup(tmp_path: Path) -> None:
    """The conversation before the first /compact is never replaced by a later one's."""
    path = _session(tmp_path)
    first = path.read_bytes()
    assert rewrite(str(path), seeded("one")) == f"{path}.bak"
    second = path.read_bytes()
    assert rewrite(str(path), seeded("two")) == f"{path}.bak.2"
    assert Path(f"{path}.bak").read_bytes() == first and Path(f"{path}.bak.2").read_bytes() == second


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
    assert path.read_bytes() == old
    assert sorted(p.name for p in tmp_path.iterdir()) == ["transcript.jsonl"]  # no .new, no .bak


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
        (
            [text("no"), stop("refusal")],
            "the model declined to summarise the conversation, so nothing changed; try /compact "
            "WHAT TO KEEP, naming what matters, or /clear to start afresh without a summary",
        ),
    ],
)
async def test_a_step_that_did_not_answer_gives_no_summary_and_says_why(step: list[Json], why: str) -> None:
    with pytest.raises(Unchanged, match=re.escape(why)) as raised:
        await summarise(Scripted([USAGE, *step]), asked(CONVERSATION), [PYTHON], 5)
    assert raised.value.usage == [USAGE]  # what the step cost still counts


async def test_a_summary_not_written_in_time_closes_the_step_and_says_so() -> None:
    """Ctrl-C stops only a turn, so the step has `timeout` seconds; then it is closed, so its
    provider stops what it runs."""
    model = Scripted([USAGE, text("x holds")], hang=True)
    with pytest.raises(Unchanged, match=r"no summary within 0\.05 seconds, so nothing changed") as raised:
        await asyncio.wait_for(summarise(model, asked(CONVERSATION), [PYTHON], 0.05), 5)
    assert model.closed and raised.value.usage == [USAGE]


async def test_a_summary_step_cancelled_is_closed() -> None:
    """The person leaving cancels the command (`chat:converse`): the step closes, so its
    provider stops, and nothing is said."""
    model = Scripted([text("x holds")], hang=True)
    step = asyncio.create_task(summarise(model, asked(CONVERSATION), [PYTHON], 60))
    await asyncio.sleep(0.01)
    step.cancel()
    with pytest.raises(asyncio.CancelledError):
        await step
    assert model.closed


async def test_a_model_failure_is_said_for_the_person_and_a_bug_is_not_hidden() -> None:
    with pytest.raises(Unchanged, match=r"rate limited; wait a minute \(so nothing changed\)"):
        await summarise(Failing(Limited()), asked(CONVERSATION), [PYTHON], 5)
    with pytest.raises(KeyError):
        await summarise(Failing(KeyError("bug")), asked(CONVERSATION), [PYTHON], 5)


async def test_compact_writes_the_new_conversation_and_queues_the_loop_and_transcript_restart(
    tmp_path: Path,
) -> None:
    """A note says the model is writing the summary as the step begins. The answer is `cleared`
    (`compacted`), the note carrying the summary, what the summary cost (its usage parts as one
    event), then `restarting` the loop and the transcript; the python row is not restarted. The
    file holds the new conversation, the old one is its `.bak`, and the restart waits for the
    row's own work."""
    path = _session(tmp_path)
    old = path.read_bytes()
    loader, jobs, screen = Loader(str(path)), Jobs(), Screen()
    early: Json = {"type": "usage", "input_tokens": 1200, "output_tokens": 0, "partial": True}
    late: Json = {"type": "usage", "input_tokens": 0, "output_tokens": 80, "cost_usd": 0.01}
    summary = "x holds 42; next, write it to answer.txt"
    model = Scripted([early, text(summary), late, stop("end_turn")])
    said = await _compact(path, model, loader=loader, screen=screen, jobs=jobs)
    assert screen.shown == [
        {
            "type": "note",
            "text": "compacting: the model is writing a summary of the conversation, in up to 300 "
            "seconds (the conversation row's `timeout`). Nothing changes until it is written; Ctrl-C "
            "doesn't stop it, leaving bh-02 does.",
        }
    ]
    assert said == [
        {"type": "cleared", "compacted": True},
        {
            "type": "note",
            "text": "the conversation was compacted; a new one begins from the model's summary of it, "
            "below (the Python process and its variables are kept; the old transcript is "
            f"{path}.bak):\n\n{summary}",
        },
        {
            "type": "usage",
            "input_tokens": 1200,
            "output_tokens": 80,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cost_usd": 0.01,
        },
        {"type": "restarting", "rows": ["loop", "transcript"]},
    ]
    assert model.requests == [(asked(CONVERSATION), [PYTHON])]
    assert FileTranscript(str(path)).messages == tuple(seeded(summary))
    assert Path(f"{path}.bak").read_bytes() == old
    assert loader.batches == []  # queued, not run in the caller's task
    await _drain(jobs)
    assert loader.batches == [("loop", "transcript")]  # together, and never the python row


async def test_however_many_usage_parts_a_provider_sends_the_note_comes_right_after_cleared(
    tmp_path: Path,
) -> None:
    """The restart is queued before the chat row shows the answer and may stop it showing the
    rest, so the note's place must not depend on the provider: the answer is four events."""
    path = _session(tmp_path)
    model = Scripted([*[USAGE] * 16, text("x holds 42"), stop("end_turn")])
    said = await _compact(path, model)
    assert [e["type"] for e in said] == ["cleared", "note", "usage", "restarting"]
    assert said[2]["input_tokens"] == 16 * 1200 and "partial" not in said[2]


@pytest.mark.parametrize(
    ("setup", "said"),
    [
        (lambda loader, path: loader.rows.pop("transcript"), "no 'transcript' row is running"),
        (
            lambda loader, path: loader.rows.__setitem__(
                "transcript", Mounted(Entry("transcript", "agent:transcript"))
            ),
            "the 'transcript' row keeps the conversation in memory, not in a file",
        ),
        (lambda loader, path: path.write_text(json.dumps(CONVERSATION[0]) + "\n"), "nothing to compact"),
        (
            lambda loader, path: path.write_text("".join(json.dumps(m) + "\n" for m in seeded("x"))),
            "nothing to compact: nothing has been said since the last /compact",
        ),
        (
            lambda loader, path: path.write_text("{half a line\n"),
            "the conversation in {path} can't be read",
        ),
    ],
)
async def test_compact_with_nothing_to_compact_says_so_and_asks_nothing(
    tmp_path: Path, setup: Callable[[Loader, Path], object], said: str
) -> None:
    path = _session(tmp_path)
    loader, jobs, model, screen = Loader(str(path)), Jobs(), Scripted(), Screen()
    setup(loader, path)
    answer = await _compact(path, model, loader=loader, screen=screen, jobs=jobs)
    assert isinstance(answer, str) and answer.startswith(said.format(path=path))
    assert model.requests == [] and screen.shown == [] and jobs.empty()
    assert not Path(f"{path}.bak").exists()


async def test_a_seed_with_a_message_after_it_compacts_again(tmp_path: Path) -> None:
    """Once something has been said since, the conversation is more than the summary."""
    path = _session(tmp_path, [*seeded("x holds 42"), {"role": "user", "content": "and y?"}])
    said = await _compact(path, Scripted([text("x holds 42, y unset"), stop("end_turn")]))
    assert said[0] == {"type": "cleared", "compacted": True}
    assert FileTranscript(str(path)).messages == tuple(seeded("x holds 42, y unset"))


async def test_compact_without_a_summary_changes_nothing_and_counts_what_it_cost(tmp_path: Path) -> None:
    path = _session(tmp_path)
    old = path.read_bytes()
    jobs = Jobs()
    call = {"type": "tool_call", "id": "c", "name": "python", "input": {}}
    said = await _compact(path, Scripted([USAGE, call, stop("tool_use")]), jobs=jobs)
    assert said == [
        {
            "type": "note",
            "text": "the model called python instead of writing a summary (nothing "
            "ran), so nothing changed; try /compact again",
        },
        {**USAGE, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ]
    said = await _compact(path, Scripted([call, stop("tool_use")]), jobs=jobs)
    assert isinstance(said, str) and said.startswith("the model called python")  # no usage: text
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


async def test_the_conversation_row_registers_clear_and_compact_and_queues_restarts_in_jobs(
    tmp_path: Path,
) -> None:
    """It depends on the model, `tools` (the specs), the loader, `commands`, `output` and `jobs`,
    never on the loop or the transcript, which it restarts. Each restart is queued in `jobs`,
    with what the person is told if it fails: the new conversation is written by then."""
    assert resolve("agent:conversation").inject == {"model", "tools", "loader", "commands", "output", "jobs"}
    path = _session(tmp_path)
    loader, commands, screen, jobs = Loader(str(path)), Registry(), Screen(), Jobs()
    model = Scripted([text("x holds 42"), stop("end_turn")], [text("x holds 42"), stop("end_turn")])

    @component(provides=("model", "tools", "loader", "commands", "output", "jobs"))
    async def values() -> Effects:
        yield bind("model", model)
        yield bind("tools", Offered())
        yield bind("loader", loader)
        yield bind("commands", commands)
        yield bind("output", screen)
        yield bind("jobs", jobs)

    rt = Runtime()
    rt.mount(values, id="values")
    row = rt.mount(conversation, id="conversation", config=ConversationConfig(timeout=5))
    await rt.settle()
    assert sorted(commands.commands) == ["clear", "compact"]
    spec, run = commands.commands["compact"]
    assert spec["usage"] == "[WHAT TO KEEP]"
    said = await run("")
    assert said[-1] == {"type": "restarting", "rows": ["loop", "transcript"]}
    assert loader.batches == []  # queued, not run in the command's task
    await _drain(jobs)
    assert loader.batches == [("loop", "transcript")]
    _, clear = commands.commands["clear"]
    assert (await clear(""))[-1] == {"type": "restarting", "rows": ["loop", "transcript", "python"]}
    await _drain(jobs)
    assert loader.batches[-1] == ("loop", "transcript", "python")
    path.write_text("".join(json.dumps(m) + "\n" for m in CONVERSATION))
    loader.fails = True
    await run("")
    await _drain(jobs)
    assert jobs.told == [
        unrestarted(ConversationConfig(), "LookupError: no row 'transcript'; the rows are loop")
    ]
    assert jobs.told[0].endswith(
        "so the loop may still hold the old one; /rows shows what is running, and /restart "
        "transcript begins the new one"
    )
    await row.retire()
    await rt.settle()
    assert commands.commands == {}
    await rt.shutdown()


async def _clear(loader: Loader, jobs: Jobs | None = None) -> Any:
    return await clear_conversation("", loader=loader, config=ConversationConfig(), jobs=jobs or Jobs())


async def test_clear_writes_an_empty_conversation_keeping_the_old_and_restarts_its_rows(
    tmp_path: Path,
) -> None:
    """/clear is /compact's rewrite with an empty conversation: the old is the `.bak` beside the
    file, never lost, and the loop, the transcript and the python tool restart together."""
    path = _session(tmp_path)
    old = path.read_bytes()
    loader, jobs = Loader(str(path)), Jobs()
    said = await _clear(loader, jobs)
    assert said == [
        {"type": "cleared"},  # not `compacted`: what commands hold for the model is dropped
        {
            "type": "note",
            "text": f"the conversation was cleared (the old one is kept as {path}.bak); starting "
            "afresh: loop, transcript, python",
        },
        {"type": "restarting", "rows": ["loop", "transcript", "python"]},
    ]
    assert path.read_text() == "" and Path(f"{path}.bak").read_bytes() == old
    assert loader.batches == []  # queued, not run in the command's task
    await _drain(jobs)
    assert loader.batches == [("loop", "transcript", "python")]
    path.write_text(old.decode())
    await _clear(loader)
    assert Path(f"{path}.bak.2").read_bytes() == old  # an earlier backup is never replaced


async def test_clear_with_nothing_to_keep_or_no_file_of_its_own_only_restarts(tmp_path: Path) -> None:
    """An empty transcript, one kept in memory, or one another component fills (its file may be
    another shape) is not written: the restart is the new conversation. Rows not running are not
    named."""
    empty = tmp_path / "transcript.jsonl"
    empty.write_text("")
    loader = Loader(str(empty))
    del loader.states["python"]
    said = await _clear(loader)
    assert said[1]["text"] == "the conversation was cleared; starting afresh: loop, transcript"
    assert not Path(f"{empty}.bak").exists()
    in_memory = await _clear(Loader(None))
    assert in_memory[-1] == {"type": "restarting", "rows": ["loop", "transcript", "python"]}
    other = Loader(str(_session(tmp_path)))
    other.rows["transcript"] = Mounted(Entry("transcript", "mine:transcript", {"path": str(tmp_path / "t")}))
    await _clear(other)
    assert not Path(f"{tmp_path / 'transcript.jsonl'}.bak").exists()


async def test_clear_that_can_t_write_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _session(tmp_path)
    old = path.read_bytes()
    os.chmod(tmp_path, 0o500)
    try:
        if os.access(tmp_path, os.W_OK):
            pytest.skip("this user writes a read-only directory (root)")
        jobs = Jobs()
        said = await _clear(Loader(str(path)), jobs)
        assert said.startswith(f"the conversation in {path} could not be cleared (")
        assert jobs.empty() and path.read_bytes() == old
    finally:
        os.chmod(tmp_path, 0o700)
