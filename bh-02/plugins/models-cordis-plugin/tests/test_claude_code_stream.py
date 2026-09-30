"""One step's raw stream events folded into chunks, from the Messages API's wire shapes; no process."""

from models_cordis_plugin.claude_code import Step, cost_of, plain_name, visible
from models_cordis_plugin.claude_code.testing import FakeStep, events_for


def _fold(step: FakeStep) -> tuple[Step, list[dict[str, object]]]:
    folded = Step()
    chunks = [chunk for event in events_for(step) for chunk in folded.take(event)]
    return folded, chunks + folded.finish()


def test_text_streams_as_it_comes_then_usage_stop_and_the_message() -> None:
    folded, chunks = _fold(
        FakeStep([{"type": "text", "text": "Hello there"}], input_tokens=50, output_tokens=7)
    )
    texts = [c["text"] for c in chunks if c["type"] == "text"]
    assert texts == ["Hello", " there"]
    usage = [c for c in chunks if c["type"] == "usage"]
    assert usage[0]["input_tokens"] == 50 and usage[0]["partial"] is True and usage[0]["output_tokens"] == 0
    assert usage[1]["output_tokens"] == 7 and "partial" not in usage[1]
    assert {"type": "stop", "reason": "end_turn"} in chunks
    assert chunks[-1] == {
        "type": "message",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "Hello there"}]},
    }
    assert folded.ended and folded.model == "claude-sonnet-5" and folded.stop == "end_turn"
    assert all("cost_usd" in u for u in usage)  # a model the price table lists


def test_a_tool_call_is_one_chunk_under_the_loop_s_name_and_the_message_keeps_claude_code_s() -> None:
    call = {"type": "tool_use", "id": "toolu_1", "name": "mcp__bh__python", "input": {"code": "print(1)"}}
    folded, chunks = _fold(FakeStep([{"type": "text", "text": "\n\n"}, call], stop="tool_use"))
    assert [c for c in chunks if c["type"] == "tool_call"] == [
        {"type": "tool_call", "id": "toolu_1", "name": "python", "input": {"code": "print(1)"}}
    ]
    assert folded.calls == ["toolu_1"] and not folded.undecodable
    message = chunks[-1]["message"]
    assert message == {"role": "assistant", "content": [call]}  # the blank text block is not replayed
    assert not visible(message)


def test_arguments_that_do_not_decode_are_the_call_s_error() -> None:
    bad = {"type": "tool_use", "id": "toolu_2", "name": "mcp__bh__python", "raw": '{"code": '}
    folded, chunks = _fold(FakeStep([bad], stop="tool_use"))
    (call,) = [c for c in chunks if c["type"] == "tool_call"]
    assert "not valid JSON" in call["error"] and folded.undecodable


def test_a_call_whose_arguments_are_incomplete_is_held_until_the_step_s_end_is_known() -> None:
    """A call block closed with its arguments cut off is not a chunk yet: only a stop reason
    says the step finished with it (Claude Code closes a stream it will retry the same way,
    with no stop reason). A good call is not held, nor is what comes before a held one."""
    good = {"type": "tool_use", "id": "toolu_1", "name": "mcp__bh__python", "input": {"code": "1"}}
    bad = {"type": "tool_use", "id": "toolu_2", "name": "mcp__bh__python", "raw": '{"code": '}
    after = {"type": "text", "text": "and"}
    events = events_for(FakeStep([good, bad, after], stop="tool_use"))
    folded = Step()
    before_end = [
        c
        for e in events
        if e["type"] != "message_delta"
        for c in folded.take(e)
        if e["type"] != "message_stop"
    ]
    assert [c.get("id") for c in before_end if c["type"] == "tool_call"] == ["toolu_1"]
    assert not [c for c in before_end if c["type"] == "text"]  # after the held call: held too
    released = folded.take(events[-2])  # message_delta: a stop reason, so the step is finished
    assert [c["type"] for c in released] == ["tool_call", "text", "text"] and "error" in released[0]
    assert folded.undecodable


def test_a_call_cut_off_by_a_close_with_no_stop_reason_is_never_released() -> None:
    call = {"type": "tool_use", "id": "toolu_1", "name": "mcp__bh__python", "input": {"code": "1+1"}}
    events = events_for(FakeStep([call], stop="tool_use"))
    closed = [*events[:3], {"type": "content_block_stop", "index": 0}, {"type": "message_stop"}]
    folded = Step()
    assert [c for e in closed for c in folded.take(e) if c["type"] != "usage"] == []
    assert folded.ended and folded.stop is None


def test_thinking_streams_and_keeps_its_signature_for_replay() -> None:
    thought = {"type": "thinking", "thinking": "let me see", "signature": "sig=="}
    _, chunks = _fold(FakeStep([thought, {"type": "text", "text": "ok"}]))
    assert {"type": "thinking", "text": "let me see"} in chunks
    assert chunks[-1]["message"]["content"][0] == thought


def test_a_step_stopped_before_its_end_has_partial_usage_and_no_stop() -> None:
    folded = Step()
    for event in events_for(FakeStep([{"type": "text", "text": "abcdef"}]))[:3]:
        folded.take(event)
    finish = folded.finish()
    assert [c["type"] for c in finish] == ["message"] and not folded.ended


def test_cost_and_names() -> None:
    assert cost_of("claude-haiku-4-5-20251001", {"input_tokens": 1_000_000}) == 1.0
    assert cost_of("a-model-nobody-priced", {"input_tokens": 1}) is None
    assert plain_name("mcp__bh__python") == "python" and plain_name("Bash") == "Bash"
