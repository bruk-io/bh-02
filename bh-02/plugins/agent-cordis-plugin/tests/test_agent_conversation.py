"""/clear and /compact over fake models, a fake loader and a temporary session's transcript file: the summary
request, the new conversation, the file written in one step, and the restart it queues."""

import asyncio
import json
import os
import re
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import pytest

from agent_cordis_plugin import (
    Answer,
    Clock,
    ConversationConfig,
    FileTranscript,
    LoopModel,
    MemoryTranscript,
    StepRecord,
    ToolBroker,
    TranscriptConfig,
    TranscriptReplaced,
    Unchanged,
    asked,
    clear_conversation,
    compact_conversation,
    conversation,
    kept_in,
    rewrite,
    seeded,
    stamp,
    summarise,
    unrestarted,
)
from agent_cordis_plugin import transcript as transcript_row
from agent_cordis_plugin.testing import Stepped, noon, on
from cordis import Effects, Runtime, bind, component
from cordis.composition import Entry
from cordis.loader import resolve
from cordis_helpers import Job

type Json = Mapping[str, Any]

PYTHON: Json = {"name": "python", "description": "Run Python.", "parameters": {"type": "object"}}

# A conversation as the loop keeps it: the prompt it began with, a dated message, an input and
# its result, the answer, then a later prompt (a change, told as an aside on the next message).
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


class Timed:
    """A `model` that plays one scripted step per call, moving a test clock `after` seconds before
    each chunk (`steps`: `(after, chunk)` pairs), and says what the loop reads of a model: its
    `settings`, and how it wants its tools offered (`tool_changes`)."""

    def __init__(
        self,
        clock: Stepped,
        *steps: Sequence[tuple[float, Json]],
        settings: Json | None = None,
        tool_changes: str = "fixed",
    ) -> None:
        self.clock = clock
        self.steps = list(steps)
        self.settings = settings
        self.tool_changes = tool_changes

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        for after, chunk in self.steps.pop(0):
            self.clock.advance(after)
            yield chunk


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
    clock: Clock | None = None,
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
        clock=clock,
    )


AT = "2026-10-18T03:47:12.345Z"


def _seed(summary: str, keep: str = "") -> list[Json]:
    """A compacted conversation's seed, as /compact writes it, with a step that has only its time."""
    return seeded(summary, keep, {"at": AT})


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
    """The prompt the conversation began with, the conversation (the later prompt told as an
    aside, so not sent), then bh-02 asking for the summary in plain text; what the person asks
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


async def test_the_new_conversation_is_bh_02_s_message_then_the_summary_and_the_loop_starts_it_afresh() -> (
    None
):
    """The seed holds no prompt and no date, so the loop's first message after it keeps the
    prompt as it reads now as the conversation's start (no aside of a change) and tells the date."""
    seed = _seed("  x holds 42.  ")
    assert [m["role"] for m in seed] == ["user", "assistant"] and seed[1]["content"] == "x holds 42."
    assert str(seed[0]["content"]).startswith("(bh-02: this conversation carries on from an earlier one")
    transcript = MemoryTranscript()
    for message in seed:
        transcript.append(message)
    model = Scripted([text("carrying on"), stop("end_turn")])

    class Prompt:
        def text(self) -> str:
            return "the prompt as it reads now"

    class Approved:
        async def approve(self, question: Json) -> Answer:
            return Answer.YES

    async def nothing(input: Json) -> Json:
        return {"content": ""}

    tools = ToolBroker()
    tools.register(PYTHON, nothing)
    loop = LoopModel(model, tools, transcript, Approved(), system=Prompt(), clock=on("2026-10-07"))
    events = [e async for e in loop.reply("next")]
    assert not [e for e in events if e["type"] == "note"]  # nothing told as changed
    ((messages, _),) = model.requests
    assert messages == [
        {"role": "system", "content": "the prompt as it reads now"},
        *seed,
        {
            "role": "user",
            "content": "(Today's date: 2026-10-07.)\n\nnext",
            "today": "2026-10-07",
            "at": stamp(noon("2026-10-07")),
        },
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
    new = _seed("x holds 42")
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
    assert rewrite(str(path), _seed("one")) == f"{path}.bak"
    second = path.read_bytes()
    assert rewrite(str(path), _seed("two")) == f"{path}.bak.2"
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
        rewrite(str(path), _seed("x holds 42"))
    assert path.read_bytes() == old
    assert sorted(p.name for p in tmp_path.iterdir()) == ["transcript.jsonl"]  # no .new, no .bak


async def test_a_summary_is_the_text_of_a_step_that_answered_with_its_usage() -> None:
    model = Scripted(
        [text("x holds "), text("42."), {"type": "thinking", "text": "hm"}, USAGE, stop("end_turn")]
    )
    summary, usage, step = await summarise(model, asked(CONVERSATION), [PYTHON], 5)
    assert (summary, usage) == ("x holds 42.", [USAGE])
    assert step["usage"] == {  # the step's record holds the usage the answer counts
        "input_tokens": 1200,
        "output_tokens": 80,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
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
    """Ctrl-C stops only a reply, so the step has `timeout` seconds; then it is closed, so its
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
    kept = FileTranscript(str(path)).messages
    assert kept == tuple(seeded(summary, "", kept[1]["step"]))
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
            lambda loader, path: path.write_text("".join(json.dumps(m) + "\n" for m in _seed("x"))),
            "nothing to compact: nothing has been said since the last /compact",
        ),
        (
            # a seed is known by its field: this one's wording is not what `seeded` writes
            lambda loader, path: path.write_text(
                "".join(
                    json.dumps(m) + "\n"
                    for m in [
                        {"role": "user", "content": "(carrying on)", "at": AT, "seed": {"keep": "the API"}},
                        {"role": "assistant", "content": "x holds 42"},
                    ]
                )
            ),
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
    path = _session(tmp_path, [*_seed("x holds 42"), {"role": "user", "content": "and y?"}])
    said = await _compact(path, Scripted([text("x holds 42, y unset"), stop("end_turn")]))
    assert said[0] == {"type": "cleared", "compacted": True}
    kept = FileTranscript(str(path)).messages
    assert kept == tuple(seeded("x holds 42, y unset", "", kept[1]["step"]))


async def test_a_conversation_that_only_reads_like_a_seed_is_compacted(tmp_path: Path) -> None:
    """No `seed` field: two messages that are a person's and the model's, whatever the first says."""
    path = _session(
        tmp_path,
        [
            {"role": "user", "content": "carry on from the earlier one", "at": AT},
            {"role": "assistant", "content": "x holds 42"},
        ],
    )
    said = await _compact(path, Scripted([text("x holds 42"), stop("end_turn")]))
    assert said[0] == {"type": "cleared", "compacted": True}


def test_the_seed_says_when_it_began_and_what_to_keep_and_the_summary_carries_the_step() -> None:
    step: StepRecord = {"at": AT, "first_chunk": 0.25, "took": 1.5, "model": "m-1"}
    user, assistant = seeded("  x holds 42.  ", "  the API's endpoints  ", step)
    assert (user["role"], user["at"], user["seed"]) == ("user", AT, {"keep": "the API's endpoints"})
    assert (assistant["role"], assistant["content"], assistant["step"]) == ("assistant", "x holds 42.", step)
    assert seeded("x", "", step)[0]["seed"] == {"keep": ""}  # none asked: the empty string, not absent


_SETTINGS: Json = {"model": "work/opus", "provider": "claude-code", "max_tokens": 4096}
_ANSWERED: list[tuple[float, Json]] = [
    (0.25, text("x holds ")),
    (0.5, text("42.")),
    (0.75, {"type": "usage", "input_tokens": 1200, "output_tokens": 80, "cost_usd": 0.01, "model": "m-1"}),
    (0.0, stop("end_turn")),
]


async def test_compact_keeps_what_the_person_asked_to_keep_and_records_the_summary_step(
    tmp_path: Path,
) -> None:
    """The user entry says when the new conversation began and the text after `/compact`, as the
    summary was asked to keep it; the summary carries its step: when its request was handed over,
    the seconds to its first and last chunk, who answered, what it cost and how it was made."""
    path = _session(tmp_path)
    clock = Stepped()
    model = Timed(clock, _ANSWERED, settings=_SETTINGS)
    await _compact(path, model, "  the API's endpoints ", clock=clock.clock)
    user, assistant = FileTranscript(str(path)).messages
    assert user["at"] == AT and user["seed"] == {"keep": "the API's endpoints"}
    assert assistant["content"] == "x holds 42."
    assert assistant["step"] == {
        "at": AT,
        "first_chunk": 0.25,
        "took": 1.5,
        "model": "m-1",
        "usage": {
            "input_tokens": 1200,
            "output_tokens": 80,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cost_usd": 0.01,
        },
        "settings": {"model": "work/opus", "provider": "claude-code", "max_tokens": 4096},
    }


async def test_the_summary_step_is_recorded_by_the_code_the_loop_records_the_same_step_with(
    tmp_path: Path,
) -> None:
    """The same chunks, at the same times, from a model that wants its tools `listed`: the loop's
    step and /compact's summary step have the same record, down to what the loop leaves out when
    a model says nothing."""
    for settings, mode in [(_SETTINGS, "listed"), (None, "fixed")]:
        looped = Stepped()
        transcript = MemoryTranscript()
        tools = ToolBroker()

        async def python(input: Json) -> Json:
            return {"content": ""}

        tools.register(PYTHON, python)
        loop = LoopModel(
            Timed(looped, _ANSWERED, settings=settings, tool_changes=mode),
            tools,
            transcript,
            _Approved(),
            clock=looped.clock,
        )
        assert [e["type"] async for e in loop.reply("find x")][-1] == "stop"
        (answer,) = [m for m in transcript.messages if m["role"] == "assistant"]

        path = _session(tmp_path)
        compacting = Stepped()
        await _compact(
            path, Timed(compacting, _ANSWERED, settings=settings, tool_changes=mode), clock=compacting.clock
        )
        _, summary = FileTranscript(str(path)).messages
        assert summary["step"] == answer["step"] and ("tool_changes" in summary["step"]) is (mode == "listed")
        assert ("settings" in summary["step"]) is (settings is not None)


@pytest.mark.parametrize(
    ("then", "repeated"),
    [
        (_SETTINGS, False),  # the settings the seed recorded stand: the loop does not repeat them
        ({**_SETTINGS, "model": "work/haiku"}, True),  # the model changed since: the loop records them
    ],
)
async def test_the_loop_repeats_the_model_s_settings_after_a_compaction_only_when_they_changed(
    tmp_path: Path, then: Json, repeated: bool
) -> None:
    """The summary is the new conversation's first step, so it records the settings (whatever the
    old conversation recorded) and the loop's first step after it compares with those."""
    path = _session(tmp_path)
    clock = Stepped()
    await _compact(path, Timed(clock, _ANSWERED, settings=_SETTINGS), clock=clock.clock)
    tools = ToolBroker()

    async def python(input: Json) -> Json:
        return {"content": ""}

    tools.register(PYTHON, python)
    async with FileTranscript(str(path)) as transcript:
        loop = LoopModel(
            Timed(clock, _ANSWERED, settings=then), tools, transcript, _Approved(), clock=clock.clock
        )
        assert [e["type"] async for e in loop.reply("next")][-1] == "stop"
        answer = transcript.messages[-1]
    assert answer["role"] == "assistant" and ("settings" in answer["step"]) is repeated


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
    user, summary = FileTranscript(str(path)).messages  # the row's own clock: the real one
    assert user["seed"] == {"keep": ""} and user["at"] == summary["step"]["at"]
    assert user["at"].endswith("Z") and summary["step"]["took"] >= 0
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


class _Approved:
    async def approve(self, question: Json) -> Answer:
        return Answer.YES


def _slow_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every write to a file takes its time, on the thread that makes it: when a reply has ended
    the thread is still behind the loop, unless the reply waited for it."""
    real = os.write

    def slow(fd: int, data: bytes | memoryview) -> int:
        time.sleep(0.05)
        return real(fd, data)

    monkeypatch.setattr(os, "write", slow)


async def _replied(
    transcript: FileTranscript, message: str = "find x", scripted: Scripted | None = None
) -> None:
    """The loop answers `message` over `transcript`: a tool step, then the answer (`scripted`, if
    the caller wants to see what the model was asked)."""

    async def python(input: Json) -> Json:
        return {"content": "42"}

    tools = ToolBroker()
    tools.register(PYTHON, python)
    model = scripted or Scripted(
        [text("let me see"), {"type": "tool_call", "id": "c1", "name": "python", "input": {"code": "x"}}],
        [text("x holds 42")],
    )
    loop = LoopModel(model, tools, transcript, _Approved(), clock=on("2026-10-07"))
    assert [e["type"] async for e in loop.reply(message)][-1] == "stop"


def _entries(path: Path) -> list[Json]:
    return [json.loads(line) for line in path.read_text().splitlines()]


async def test_clear_after_a_reply_keeps_every_entry_of_it_in_the_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A command runs only once the reply before it has ended (the chat row reads its next line
    then), and the loop has flushed the transcript by that time, though the row is still running:
    /clear finds the whole reply in the file it keeps as the `.bak`, the last entry included, and
    does not find the file empty."""
    path = tmp_path / "transcript.jsonl"
    _slow_disk(monkeypatch)
    async with FileTranscript(str(path)) as transcript:
        await _replied(transcript)
        await _clear(Loader(str(path)))
        appended = list(transcript.messages)
    assert [m["role"] for m in appended] == ["tools", "user", "assistant", "tool", "assistant"]
    assert _entries(Path(f"{path}.bak")) == appended
    assert path.read_text() == ""


async def test_compact_after_a_reply_summarises_every_entry_of_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "transcript.jsonl"
    _slow_disk(monkeypatch)
    model = Scripted([text("x holds 42"), stop("end_turn")])
    async with FileTranscript(str(path)) as transcript:
        await _replied(transcript)
        await _compact(path, model)
        appended = list(transcript.messages)
    assert model.requests == [(asked(appended), [PYTHON])]  # the whole reply, its answer included
    assert _entries(Path(f"{path}.bak")) == appended
    kept = FileTranscript(str(path)).messages
    assert kept == tuple(seeded("x holds 42", "", kept[1]["step"]))


@runtime_checkable
class Recoverable(Protocol):
    """What `chat:converse` shows and carries on after (CONTRACTS.md: errors), as the family
    declares it: the chat plugin's own, which this one may not import."""

    kind: str
    message: str


@pytest.mark.parametrize("command", ["clear", "compact"])
@pytest.mark.parametrize("wrote", [True, False], ids=["file held open", "nothing written yet"])
async def test_a_reply_after_a_restart_that_failed_is_refused_naming_the_restart(
    tmp_path: Path, command: str, wrote: bool
) -> None:
    """/clear or /compact replaced the file and its restart failed (the person was told): the
    transcript still mounted is the old conversation's, over the new one's file. A reply's entries
    are refused, as a recoverable failure that names `/restart transcript`: not written to the old
    inode (the descriptor it holds), not written after the new conversation's seed (a transcript
    that had written nothing yet), and not lost without a word. The refusal comes before the
    model is asked, at the first message after the failed restart too (TASK-0152): the model
    sees no request, and the transcript keeps nothing of the message. The restart the message
    names begins the new conversation from the file."""
    path = tmp_path / "transcript.jsonl"
    if not wrote:
        _session(tmp_path)  # a resumed session: the transcript has read the file and written nothing
    loader, jobs = Loader(str(path)), Jobs()
    loader.fails = True
    old = FileTranscript(str(path))
    if wrote:
        await _replied(old, "find the answer")
    if command == "clear":
        await _clear(loader, jobs)
        assert path.read_text() == ""
    else:
        await _compact(path, Scripted([text("x holds 42"), stop("end_turn")]), loader=loader, jobs=jobs)
        assert [m["role"] for m in _entries(path)] == ["user", "assistant"]
    await _drain(jobs)
    assert jobs.told == [
        unrestarted(ConversationConfig(), "LookupError: no row 'transcript'; the rows are loop")
    ]
    new, backup = path.read_bytes(), Path(f"{path}.bak").read_bytes()

    kept, model = old.messages, Scripted([text("an answer from the old conversation")])
    with pytest.raises(TranscriptReplaced) as refused:
        await _replied(old, "forged", model)
    error = refused.value
    assert isinstance(error, Recoverable) and isinstance(error, OSError)  # chat shows it and carries on
    assert error.kind == "transcript_replaced"
    assert str(path) in error.message and "/restart transcript" in error.message
    assert model.requests == []  # refused before the model was asked, not at the step's entry after it
    assert old.messages == kept  # and nothing of the message was kept, not even in memory
    with pytest.raises(TranscriptReplaced, match="/restart transcript"):  # the next message, at once
        old.append({"role": "user", "content": "forged again"})
    with pytest.raises(TranscriptReplaced, match="/restart transcript"):
        await old.flush()
    # neither file took any of it: the new conversation is as the rewrite left it, the old one is
    # the backup as it was kept
    assert path.read_bytes() == new and Path(f"{path}.bak").read_bytes() == backup
    assert b"forged" not in new + backup

    # what /restart transcript does: the row's leaving (it raises what it kept, as a full disk's
    # does, and the restart goes on all the same), then a transcript over the file
    with pytest.raises(TranscriptReplaced):
        async with old:
            pass
    async with FileTranscript(str(path)) as restarted:
        began = len(restarted.messages)
        assert began == (0 if command == "clear" else 2)
        await _replied(restarted, "a fresh question")
    entries = _entries(path)
    assert [m["role"] for m in entries[began:]] == ["tools", "user", "assistant", "tool", "assistant"]
    assert entries[began + 1]["content"].endswith("a fresh question")
    assert b"forged" not in path.read_bytes()


async def test_a_transcript_row_whose_file_was_replaced_restarts_all_the_same(tmp_path: Path) -> None:
    """The remedy the message names has to work: the row's leaving raises what the refusal kept
    (the writer's failure is raised by its close, as a full disk's is), cordis ends the row all the
    same, and the row that takes its place writes to the new file."""
    path = tmp_path / "transcript.jsonl"
    rt = Runtime()
    row = rt.mount(transcript_row, id="transcript", config=TranscriptConfig(path=str(path)))
    await rt.settle()
    old = row.ctx.get("transcript")
    assert isinstance(old, FileTranscript)
    await _replied(old)
    rewrite(str(path), [])  # what /clear does
    with pytest.raises(TranscriptReplaced):
        await _replied(old, "forged")
    await row.retire()  # the restart: the row's leaving closes the transcript, which says why it refuses
    await rt.settle()
    row = rt.mount(transcript_row, id="transcript", config=TranscriptConfig(path=str(path)))
    await rt.settle()
    new = row.ctx.get("transcript")
    assert isinstance(new, FileTranscript) and new is not old and new.messages == ()
    await _replied(new, "a fresh question")
    await rt.shutdown()
    assert [m["role"] for m in _entries(path)] == ["tools", "user", "assistant", "tool", "assistant"]
    assert b"forged" not in path.read_bytes()
