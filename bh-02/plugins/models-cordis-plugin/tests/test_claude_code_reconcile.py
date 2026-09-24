"""What Claude Code holds against what the loop asks next: the decisions, pure.

Messages are shaped as `agent:loop` writes them (its `_Turn.entry`, `unfinished`, tool results,
`feedback` lines), so a change there that breaks the agreement shows up here."""

from typing import Any

from models_cordis_plugin.claude_code import CONTINUE, Deliver, Held, Rebuild, Send, digest, reconcile
from models_cordis_plugin.claude_code.reconcile import CLEAN, CUT, FAILED, OPEN, RUNNING, STOPPED, STRAYED

_STOPPED = "[the person stopped this reply here]"
_MESSAGE = {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}
_CALLING = {
    "role": "assistant",
    "content": [{"type": "tool_use", "id": "t1", "name": "mcp__bh__python", "input": {"code": "1"}}],
}


def _user(text: str, **extra: Any) -> dict[str, Any]:
    return {"role": "user", "content": text, **extra}


def _held(prefix: list[dict[str, Any]], **fields: Any) -> Held:
    return Held(len(prefix), digest(prefix), **fields)


def test_a_first_line_is_sent() -> None:
    assert reconcile(Held(), [_user("hello")]) == Send("hello")


def test_after_an_answer_the_loop_s_entry_is_accepted_and_the_next_line_sent() -> None:
    asked = [_user("hello")]
    held = _held(asked, emitted=_MESSAGE, said="hi", ended=CLEAN)
    rest = [*asked, {"role": "assistant", "content": "hi", "provider": _MESSAGE}, _user("again")]
    assert reconcile(held, rest) == Send("again")


def test_tool_results_for_the_open_calls_are_delivered() -> None:
    asked = [_user("run it")]
    held = _held(asked, emitted=_CALLING, ended=OPEN, calls=("t1",))
    entry = {"role": "assistant", "content": "", "tool_calls": [{"id": "t1"}], "provider": _CALLING}
    rest = [*asked, entry, {"role": "tool", "content": "1", "call_id": "t1"}]
    assert reconcile(held, rest) == Deliver((("t1", "1"),))


def test_a_line_typed_after_a_stop_mid_call_is_a_steer_before_the_results() -> None:
    asked = [_user("run it")]
    held = _held(asked, emitted=_CALLING, ended=OPEN, calls=("t1",))
    entry = {"role": "assistant", "content": "", "tool_calls": [{"id": "t1"}], "provider": _CALLING}
    interrupted = {"role": "tool", "content": "interrupted: ...", "call_id": "t1"}
    rest = [*asked, entry, interrupted, _user("never mind")]
    assert reconcile(held, rest) == Deliver((("t1", "interrupted: ..."),), steer="never mind")


def test_results_that_are_not_the_open_calls_rebuild() -> None:
    asked = [_user("run it")]
    held = _held(asked, emitted=_CALLING, ended=OPEN, calls=("t1", "t2"))
    entry = {"role": "assistant", "content": "", "provider": _CALLING}
    rest = [*asked, entry, {"role": "tool", "content": "1", "call_id": "t1"}]
    assert reconcile(held, rest) == Rebuild("the tool results are not the open calls'", 3, CONTINUE)


def test_a_cut_step_s_entry_without_provider_is_accepted_by_its_text() -> None:
    asked = [_user("write")]
    held = _held(asked, emitted=_MESSAGE, said="Once upon", ended=CUT)
    feedback = _user("Your last message hit the output token limit...", feedback="truncated")
    rest = [*asked, {"role": "assistant", "content": "Once upon"}, feedback]
    assert reconcile(held, rest) == Send(feedback["content"])
    other = [*asked, {"role": "assistant", "content": "something else"}, feedback]
    assert isinstance(reconcile(held, other), Rebuild)


def test_a_stopped_step_s_entry_is_accepted() -> None:
    asked = [_user("write")]
    held = _held(asked, said="Once up", ended=STOPPED)
    rest = [*asked, {"role": "assistant", "content": f"Once up\n\n{_STOPPED}"}, _user("next")]
    assert reconcile(held, rest) == Send("next")


def test_a_different_conversation_rebuilds_everything_but_its_last_line() -> None:
    asked = [_user("hello")]
    held = _held(asked, emitted=_MESSAGE, ended=CLEAN)
    cleared = [_user("fresh start")]  # /clear: a new transcript
    assert reconcile(held, cleared) == Rebuild(
        "the conversation is not the one Claude Code holds", 0, "fresh start"
    )
    history = [_user("a"), {"role": "assistant", "content": "b"}, _user("c")]  # a resume with no state
    assert reconcile(Held(), history) == Rebuild("the request is not one new user line", 2, "c")


def test_a_failed_strayed_or_unfinished_step_rebuilds() -> None:
    rest = [_user("a"), {"role": "assistant", "content": "[this reply failed here; ...]"}, _user("b")]
    for ended in (FAILED, STRAYED, RUNNING):
        decision = reconcile(_held(rest[:1], ended=ended), rest)
        assert isinstance(decision, Rebuild) and decision.prefix == 2 and decision.send == "b"


def test_a_saved_state_from_a_crash_reads_as_failed() -> None:
    for ended in (OPEN, RUNNING):
        assert Held.from_json(_held([], ended=ended, calls=("t1",)).to_json()).ended == FAILED
    kept = _held([_user("a")], emitted=_MESSAGE, said="hi", ended=CLEAN)
    assert Held.from_json(kept.to_json()) == kept


def test_the_digest_ignores_key_order_and_tuples() -> None:
    assert digest([{"a": 1, "b": (1, 2)}]) == digest([{"b": [1, 2], "a": 1}])
    assert digest([{"a": 1}]) != digest([{"a": 2}])
