"""The model over a fake Claude Code session (`models_cordis_plugin.claude_code.testing`): one step
per call, the parked calls, stops, divergence and rebuilds; no process, no network.

The requests are shaped as `agent:loop` builds them (a system message, then its transcript
entries), and the fake calls the declared tools over the MCP protocol with the tool_use id in
`_meta`, as Claude Code does. The credential is a stand-in in a temporary file."""

import asyncio
import json
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin.claude_code import (
    CONTINUE,
    TOKEN_VARIABLE,
    ClaudeCodeConfig,
    ClaudeCodeError,
    ClaudeCodeModel,
    failure_of,
    project_dir,
)
from models_cordis_plugin.claude_code.testing import FakeClaudeCode, FakeStep

_SPEC = {
    "name": "python",
    "description": "Run a cell.",
    "parameters": {"type": "object", "properties": {"code": {"type": "string"}}},
}
_SYSTEM = {"role": "system", "content": "You are a test."}
_STOPPED = "[the person stopped this reply here]"


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _call(call_id: str, code: str = "1+1", name: str = "mcp__bh__python") -> dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": name, "input": {"code": code}}


class _Harness:
    """A model whose sessions are fakes, each over the next scripted steps."""

    def __init__(self, tmp_path: Path, *scripts: list[FakeStep], hold: asyncio.Event | None = None) -> None:
        env_file = tmp_path / "local.env"
        env_file.write_text(f"{TOKEN_VARIABLE}=sentinel-not-a-real-token\n")
        self.state = tmp_path / "state"
        self.cwd = str(tmp_path / "work")
        self.config = ClaudeCodeConfig(state=str(self.state), env_file=str(env_file), cwd=self.cwd)
        self.scripts = list(scripts)
        self.fakes: list[FakeClaudeCode] = []
        self.hold = hold
        self.model = ClaudeCodeModel(self.config, self.open)

    def open(self, options: Any) -> FakeClaudeCode:
        fake = FakeClaudeCode(options, self.scripts.pop(0) if self.scripts else [], hold_calls=self.hold)
        self.fakes.append(fake)
        return fake

    async def step(
        self, rest: Sequence[Mapping[str, Any]], system: Mapping[str, Any] = _SYSTEM
    ) -> list[dict[str, Any]]:
        return [dict(c) async for c in self.model.complete([system, *rest], [_SPEC])]

    def saved(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads((self.state / "state.json").read_text())
        return loaded


def _said(chunks: Sequence[Mapping[str, Any]]) -> str:
    return "".join(c["text"] for c in chunks if c["type"] == "text")


def _entry(chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The loop's transcript entry for an act or answered step (agent:loop's `_Turn.entry`)."""
    calls = [
        {"id": c["id"], "name": c["name"], "input": c["input"]} for c in chunks if c["type"] == "tool_call"
    ]
    entry: dict[str, Any] = {"role": "assistant", "content": _said(chunks)}
    if calls:
        entry["tool_calls"] = calls
    entry["provider"] = chunks[-1]["message"]
    return entry


async def test_an_answer_is_one_query_and_claude_code_is_started_locked_down(tmp_path: Path) -> None:
    h = _Harness(tmp_path, [FakeStep([_text("Hello there")])])
    chunks = await h.step([{"role": "user", "content": "hi"}])
    assert _said(chunks) == "Hello there"
    assert {"type": "stop", "reason": "end_turn"} in chunks and chunks[-1]["type"] == "message"
    (fake,) = h.fakes
    assert fake.asked == ["hi"] and fake.interrupts == 0
    options = fake.options
    assert options.system_prompt == "You are a test."
    assert options.tools == [] and options.setting_sources == [] and options.strict_mcp_config
    assert options.include_partial_messages and options.model == "sonnet"
    assert str(options.cli_path).endswith("claude-code-detached")
    assert options.env[TOKEN_VARIABLE] == "sentinel-not-a-real-token"
    assert options.env["CLAUDE_CONFIG_DIR"] == str(h.state / "config")
    assert not any(key.startswith("ANTHROPIC_") for key in options.env)
    assert h.saved()["held"]["ended"] == "clean" and h.saved()["session"] == "fake-session"
    await h.model.close()
    assert fake.disconnected


async def test_a_tool_step_parks_its_call_until_the_next_request_brings_the_result(tmp_path: Path) -> None:
    h = _Harness(
        tmp_path,
        [FakeStep([_text("Let me run it."), _call("t1")], stop="tool_use"), FakeStep([_text("It is 2.")])],
    )
    asked = [{"role": "user", "content": "what is 1+1"}]
    first = await h.step(asked)
    assert [c for c in first if c["type"] == "tool_call"] == [
        {"type": "tool_call", "id": "t1", "name": "python", "input": {"code": "1+1"}}
    ]
    assert {"type": "stop", "reason": "tool_use"} in first
    rest = [*asked, _entry(first), {"role": "tool", "content": "2", "call_id": "t1"}]
    second = await h.step(rest)
    assert _said(second) == "It is 2."
    (fake,) = h.fakes  # one process, one query
    assert fake.asked == ["what is 1+1"] and fake.results == {"t1": "2"} and fake.interrupts == 0


async def test_a_result_that_arrives_before_its_call_waits_for_it(tmp_path: Path) -> None:
    hold = asyncio.Event()
    h = _Harness(tmp_path, [FakeStep([_call("t1")], stop="tool_use"), FakeStep([_text("done")])], hold=hold)
    asked = [{"role": "user", "content": "go"}]
    first = await h.step(asked)
    release = asyncio.get_running_loop().call_later(0.05, hold.set)  # Claude Code calls late
    second = await h.step([*asked, _entry(first), {"role": "tool", "content": "early", "call_id": "t1"}])
    release.cancel()
    assert _said(second) == "done" and h.fakes[0].results == {"t1": "early"}


async def test_a_line_typed_after_a_stop_mid_call_is_pushed_before_the_result(tmp_path: Path) -> None:
    h = _Harness(tmp_path, [FakeStep([_call("t1")], stop="tool_use"), FakeStep([_text("ok, stopped")])])
    asked = [{"role": "user", "content": "go"}]
    first = await h.step(asked)
    interrupted = {"role": "tool", "content": "interrupted: stopped", "call_id": "t1"}
    second = await h.step([*asked, _entry(first), interrupted, {"role": "user", "content": "never mind"}])
    assert _said(second) == "ok, stopped"
    fake = h.fakes[0]
    (steer,) = fake.asked[1]
    assert steer["priority"] == "next" and steer["message"] == {"role": "user", "content": "never mind"}
    assert fake.results == {"t1": "interrupted: stopped"}


async def test_closing_a_step_mid_stream_interrupts_claude_code_and_the_next_line_needs_no_rebuild(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path, [FakeStep([_text("Once upon a time")])], [FakeStep([_text("sure")])])
    asked = [{"role": "user", "content": "story"}]
    said = []
    stream = h.model.complete([_SYSTEM, *asked], [_SPEC])
    async for chunk in stream:
        if chunk["type"] == "text":
            said.append(chunk["text"])
            break
    await stream.aclose()
    fake = h.fakes[0]
    assert fake.interrupts == 1 and h.saved()["held"]["ended"] == "stopped"
    fake.steps.append(FakeStep([_text("sure")]))
    stopped = {"role": "assistant", "content": f"{''.join(said)}\n\n{_STOPPED}"}
    after = await h.step([*asked, stopped, {"role": "user", "content": "something else"}])
    assert _said(after) == "sure" and len(h.fakes) == 1 and fake.asked[-1] == "something else"


async def test_a_cancelled_step_interrupts_and_the_next_step_still_reads_the_stream(tmp_path: Path) -> None:
    """A Ctrl-C cancels the reply's task mid-await (chat's `_interruptible`), inside this
    model's read of Claude Code's stream, not only at a yield; the loop then closes it."""
    h = _Harness(tmp_path, [FakeStep([_text("Once upon a time")], stall_after=4)])
    asked = [{"role": "user", "content": "story"}]
    first_text = asyncio.Event()

    async def read() -> None:
        stream = h.model.complete([_SYSTEM, *asked], [_SPEC])
        try:
            async for chunk in stream:
                if chunk["type"] == "text":
                    first_text.set()
        finally:
            await stream.aclose()  # as agent:loop does

    task = asyncio.create_task(read())
    await first_text.wait()
    await asyncio.sleep(0.01)  # the model is now waiting on the stalled stream
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    fake = h.fakes[0]
    assert fake.interrupts == 1 and h.saved()["held"]["ended"] == "stopped"
    fake.steps.append(FakeStep([_text("fine")]))
    stopped = {"role": "assistant", "content": f"Once upon a time\n\n{_STOPPED}"}
    after = await h.step([*asked, stopped, {"role": "user", "content": "again"}])
    assert _said(after) == "fine" and len(h.fakes) == 1


@pytest.mark.parametrize("stop", ["end_turn", "max_tokens"])
async def test_closing_a_step_on_its_last_chunks_leaves_the_idle_claude_code_alone(
    tmp_path: Path, stop: str
) -> None:
    """The loop yields the step's final `usage` up to the screen; a Ctrl-C there closes this
    model after an answered or cut step has settled. Nothing is running, so nothing is
    interrupted, and the loop's `[stopped]` entry continues the same process (a tool step closed
    there is interrupted and rebuilt instead)."""
    h = _Harness(tmp_path, [FakeStep([_text("All done")], stop=stop)])
    asked = [{"role": "user", "content": "go"}]
    said: list[str] = []
    stream = h.model.complete([_SYSTEM, *asked], [_SPEC])
    async for chunk in stream:
        if chunk["type"] == "text":
            said.append(chunk["text"])
        elif chunk["type"] == "usage" and said:
            break  # where agent:loop sits when the person stops the reply
    fake = h.fakes[0]
    interrupted = fake.interrupts
    started = time.monotonic()
    await stream.aclose()
    assert time.monotonic() - started < 1.0
    assert fake.interrupts == interrupted and not fake.disconnected
    assert h.saved()["held"]["ended"] == "stopped"
    fake.steps.append(FakeStep([_text("next")]))
    stopped = {"role": "assistant", "content": f"{''.join(said)}\n\n{_STOPPED}"}
    after = await h.step([*asked, stopped, {"role": "user", "content": "and?"}])
    assert _said(after) == "next" and len(h.fakes) == 1 and fake.asked[-1] == "and?"


async def test_closing_a_tool_step_on_its_last_chunks_interrupts_claude_code_and_then_rebuilds(
    tmp_path: Path,
) -> None:
    """A Ctrl-C on a tool step's final chunks: the loop records the step as stopped and never
    answers its calls, so Claude Code is interrupted at once rather than left parked on them
    until the next request."""
    h = _Harness(tmp_path, [FakeStep([_text("Let me run it."), _call("t1")], stop="tool_use")])
    asked = [{"role": "user", "content": "go"}]
    said: list[str] = []
    stream = h.model.complete([_SYSTEM, *asked], [_SPEC])
    async for chunk in stream:
        if chunk["type"] == "text":
            said.append(chunk["text"])
        elif chunk["type"] == "usage" and said:
            break
    fake = h.fakes[0]
    await _parked(h)
    await stream.aclose()
    assert fake.interrupts == 1 and not h.model.parked and "t1" not in fake.results
    assert h.saved()["held"]["ended"] == "failed"
    h.scripts.append([FakeStep([_text("next")])])
    stopped = {"role": "assistant", "content": f"{''.join(said)}\n\n{_STOPPED}"}
    after = await h.step([*asked, stopped, {"role": "user", "content": "and?"}])
    assert _said(after) == "next" and len(h.fakes) == 2 and h.fakes[1].asked == ["and?"]


async def _parked(h: _Harness) -> None:
    for _ in range(200):
        if h.model.parked:
            return
        await asyncio.sleep(0.01)
    pytest.fail("the call never parked")


async def test_a_cleared_conversation_while_a_call_is_parked_answers_it_and_starts_afresh(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path, [FakeStep([_call("t1")], stop="tool_use")], [FakeStep([_text("fresh")])])
    await h.step([{"role": "user", "content": "go"}])
    await _parked(h)
    after = await h.step([{"role": "user", "content": "b"}])  # /clear mid-approval
    old, new = h.fakes
    assert not h.model.parked and old.interrupts >= 1 and old.disconnected
    assert _said(after) == "fresh" and new.options.resume is None and new.asked == ["b"]


async def test_results_that_are_not_the_parked_call_s_rebuild_the_session_and_resume_it(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path, [FakeStep([_call("t1")], stop="tool_use")], [FakeStep([_text("carried on")])])
    asked = [{"role": "user", "content": "go"}]
    first = await h.step(asked)
    await _parked(h)
    rest = [*asked, _entry(first), {"role": "tool", "content": "elsewhere", "call_id": "t2"}]
    after = await h.step(rest)
    old, new = h.fakes
    assert not h.model.parked and old.interrupts >= 1 and old.disconnected
    assert _said(after) == "carried on" and new.options.resume is not None
    where = project_dir(h.state / "config", os.path.realpath(h.cwd))
    assert where is not None
    records = [json.loads(line) for line in (where / f"{new.options.resume}.jsonl").read_text().splitlines()]
    assert [r["type"] for r in records] == ["user", "assistant", "user"]
    assert records[-1]["message"]["content"][0]["tool_use_id"] == "t2"


async def test_a_conversation_that_cannot_be_written_for_claude_code_says_so_and_starts_nothing(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path, [FakeStep([_text("hello")])])
    deep = tmp_path.joinpath(*["a-rather-long-directory-name"] * 8)
    h.config = ClaudeCodeConfig(state=h.config.state, env_file=h.config.env_file, cwd=str(deep))
    h.model = ClaudeCodeModel(h.config, h.open)
    history = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "what did I say?"},
    ]
    with pytest.raises(ClaudeCodeError) as raised:
        await h.step(history)
    assert raised.value.kind == "path_too_long" and "shorter path" in raised.value.message
    assert h.fakes == []  # never a fresh conversation that silently lost the transcript
    cleared = await h.step([{"role": "user", "content": "hi"}])  # /clear, as the error says
    assert _said(cleared) == "hello" and h.fakes[0].options.resume is None


async def test_a_truncated_step_is_interrupted_so_the_loop_s_nudge_decides(tmp_path: Path) -> None:
    h = _Harness(tmp_path, [FakeStep([_text("Once upon")], stop="max_tokens")])
    asked = [{"role": "user", "content": "story"}]
    first = await h.step(asked)
    assert {"type": "stop", "reason": "max_tokens"} in first
    fake = h.fakes[0]
    assert fake.interrupts == 1 and h.saved()["held"]["ended"] == "cut"
    fake.steps.append(FakeStep([_text("The end.")]))
    feedback = {
        "role": "user",
        "content": "Your last message hit the output token limit...",
        "feedback": "truncated",
    }
    second = await h.step([*asked, {"role": "assistant", "content": "Once upon"}, feedback])
    assert _said(second) == "The end." and len(h.fakes) == 1 and fake.asked[-1] == feedback["content"]


async def test_a_new_conversation_starts_a_fresh_claude_code(tmp_path: Path) -> None:
    h = _Harness(tmp_path, [FakeStep([_text("one")])], [FakeStep([_text("two")])])
    first = await h.step([{"role": "user", "content": "a"}])
    await h.step([{"role": "user", "content": "b"}])  # /clear: a transcript that is not the one held
    old, new = h.fakes
    assert _said(first) == "one" and old.disconnected and new.options.resume is None and new.asked == ["b"]


async def test_a_conversation_claude_code_never_saw_is_written_as_a_session_and_resumed(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path, [FakeStep([_text("you said a")])])
    history = [
        {"role": "user", "content": "a"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "old1", "name": "python", "input": {}}],
            "provider": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "old1", "name": "python", "input": {}}],
            },
        },
        {"role": "tool", "content": "r", "call_id": "old1"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "what did I say?"},
    ]
    await h.step(history)
    (fake,) = h.fakes
    resume = fake.options.resume
    assert resume is not None and fake.asked == ["what did I say?"]
    where = project_dir(h.state / "config", os.path.realpath(h.cwd))
    assert where is not None
    records = [json.loads(line) for line in (where / f"{resume}.jsonl").read_text().splitlines()]
    assert [r["type"] for r in records] == ["user", "assistant", "user", "assistant"]
    assert records[1]["message"]["content"][0]["name"] == "mcp__bh__python"


async def test_a_changed_system_prompt_restarts_claude_code_on_its_own_session(tmp_path: Path) -> None:
    h = _Harness(tmp_path, [FakeStep([_text("one")])], [FakeStep([_text("two")])])
    asked = [{"role": "user", "content": "a"}]
    first = await h.step(asked)
    kept = project_dir(h.state / "config", os.path.realpath(h.cwd))
    assert kept is not None
    kept.mkdir(parents=True)
    (kept / "fake-session.jsonl").write_text("{}\n")  # what Claude Code wrote
    moved = {"role": "system", "content": "You are a test. Git branch: other"}
    second = await h.step([*asked, _entry(first), {"role": "user", "content": "b"}], system=moved)
    old, new = h.fakes
    assert _said(second) == "two" and old.disconnected
    assert new.options.resume == "fake-session" and new.options.system_prompt == moved["content"]
    assert new.asked == ["b"]


@pytest.mark.parametrize("declared_too", [False, True], ids=["only-foreign", "with-a-declared-call"])
async def test_a_step_built_on_a_call_claude_code_answered_itself_never_reaches_the_loop(
    tmp_path: Path, declared_too: bool
) -> None:
    """A tool the permission callback denies never reaches the server: Claude Code answers it
    and starts the next step on its own answer, before (or instead of) the loop's results. That
    step ("hm") is dropped unseen, and Claude Code is rebuilt from the loop's transcript, with
    the loop's own result for the call, and asked to carry on."""
    calls = [_call("t9", name="mcp__gmail__send"), *([_call("t1")] if declared_too else [])]
    h = _Harness(
        tmp_path,
        [FakeStep(calls, stop="tool_use"), FakeStep([_text("hm")])],
        [FakeStep([_text("fresh")])],
    )
    asked = [{"role": "user", "content": "go"}]
    first = await h.step(asked)
    results = [{"role": "tool", "content": "gmail__send is not a tool here", "call_id": "t9"}]
    if declared_too:
        await _parked(h)
        results.append({"role": "tool", "content": "2", "call_id": "t1"})
    after = await h.step([*asked, _entry(first), *results])
    old, new = h.fakes
    assert _said(after) == "fresh" and "hm" not in _said(after)
    assert old.interrupts >= 1 and old.disconnected and not h.model.parked
    assert new.options.resume is not None and new.asked == [CONTINUE]
    where = project_dir(h.state / "config", os.path.realpath(h.cwd))
    assert where is not None
    rebuilt = (where / f"{new.options.resume}.jsonl").read_text()
    assert "gmail__send is not a tool here" in rebuilt  # the loop's result, not Claude Code's
    assert "not one of bh-02's tools" not in rebuilt
    assert h.saved()["held"]["ended"] == "clean"


async def test_closing_with_a_call_parked_answers_it_and_the_saved_state_asks_for_a_rebuild(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path, [FakeStep([_call("t1")], stop="tool_use")])
    await h.step([{"role": "user", "content": "go"}])
    fake = h.fakes[0]
    for _ in range(100):
        if h.model.parked:
            break
        await asyncio.sleep(0.01)
    await h.model.close()
    assert not h.model.parked and fake.disconnected  # answered, not left waiting
    assert fake.interrupts == 1  # before the answer, so Claude Code doesn't carry on with it
    assert h.saved()["held"]["ended"] == "failed"


async def test_a_step_claude_code_reports_failed_is_a_recoverable_error_and_then_a_rebuild(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path, [FakeStep([], error="rate_limit")], [FakeStep([_text("back")])])
    asked = [{"role": "user", "content": "go"}]
    with pytest.raises(ClaudeCodeError) as raised:
        await h.step(asked)
    assert raised.value.kind == "rate_limit" and "API Error: rate_limit" in raised.value.message
    failed = {"role": "assistant", "content": "[this reply failed here; the person saw the error]"}
    again = await h.step([*asked, failed, {"role": "user", "content": "go"}])
    assert _said(again) == "back" and len(h.fakes) == 2 and h.fakes[1].options.resume is not None


async def test_a_stream_claude_code_restarts_mid_step_is_a_recoverable_error_not_one_merged_step(
    tmp_path: Path,
) -> None:
    """A second `message_start` before the step's `message_stop` is Claude Code retrying the
    stream: its halves are never folded into one step, and the next line rebuilds."""
    h = _Harness(
        tmp_path, [FakeStep([_text("half an answer")], restart_after=3)], [FakeStep([_text("back")])]
    )
    asked = [{"role": "user", "content": "go"}]
    with pytest.raises(ClaudeCodeError) as raised:
        await h.step(asked)
    assert raised.value.kind == "stream_retried" and "Send the message again" in raised.value.message
    failed = {"role": "assistant", "content": "[this reply failed here; the person saw the error]"}
    again = await h.step([*asked, failed, {"role": "user", "content": "go"}])
    assert _said(again) == "back" and len(h.fakes) == 2


_THOUGHT = {"type": "thinking", "thinking": "they want a greeting", "signature": "sig"}


@pytest.mark.parametrize("streamed", [0, 1], ids=["nothing-streamed", "message-start-streamed"])
async def test_a_step_claude_code_falls_back_to_a_non_streamed_request_for_still_completes(
    tmp_path: Path, streamed: int
) -> None:
    """Claude Code gives up on a stream that fails before a block completes and asks again
    without streaming: the step comes as one whole `AssistantMessage` (a new id, its stop reason
    set) and no stream events, then the result. It was the first reply after a /clear that
    failed so, live, as "Claude couldn't finish the step" (task-0020); it is folded as the step."""
    whole = FakeStep([_THOUGHT, _text("Hello.")], fallback_after=streamed)
    h = _Harness(tmp_path, [FakeStep([_text("one")])], [whole, FakeStep([_text("still here")])])
    first = await h.step([{"role": "user", "content": "a"}])
    cleared = [{"role": "user", "content": "Say hello."}]  # /clear: a new Claude Code
    chunks = await h.step(cleared)
    assert _said(first) == "one" and _said(chunks) == "Hello."
    assert {"type": "thinking", "text": "they want a greeting"} in chunks
    assert {"type": "stop", "reason": "end_turn"} in chunks
    assert chunks[-1] == {
        "type": "message",
        "message": {"role": "assistant", "content": [_THOUGHT, _text("Hello.")]},
    }
    used = [c for c in chunks if c["type"] == "usage"]
    assert sum(u["input_tokens"] for u in used) == 100 and sum(u["output_tokens"] for u in used) == 10
    assert "partial" not in used[-1]
    # the conversation carries on in the same Claude Code: the step is what it holds
    again = await h.step([*cleared, _entry(chunks), {"role": "user", "content": "Still there?"}])
    assert _said(again) == "still here"
    old, new = h.fakes
    assert new.asked == ["Say hello.", "Still there?"] and new.interrupts == 0 and not new.disconnected


async def test_a_tool_step_that_comes_whole_parks_its_call_and_takes_the_result(tmp_path: Path) -> None:
    h = _Harness(
        tmp_path,
        [
            FakeStep([_text("Let me run it."), _call("t1")], stop="tool_use", fallback_after=0),
            FakeStep([_text("It is 2.")]),
        ],
    )
    asked = [{"role": "user", "content": "what is 1+1"}]
    first = await h.step(asked)
    assert [c for c in first if c["type"] == "tool_call"] == [
        {"type": "tool_call", "id": "t1", "name": "python", "input": {"code": "1+1"}}
    ]
    assert {"type": "stop", "reason": "tool_use"} in first
    second = await h.step([*asked, _entry(first), {"role": "tool", "content": "2", "call_id": "t1"}])
    assert _said(second) == "It is 2."
    (fake,) = h.fakes
    assert fake.results == {"t1": "2"} and fake.interrupts == 0


async def test_a_step_that_comes_whole_after_part_of_it_streamed_is_not_said_twice(tmp_path: Path) -> None:
    """Text already streamed can't be taken back, so a whole message after it is the retried
    stream's error (the next line rebuilds), never the reply said twice."""
    h = _Harness(tmp_path, [FakeStep([_text("Hello there")], fallback_after=3)], [FakeStep([_text("back")])])
    asked = [{"role": "user", "content": "go"}]
    with pytest.raises(ClaudeCodeError) as raised:
        await h.step(asked)
    assert raised.value.kind == "stream_retried"
    failed = {"role": "assistant", "content": "[this reply failed here; the person saw the error]"}
    again = await h.step([*asked, failed, {"role": "user", "content": "go"}])
    assert _said(again) == "back" and len(h.fakes) == 2


@pytest.mark.parametrize("after", [5, 3], ids=["thinking-done", "thinking-open"])
async def test_a_stream_claude_code_retries_after_only_thinking_carries_on_to_the_reply(
    tmp_path: Path, after: int
) -> None:
    """A stream that stalls or drops after only thinking is closed by Claude Code where it is (a
    `message_stop` with no `message_delta`, so no stop reason) and streamed again (task-0021):
    that close is not the step's end, and the retried stream's reply is the step."""
    h = _Harness(
        tmp_path, [FakeStep([_THOUGHT, _text("Hello.")], retry_after=after), FakeStep([_text("more")])]
    )
    asked = [{"role": "user", "content": "Say hello."}]
    chunks = await h.step(asked)
    assert _said(chunks) == "Hello."
    assert {"type": "stop", "reason": "end_turn"} in chunks
    assert chunks[-1] == {
        "type": "message",
        "message": {"role": "assistant", "content": [_THOUGHT, _text("Hello.")]},
    }
    again = await h.step([*asked, _entry(chunks), {"role": "user", "content": "Go on."}])
    assert _said(again) == "more"
    (fake,) = h.fakes  # the same Claude Code, never interrupted
    assert fake.asked == ["Say hello.", "Go on."] and fake.interrupts == 0


async def test_a_stream_claude_code_retries_after_text_was_shown_is_not_said_twice(tmp_path: Path) -> None:
    """Claude Code retries a dropped stream even when text had begun to stream: what was shown
    can't be taken back, so it is the retried stream's error, as a restarted stream is."""
    h = _Harness(
        tmp_path, [FakeStep([_THOUGHT, _text("Hello there")], retry_after=7)], [FakeStep([_text("back")])]
    )
    asked = [{"role": "user", "content": "go"}]
    with pytest.raises(ClaudeCodeError) as raised:
        await h.step(asked)
    assert raised.value.kind == "stream_retried"
    failed = {"role": "assistant", "content": "[this reply failed here; the person saw the error]"}
    again = await h.step([*asked, failed, {"role": "user", "content": "go"}])
    assert _said(again) == "back" and len(h.fakes) == 2


@pytest.mark.parametrize("after", [2, 3], ids=["no-arguments-yet", "half-the-arguments"])
async def test_a_call_cut_off_by_a_stream_claude_code_retries_is_never_shown(
    tmp_path: Path, after: int
) -> None:
    """A dropped connection mid-call: Claude Code closes the call's block (a `content_block_stop`
    with its arguments incomplete), then the message with no stop reason, and streams again
    (task-0027). The cut-off call was never made, so it is not shown: the retried stream's call
    is the step's one call, and it runs."""
    h = _Harness(
        tmp_path,
        [FakeStep([_call("t1")], stop="tool_use", retry_after=after), FakeStep([_text("It is 2.")])],
    )
    asked = [{"role": "user", "content": "what is 1+1"}]
    first = await h.step(asked)
    assert [c for c in first if c["type"] == "tool_call"] == [
        {"type": "tool_call", "id": "t1", "name": "python", "input": {"code": "1+1"}}
    ]
    assert {"type": "stop", "reason": "tool_use"} in first
    second = await h.step([*asked, _entry(first), {"role": "tool", "content": "2", "call_id": "t1"}])
    assert _said(second) == "It is 2."
    (fake,) = h.fakes
    assert fake.results == {"t1": "2"} and fake.interrupts == 0


async def test_a_call_cut_off_by_a_retried_stream_after_text_is_not_shown_before_the_error(
    tmp_path: Path,
) -> None:
    """Text already shown still makes a retried stream the step's error (task-0021), but the
    half-streamed call that the close cut off never reaches the loop before it."""
    h = _Harness(
        tmp_path,
        [FakeStep([_text("Let me run it."), _call("t1")], stop="tool_use", retry_after=7)],
    )
    shown: list[dict[str, Any]] = []
    with pytest.raises(ClaudeCodeError) as raised:
        async for chunk in h.model.complete([_SYSTEM, {"role": "user", "content": "go"}], [_SPEC]):
            shown.append(dict(chunk))
    assert raised.value.kind == "stream_retried"
    assert _said(shown) == "Let me run it." and not [c for c in shown if c["type"] == "tool_call"]


async def test_a_finished_step_whose_call_did_not_decode_shows_it_with_its_error(tmp_path: Path) -> None:
    """A stop reason arrived, so the step is finished: its undecodable call is shown with its
    error for the loop to classify, and Claude Code is interrupted so the loop's nudge decides."""
    bad = {"type": "tool_use", "id": "t1", "name": "mcp__bh__python", "raw": '{"code": '}
    h = _Harness(tmp_path, [FakeStep([_text("Running it."), bad], stop="tool_use")])
    chunks = await h.step([{"role": "user", "content": "go"}])
    (call,) = [c for c in chunks if c["type"] == "tool_call"]
    assert call["id"] == "t1" and call["input"] == {} and "not valid JSON" in call["error"]
    types = [c["type"] for c in chunks]
    assert types.index("tool_call") < types.index("stop") and {"type": "stop", "reason": "tool_use"} in chunks
    (fake,) = h.fakes
    assert fake.interrupts == 1 and h.saved()["held"]["ended"] == "cut"


async def _refused(tmp_path: Path, env_file: Path) -> ClaudeCodeError:
    config = ClaudeCodeConfig(state=str(tmp_path / "s"), env_file=str(env_file))
    model = ClaudeCodeModel(config, lambda options: pytest.fail("nothing starts without a token"))
    with pytest.raises(ClaudeCodeError) as raised:
        async for _ in model.complete([{"role": "user", "content": "hi"}], []):
            pass
    assert raised.value.kind == "authentication_failed" and "claude setup-token" in raised.value.message
    return raised.value


async def test_without_a_credential_the_step_names_the_file_it_read_and_what_is_wrong(
    tmp_path: Path,
) -> None:
    missing = await _refused(tmp_path, tmp_path / "elsewhere.env")
    assert str(tmp_path / "elsewhere.env") in missing.message and "does not exist" in missing.message
    other = tmp_path / "other.env"
    other.write_text("SOMETHING_ELSE=1\n")
    lacking = await _refused(tmp_path, other)
    assert f"{TOKEN_VARIABLE} is not in {other}" in lacking.message
    assert "local.env" not in lacking.message  # the row reads other.env, so that is the file named


def test_a_refused_credential_says_what_to_do_in_bh_02_s_words_only() -> None:
    error = failure_of("authentication_failed", "Not logged in · Please run /login")
    assert error.kind == "authentication_failed" and "claude setup-token" in error.message
    assert "/login" not in error.message and "local.env" in error.message
    limited = failure_of("rate_limit", "API Error: 429")
    assert limited.message.endswith("(API Error: 429)")  # a detail that helps is kept
