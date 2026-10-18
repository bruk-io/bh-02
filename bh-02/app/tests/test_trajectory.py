"""`bh_02.trajectory`: a session laid out in time from the bytes of its transcript files, with no session
running and nothing opened (decision-0009, Reading). Fixtures are written as the loop writes them
(`test_trajectory_records.py` holds the loop to the same shape)."""

import dataclasses
import datetime
import json
import re
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

from bh_02.trajectory import Line, Trajectory, Transcript, is_conversation_file, rendered, trajectory

type Json = Mapping[str, object]

LIVE = "transcript.jsonl"
NO_ROWS = "rows.jsonl not found: row reloads are not shown"
# UTC-7: a time on the 18th at 03:47 UTC is the 17th at 20:47 here, so a line that shows the date
# shows the person's day, not the file's
LOCAL = datetime.timezone(datetime.timedelta(hours=-7))
# what must never reach a terminal: C0 and C1 controls but newline and tab, and the bidirectional overrides
UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def jsonl(*entries: Json) -> bytes:
    return b"".join(json.dumps(entry).encode() + b"\n" for entry in entries)


def file(data: bytes, name: str = LIVE, *, agent: str | None = None, modified: float = 0.0) -> Transcript:
    return Transcript(agent, name, modified, data)


def user(message: str, at: str, **more: object) -> Json:
    return {"role": "user", "content": message, "at": at} | more


def step(at: str, **more: object) -> Json:
    return {"at": at} | more


def assistant(content: str, record: Json | None = None, *calls: tuple[str, str]) -> Json:
    entry: dict[str, object] = {"role": "assistant", "content": content}
    if calls:
        entry["tool_calls"] = [{"id": id, "name": name, "input": {}} for id, name in calls]
    if record is not None:
        entry["step"] = record
    return entry


def result(call_id: str, record: Json | None = None) -> Json:
    entry: dict[str, object] = {"role": "tool", "content": "ok", "call_id": call_id, "asides": []}
    if record is not None:
        entry["call"] = record
    return entry


USAGE: Json = {
    "input_tokens": 1200,
    "output_tokens": 212,
    "cache_read_input_tokens": 1000,
    "cache_creation_input_tokens": 0,
    "cost_usd": 0.0312,
}
SETTINGS: Json = {"model": "work/opus", "provider": "claude-code", "max_tokens": 4096, "temperature": 0.2}

# A conversation as the loop writes it: the prompt and tools, a message the model answers with two
# calls (the first asked and with a call of its input's, the second a sub-agent), the final answer,
# a second message, and a step whose call has no result.
CONVERSATION = jsonl(
    {"role": "system", "content": "the prompt"},
    {"role": "tools", "tools": []},
    user(
        "(Today's date: 2026-10-17.)\n\nfix the bug in foo",
        "2026-10-18T03:47:12.345Z",
        today="2026-10-17",
    ),
    assistant(
        "let me look",
        step(
            "2026-10-18T03:47:12.400Z",
            first_chunk=1.2,
            took=4.6,
            model="claude-opus-5-5",
            usage=USAGE,
            settings=SETTINGS,
        ),
        ("c1", "python"),
        ("c2", "agent"),
    ),
    result(
        "c1",
        {
            "at": "2026-10-18T03:47:17.000Z",
            "answer": "yes",
            "waited": 4.2,
            "took": 0.8,
            "nested": [
                {"name": "read_file", "at": "2026-10-18T03:47:17.100Z", "answer": "unasked", "took": 0.01}
            ],
        },
    ),
    result(
        "c2",
        {"at": "2026-10-18T03:47:18.000Z", "answer": "unasked", "took": 12.0, "child": "general-1"},
    ),
    assistant(
        "done",
        step(
            "2026-10-18T03:47:31.000Z",
            first_chunk=0.5,
            took=1.5,
            usage={
                "input_tokens": 1500,
                "output_tokens": 30,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        ),
    ),
    user("and bar?", "2026-10-18T03:48:00.000Z"),
    assistant("looking", step("2026-10-18T03:48:01.000Z"), ("c9", "python")),
)
CHILD = jsonl(
    user("count the files", "2026-10-18T03:47:19.000Z"),
    assistant("3", step("2026-10-18T03:47:20.000Z", first_chunk=0.3, took=1.0, model="claude-haiku-5")),
)


def laid(*files: Transcript, rows: bytes = b"") -> Trajectory:
    return trajectory(files, rows)


def text(laid_out: Trajectory, *, live: bool = False, tz: datetime.tzinfo | None = LOCAL) -> list[str]:
    return [line.text for line in rendered(laid_out, tz, live=live)]


def test_the_trajectory_is_frozen_data_computed_from_the_bytes() -> None:
    one = laid(file(CONVERSATION), file(CHILD, agent="general-1"))
    assert one == laid(file(CONVERSATION), file(CHILD, agent="general-1"))  # the same files, the same value
    with pytest.raises(dataclasses.FrozenInstanceError):
        one.conversations = ()
    (conversation,) = one.conversations
    for node in (conversation, conversation.replies[0], conversation.replies[0].items[0]):
        assert dataclasses.is_dataclass(node) and node.__dataclass_params__.frozen


def test_a_reply_is_the_message_with_the_date_the_loop_told_taken_off_and_the_steps_that_answer_it() -> None:
    (conversation,) = laid(file(CONVERSATION)).conversations
    first, second = conversation.replies
    assert first.message == "fix the bug in foo"
    assert first.at == datetime.datetime(2026, 10, 18, 3, 47, 12, 345000, tzinfo=datetime.UTC)
    assert len(first.items) == 2 and len(second.items) == 1
    assert second.message == "and bar?"


def test_a_step_has_its_timing_model_usage_cost_and_settings_and_a_speed_over_its_generation() -> None:
    (conversation,) = laid(file(CONVERSATION)).conversations
    step = conversation.replies[0].items[0]
    assert step.model == "claude-opus-5-5"
    assert (step.first_chunk, step.took) == (1.2, 4.6)
    assert step.generation == pytest.approx(3.4)
    assert step.tokens_per_second == pytest.approx(212 / 3.4)
    usage = step.usage
    assert (usage.input_tokens, usage.output_tokens, usage.cache_read, usage.cost_usd) == (
        1200,
        212,
        1000,
        0.0312,
    )
    assert step.settings.model == "work/opus" and step.settings.max_tokens == 4096


def test_a_call_has_its_answer_wait_and_run_time_the_calls_of_its_input_and_the_sub_agent_it_started() -> (
    None
):
    laid_out = laid(file(CONVERSATION), file(CHILD, agent="general-1"))
    (conversation,) = laid_out.conversations
    python, agent = conversation.replies[0].items[0].calls
    assert (python.tool, python.answer, python.waited, python.took) == ("python", "yes", 4.2, 0.8)
    (read,) = python.nested
    assert (read.tool, read.answer, read.waited, read.took) == ("read_file", "unasked", None, 0.01)
    assert agent.child == "general-1" and agent.agent is not None
    assert agent.agent.conversations[0].replies[0].message == "count the files"
    assert laid_out.unlinked == ()  # a sub-agent a call names is under it, not listed again


def test_a_call_with_no_result_in_the_transcript_shows_no_result_recorded() -> None:
    lines = text(laid(file(CONVERSATION)))
    (missing,) = [line for line in lines if "no result recorded" in line]
    assert missing.strip().startswith("call python")
    assert [line for line in lines if line.strip().startswith("call")].count(
        missing
    ) == 1  # the others have one


def test_while_following_the_last_step_s_call_with_no_result_is_held_back_as_it_may_be_running() -> None:
    laid_out = laid(file(CONVERSATION))
    assert not any("no result recorded" in line for line in text(laid_out, live=True))
    # one in an earlier step is not running: its transcript went on without a result
    gone = jsonl(
        user("go", "2026-10-18T03:47:12.000Z"),
        assistant("a", step("2026-10-18T03:47:13.000Z"), ("c1", "python")),
        assistant("b", step("2026-10-18T03:47:14.000Z")),
    )
    assert any("no result recorded" in line for line in text(laid(file(gone)), live=True))


def test_the_loops_nudge_to_the_model_is_a_line_between_the_steps_it_follows() -> None:
    data = jsonl(
        user("go", "2026-10-18T03:47:12.000Z"),
        assistant("", step("2026-10-18T03:47:13.000Z", first_chunk=0.1, took=0.2)),
        {"role": "user", "content": "(bh-02: ...)", "feedback": "silent", "at": "2026-10-18T03:47:14.000Z"},
        assistant("ok", step("2026-10-18T03:47:15.000Z", first_chunk=0.1, took=0.2)),
    )
    assert text(laid(file(data)))[2:] == [
        "    step 1  20:47:13.000  first chunk 0.10s  generated in 0.10s",
        "    nudge  20:47:14.000  silent",
        "    step 2  20:47:15.000  first chunk 0.10s  generated in 0.10s",
    ]
    (reply,) = laid(file(data)).conversations[0].replies  # a nudge does not begin a reply of its own
    assert reply.message == "go"


def test_a_step_that_ended_before_any_chunk_says_so() -> None:
    (line,) = [line for line in text(laid(file(CONVERSATION))) if line.strip().startswith("step 1  20:48")]
    assert "no chunk came" in line


def test_the_conversation_a_compact_began_shows_the_summary_step_s_time_and_cost_at_the_boundary() -> None:
    seeded = jsonl(
        user(
            "(bh-02: this conversation carries on from an earlier one)",
            "2026-10-18T03:40:00.000Z",
            seed={"keep": "the todo list"},
        ),
        assistant(
            "the summary",
            step(
                "2026-10-18T03:40:00.000Z",
                first_chunk=2.0,
                took=9.0,
                model="claude-opus-5-5",
                usage=USAGE | {"cost_usd": 0.5},
                settings=SETTINGS,
            ),
        ),
        user("next", "2026-10-18T03:41:00.000Z"),
        assistant("k", step("2026-10-18T03:41:01.000Z", first_chunk=0.3, took=1.0)),
    )
    before = jsonl(user("old", "2026-10-18T02:00:00.000Z"), assistant("a", step("2026-10-18T02:00:01.000Z")))
    lines = text(laid(file(before, "transcript.jsonl.bak"), file(seeded)))
    boundary = next(n for n, line in enumerate(lines) if line.startswith("conversation 2"))
    assert lines[boundary].endswith("begun by /compact, asked to keep: the todo list")
    summary = lines[boundary + 1]
    assert summary.strip().startswith("summary step  2026-10-17 20:40:00.000  claude-opus-5-5")
    assert "first chunk 2.00s" in summary and "generated in 7.00s" in summary and "cost $0.5000" in summary
    assert lines[boundary + 2].strip().startswith("settings: work/opus via claude-code")
    # the summary is the boundary, not a reply or step of the new conversation
    (_, second) = laid(file(before, "transcript.jsonl.bak"), file(seeded)).conversations
    assert [reply.message for reply in second.replies] == ["next"]
    assert second.seed is not None and second.seed.keep == "the todo list"


def test_a_conversation_that_follows_another_without_a_seed_was_cleared() -> None:
    old = jsonl(user("old", "2026-10-18T02:00:00.000Z"))
    new = jsonl(user("new", "2026-10-18T03:00:00.000Z"))
    lines = text(laid(file(old, "transcript.jsonl.bak"), file(new)))
    assert [line for line in lines if line.startswith("conversation")] == [
        "conversation 1  transcript.jsonl.bak  2026-10-17 19:00:00.000",
        "conversation 2  transcript.jsonl  2026-10-17 20:00:00.000  begun by /clear",
    ]


def test_a_sub_agent_goes_under_its_call_and_one_no_call_names_after_them_by_its_own_times() -> None:
    early = jsonl(user("early", "2026-10-18T03:45:00.000Z"), assistant("x", step("2026-10-18T03:45:01.000Z")))
    late = jsonl(user("late", "2026-10-18T04:00:00.000Z"))
    lines = text(
        laid(
            file(CONVERSATION),
            file(CHILD, agent="general-1"),
            file(late, agent="general-2"),  # named first, but its own time is the later
            file(early, agent="general-3"),
        )
    )
    call = next(n for n, line in enumerate(lines) if line.strip().startswith("call agent"))
    assert lines[call].endswith("started sub-agent general-1")
    assert lines[call + 1] == "        sub-agent general-1"  # inside the call that started it
    assert lines[call + 3] == "            reply 1  2026-10-17 20:47:19.000  count the files"
    assert lines[-7:] == [
        "sub-agent general-3  (no call that started it is recorded)",
        "  conversation 1  transcript.jsonl  2026-10-17 20:45:00.000",
        "    reply 1  2026-10-17 20:45:00.000  early",
        "      step 1  20:45:01.000  no chunk came",
        "sub-agent general-2  (no call that started it is recorded)",
        "  conversation 1  transcript.jsonl  2026-10-17 21:00:00.000",
        "    reply 1  2026-10-17 21:00:00.000  late",
    ]


def test_a_call_naming_a_sub_agent_that_has_no_transcript_says_so() -> None:
    (line,) = [line for line in text(laid(file(CONVERSATION))) if "started sub-agent" in line]
    assert line.endswith("started sub-agent general-1 (its transcript was not found)")


def test_the_conversations_are_ordered_live_last_and_backups_by_first_at_else_by_mtime() -> None:
    def one(message: str, at: str | None) -> bytes:
        return jsonl({"role": "user", "content": message} | ({"at": at} if at else {}))

    live = one("live", "2026-10-18T01:00:00.000Z")  # its time is the earliest, and it is last all the same
    files = [
        file(one("by name 2", "2026-10-18T05:00:00.000Z"), "transcript.jsonl.bak", modified=1.0),
        file(one("by name 1", "2026-10-18T03:00:00.000Z"), "transcript.jsonl.bak.2", modified=9.0),
        # no `at` at all: ordered by when it was copied, 04:00 UTC
        file(
            one("by mtime", None),
            "transcript.jsonl.bak.3",
            modified=datetime.datetime(2026, 10, 18, 4, tzinfo=datetime.UTC).timestamp(),
        ),
        file(live),
    ]
    messages = [c.replies[0].message for c in laid(*files).conversations]
    assert messages == ["by name 1", "by mtime", "by name 2", "live"]
    # the order the files are given in does not matter
    assert [c.replies[0].message for c in laid(*reversed(files)).conversations] == messages


def test_backups_with_the_same_time_keep_the_order_they_were_made_in() -> None:
    same = jsonl(user("x", "2026-10-18T03:00:00.000Z"))
    names = [
        c.name
        for c in laid(
            *(
                file(same, n)
                for n in ("transcript.jsonl.bak.10", "transcript.jsonl.bak.2", "transcript.jsonl.bak")
            )
        ).conversations
    ]
    assert names == ["transcript.jsonl.bak", "transcript.jsonl.bak.2", "transcript.jsonl.bak.10"]


def test_what_the_loop_leaves_out_for_its_own_reason_is_left_out_of_the_line() -> None:
    """The answer to a message the model was never asked is no step and has no `step` record, and a
    call refused before approval has an `at` and no `answer`: each line says what it has."""
    refused = "(the reply was stopped while the prompt was read)"
    data = jsonl(
        user("hello", "2026-10-18T03:47:12.000Z"),
        assistant(refused),
        user("run it", "2026-10-18T03:48:00.000Z"),
        assistant("", step("2026-10-18T03:48:01.000Z", first_chunk=0.5, took=1.0), ("c1", "nowhere")),
        result("c1", {"at": "2026-10-18T03:48:02.000Z"}),
    )
    assert text(laid(file(data))) == [
        "conversation 1  transcript.jsonl  2026-10-17 20:47:12.000",
        "  reply 1  2026-10-17 20:47:12.000  hello",
        "    step 1",
        "  reply 2  2026-10-17 20:48:00.000  run it",
        "    step 1  20:48:01.000  first chunk 0.50s  generated in 0.50s",
        "      call nowhere  20:48:02.000  not put to approval",
    ]


def test_a_field_of_the_wrong_type_or_a_record_that_is_not_one_is_left_out_not_a_failure() -> None:
    broken = jsonl(
        user("hi", "not a time", today=5),
        {
            "role": "assistant",
            "content": 3,
            "tool_calls": ["nonsense", {"id": 1, "name": ["python"]}],
            "step": {
                "at": "2026-10-18T03:47:12.000Z",
                "first_chunk": "slow",
                "took": True,
                "usage": "lots",
                "settings": [],
                "model": 7,
            },
        },
        {
            "role": "tool",
            "call_id": 1,
            "call": {"at": 5, "answer": "maybe", "waited": float("nan"), "took": 10**400, "nested": "x"},
        },
        {"role": "assistant", "step": []},
        {"role": "user", "feedback": 3, "at": None},
        {"role": "tool"},
        {"role": "banana"},
        {"role": "user", "content": "kept", "at": "2026-10-18T03:47:20.000Z", "seed": "not a record"},
    )
    lines = text(laid(file(broken + b"[1, 2]\n3\nnull\n")))
    assert lines == [
        "conversation 1  transcript.jsonl  2026-10-17 20:47:12.000",
        "  reply 1  hi",
        "    step 1  2026-10-17 20:47:12.000  no chunk came",
        "      call ?",
        "    step 2",
        "  reply 2",
        "  reply 3  2026-10-17 20:47:20.000  kept",
    ]


def test_a_torn_last_line_is_skipped_and_the_whole_lines_before_it_are_shown() -> None:
    whole = jsonl(user("first", "2026-10-18T03:47:12.000Z"), assistant("a", step("2026-10-18T03:47:13.000Z")))
    torn = whole + b'{"role": "user", "content": "being writ'
    assert text(laid(file(torn))) == text(laid(file(whole)))
    assert [r.message for r in laid(file(torn)).conversations[0].replies] == ["first"]
    assert text(laid(file(b'{"role": "user", "content": "being writ'))) == []  # nothing whole at all


def test_control_characters_never_reach_the_text() -> None:
    hostile = "\x1b[2J\x1b]0;title\x07 ok \u202egpj.exe\u2066 \x9b \x00 \r\n\tend"
    data = jsonl(
        user(hostile, "2026-10-18T03:47:12.000Z"),
        assistant(
            "x",
            step("2026-10-18T03:47:13.000Z", model=hostile, settings={"model": hostile, "provider": hostile}),
            ("c1", hostile),
        ),
        result("c1", {"at": "2026-10-18T03:47:14.000Z", "child": hostile}),
        {"role": "user", "content": "n", "feedback": hostile, "at": "2026-10-18T03:47:15.000Z"},
    )
    lines = text(laid(file(data, "transcript.jsonl.bak"), file(data, agent=hostile)))
    assert lines and all("\n" not in line and not UNSAFE.search(line) for line in lines)
    assert any("ok" in line for line in lines)  # the words stay, the controls go


def test_times_are_shown_in_the_zone_asked_for_and_in_the_machines_when_none_is() -> None:
    laid_out = laid(file(CONVERSATION))
    (reply,) = [line for line in text(laid_out) if line.strip().startswith("reply 1")]
    assert "2026-10-17 20:47:12.345" in reply  # UTC-7
    (utc,) = [line for line in text(laid_out, tz=datetime.UTC) if line.strip().startswith("reply 1")]
    assert "2026-10-18 03:47:12.345" in utc


def test_the_default_zone_is_the_machines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "Pacific/Auckland")  # UTC+13 on the 18th of October
    time.tzset()
    try:
        (reply,) = [
            line for line in text(laid(file(CONVERSATION)), tz=None) if line.strip().startswith("reply 1")
        ]
        assert "2026-10-18 16:47:12.345" in reply
    finally:
        monkeypatch.undo()
        time.tzset()


def test_a_step_shows_its_time_alone_when_it_is_the_replys_day_and_with_its_date_when_it_is_not() -> None:
    data = jsonl(
        user("late", "2026-10-18T06:59:59.000Z"),  # 23:59:59 on the 17th at UTC-7
        assistant("a", step("2026-10-18T07:00:01.000Z")),  # 00:00:01 on the 18th
    )
    _, reply, step_line = text(laid(file(data)))
    assert "2026-10-17 23:59:59.000" in reply
    assert "step 1  2026-10-18 00:00:01.000" in step_line


def test_the_rows_file_is_read_into_the_trajectory_by_time_skipping_what_is_not_a_record() -> None:
    rows = (
        jsonl(
            {"at": "2026-10-18T03:50:00.000Z", "kind": "reload", "row": "model"},
            {
                "at": "2026-10-18T03:40:00.000Z",
                "kind": "failed",
                "row": "agents/general-1/loop",
                "error": "boom",
            },
            {"at": "yesterday", "kind": "reload", "row": "x"},
            {"at": "2026-10-18T03:41:00.000Z", "kind": 4, "row": "x"},
        )
        + b'{"at": "2026-10-18T03:5'
    )
    reloads = laid(file(CONVERSATION), rows=rows).reloads
    assert [(r.kind, r.row, r.error) for r in reloads] == [
        ("failed", "agents/general-1/loop", "boom"),
        ("reload", "model", None),
    ]
    assert laid(file(CONVERSATION)).reloads == ()


def test_a_conversation_with_no_rows_file_has_no_reloads_and_is_said_so_first() -> None:
    """`rows` None is a session with no rows.jsonl, which is not the same as an empty one: that has no
    reloads and is not said so. Only a session with a conversation is said so."""
    missing = trajectory([file(CONVERSATION)])
    assert missing.reloads is None
    assert text(missing)[0] == NO_ROWS
    assert NO_ROWS not in text(laid(file(CONVERSATION)))  # an empty rows file: found, no reloads
    assert laid(file(CONVERSATION)).reloads == ()
    assert text(trajectory([])) == []  # no conversation: nothing to say


def reload_record(at: str, kind: str, row: str, **more: object) -> Json:
    return {"at": at, "kind": kind, "row": row} | more


def test_each_row_reload_is_a_line_in_time_order_among_the_steps_and_calls_where_the_next_line_is() -> None:
    rows = jsonl(
        # in the order the file has them, which is not the order they happened in
        reload_record("2026-10-18T03:47:45.000Z", "reload", "python"),  # between the replies
        reload_record("2026-10-18T03:40:00.000Z", "reload", "loop"),  # before the conversation
        reload_record(
            "2026-10-18T03:47:14.000Z", "reload", "transcript"
        ),  # after the step, before its first call
        reload_record(
            "2026-10-18T03:47:17.050Z", "failed", "model", error="RuntimeError('boom')"
        ),  # after the call, before the call its input made
        reload_record(
            "2026-10-18T03:47:19.500Z", "reload", "agents/general-1/loop"
        ),  # a sub-agent's row: placed by the sub-agent's lines, not the session's
        reload_record("2026-10-18T03:50:00.000Z", "reload", "loop"),  # after everything
    )
    lines = text(laid(file(CONVERSATION), file(CHILD, agent="general-1"), rows=rows))
    assert "\n".join(lines) == "\n".join(
        [
            "row first load loop  20:40:00.000",
            "conversation 1  transcript.jsonl  2026-10-17 20:47:12.345",
            "  reply 1  2026-10-17 20:47:12.345  fix the bug in foo",
            "    step 1  20:47:12.400  claude-opus-5-5  first chunk 1.20s  generated in 3.40s  62.4 tokens/s"
            "  in 1,200 tokens  out 212 tokens  cache read 1,000  cost $0.0312",
            "      settings: work/opus via claude-code, max_tokens 4096, temperature 0.2",
            "      row first load transcript  20:47:14.000",
            "      call python  20:47:17.000  answer yes (waited 4.20s)  ran 0.80s",
            "        row failed model  20:47:17.050  RuntimeError('boom')",
            "        nested call read_file  20:47:17.100  answer unasked  ran 0.01s",
            "      call agent  20:47:18.000  answer unasked  ran 12.00s  started sub-agent general-1",
            "        sub-agent general-1",
            "          conversation 1  transcript.jsonl  2026-10-17 20:47:19.000",
            "            reply 1  2026-10-17 20:47:19.000  count the files",
            "              row first load agents/general-1/loop  20:47:19.500",
            "              step 1  20:47:20.000  claude-haiku-5  first chunk 0.30s  generated in 0.70s",
            "    step 2  20:47:31.000  first chunk 0.50s  generated in 1.00s  30.0 tokens/s"
            "  in 1,500 tokens  out 30 tokens",
            "  row first load python  20:47:45.000",
            "  reply 2  2026-10-17 20:48:00.000  and bar?",
            "    step 1  20:48:01.000  no chunk came",
            "      call python  no result recorded",
            "row reload loop  20:50:00.000",
        ]
    )


def test_a_sub_agents_rows_are_placed_by_its_lines_and_the_session_s_by_the_session_s() -> None:
    """The child runs alongside its parent: a reload of the session's own row while it runs is not put
    among the child's lines, and the child's rows coming up are put before its first line."""
    rows = jsonl(
        reload_record("2026-10-18T03:47:18.900Z", "reload", "agents/general-1"),  # the child's loader
        reload_record("2026-10-18T03:47:18.950Z", "reload", "agents/general-1/loop"),
        reload_record("2026-10-18T03:47:19.500Z", "reload", "agents"),  # the parent's agents row
        reload_record("2026-10-18T03:59:00.000Z", "reload", "agents/ghost-9/loop"),  # a child with no files
    )
    lines = text(laid(file(CONVERSATION), file(CHILD, agent="general-1"), rows=rows))
    assert [line.strip().split("  ")[0] for line in lines[6:]] == [
        "call agent",
        "sub-agent general-1",
        "row first load",  # the child's two rows coming up, before its first line, at its depth
        "conversation 1",
        "reply 1",
        "step 1",
        "row first load agents",  # the session's, among the session's lines, after the child's block
        "step 2",
        "reply 2",
        "step 1",
        "call python",
        "row first load agents/ghost-9/loop",  # no line of the child's to place it: after the last line
    ]
    assert lines[8] == " " * 10 + "row first load  20:47:18.900  2 rows in 0.05s"
    assert lines[-1] == "row first load agents/ghost-9/loop  20:59:00.000"


def test_a_sub_agent_no_call_names_has_its_rows_in_its_own_block() -> None:
    rows = jsonl(reload_record("2026-10-18T03:47:18.950Z", "reload", "agents/general-1/loop"))
    data = jsonl(user("hi", "2026-10-18T03:47:00.000Z"))
    lines = text(laid(file(data), file(CHILD, agent="general-1"), rows=rows))
    assert [line.strip().split("  ")[0] for line in lines] == [
        "conversation 1",
        "reply 1",
        "sub-agent general-1",
        "row first load agents/general-1/loop",
        "conversation 1",
        "reply 1",
        "step 1",
    ]


def test_a_reload_at_the_time_of_a_line_comes_after_it_and_one_with_no_line_after_it_comes_last() -> None:
    data = jsonl(user("hi", "2026-10-18T03:00:00.000Z"), assistant("a", step("2026-10-18T03:00:01.000Z")))
    rows = jsonl(
        reload_record("2026-10-18T03:00:00.000Z", "reload", "same-as-the-reply"),
        reload_record("2026-10-18T03:00:01.000Z", "reload", "same-as-the-step"),
    )
    lines = text(laid(file(data), rows=rows))
    assert [line.strip().split("  ")[0] for line in lines] == [
        "conversation 1",
        "reply 1",
        "row first load same-as-the-reply",
        "step 1",
        "row first load same-as-the-step",
    ]


def test_reloads_of_a_session_with_no_conversation_are_all_there_with_their_dates() -> None:
    rows = jsonl(
        reload_record("2026-10-18T03:00:00.000Z", "reload", "loop"),
        reload_record("2026-10-19T03:00:00.000Z", "failed", "ui", error="boom"),
    )
    assert text(laid(rows=rows)) == [
        "row first load loop  2026-10-17 20:00:00.000",
        "row failed ui  2026-10-18 20:00:00.000  boom",
    ]


def test_a_reload_shows_its_date_only_when_it_is_not_the_day_of_the_line_it_is_placed_by() -> None:
    data = jsonl(user("hi", "2026-10-18T03:00:00.000Z"), assistant("a", step("2026-10-18T03:00:01.000Z")))
    rows = jsonl(
        reload_record("2026-10-17T03:00:00.000Z", "reload", "loop"),  # its first load
        reload_record("2026-10-18T02:59:59.000Z", "reload", "loop"),
        reload_record("2026-10-18T09:00:00.000Z", "reload", "loop"),
    )
    lines = text(laid(file(data), rows=rows))
    assert lines[0] == "row first load loop  2026-10-16 20:00:00.000"
    assert lines[1] == "row reload loop  19:59:59.000"
    assert lines[-1] == "row reload loop  2026-10-18 02:00:00.000"


def test_a_row_reload_never_puts_a_control_character_on_the_terminal() -> None:
    hostile = "\x1b[2J\x07 name \u202etxt.exe"
    rows = jsonl(reload_record("2026-10-18T03:00:00.000Z", "failed", f"agents/{hostile}", error=hostile))
    (line,) = text(laid(rows=rows))
    assert "name" in line and not UNSAFE.search(line)


# --- first loads ------------------------------------------------------------------------------------------

BOOT = datetime.datetime(2026, 10, 18, 3, 40, tzinfo=datetime.UTC)  # 20:40:00 here, before the conversation


def came_up(at: datetime.datetime, *rows: str, apart: float = 0.01) -> list[Json]:
    """A `reload` record for each of `rows`: the first at `at`, each `apart` seconds after the one before."""
    stamps = (at + datetime.timedelta(seconds=apart * n) for n in range(len(rows)))
    return [
        reload_record(moment.isoformat(timespec="milliseconds").replace("+00:00", "Z"), "reload", row)
        for moment, row in zip(stamps, rows, strict=True)
    ]


def test_a_rows_first_record_in_the_session_is_its_first_load_by_time_and_a_failure_is_never_one() -> None:
    rows = jsonl(
        # in the order the file has them, which is not the order they happened in
        reload_record("2026-10-18T03:41:00.000Z", "reload", "loop"),  # a reload: it came up at 03:40
        reload_record("2026-10-18T03:40:00.000Z", "reload", "loop"),
        reload_record("2026-10-18T03:40:01.000Z", "failed", "model", error="boom"),  # named by failing
        reload_record("2026-10-18T03:42:00.000Z", "reload", "model"),  # so this one is not a first load
        reload_record("2026-10-18T03:43:00.000Z", "reload", "agents/general-1/loop"),
        reload_record("2026-10-18T03:44:00.000Z", "reload", "ui"),
    )
    assert [(r.row, r.kind, r.first) for r in laid(rows=rows).reloads] == [
        ("loop", "reload", True),
        ("model", "failed", False),
        ("loop", "reload", False),
        ("model", "reload", False),
        ("agents/general-1/loop", "reload", True),
        ("ui", "reload", True),
    ]


def test_the_rows_a_session_comes_up_with_are_one_line_with_how_many_and_the_time_they_took() -> None:
    rows = jsonl(*came_up(BOOT, "loader", "loop", "tools", "transcript", "ui", apart=0.03))
    lines = text(laid(file(CONVERSATION), rows=rows))
    assert lines[:2] == [
        "row first load  20:40:00.000  5 rows in 0.12s",
        "conversation 1  transcript.jsonl  2026-10-17 20:47:12.345",
    ]
    assert sum("row " in line for line in lines) == 1


def test_a_reload_or_failure_among_first_loads_is_a_line_and_the_first_loads_around_it_are_lines() -> None:
    first = came_up(BOOT, "loader", "loop", "ui")
    rows = jsonl(
        *first,
        reload_record("2026-10-18T03:40:00.100Z", "reload", "loop"),
        *came_up(BOOT + datetime.timedelta(seconds=0.2), "python"),
        reload_record("2026-10-18T03:40:00.300Z", "failed", "model", error="boom"),
        *came_up(BOOT + datetime.timedelta(seconds=0.4), "tools", "memory"),
    )
    assert text(laid(rows=rows)) == [
        "row first load  2026-10-17 20:40:00.000  3 rows in 0.02s",
        "row reload loop  2026-10-17 20:40:00.100",
        "row first load python  2026-10-17 20:40:00.200",
        "row failed model  2026-10-17 20:40:00.300  boom",
        "row first load  2026-10-17 20:40:00.400  2 rows in 0.01s",
    ]


def test_a_sub_agents_first_loads_are_one_line_under_it_and_the_sessions_reloads_do_not_cut_them() -> None:
    child = BOOT + datetime.timedelta(seconds=7 * 60 + 18)  # 03:47:18, as the call starts it
    rows = jsonl(
        *came_up(child, "agents/general-1", "agents/general-1/loop", "agents/general-1/python", apart=0.01),
        reload_record("2026-10-18T03:47:18.015Z", "reload", "agents"),  # the session's own, among them
        *came_up(child + datetime.timedelta(seconds=0.5), "agents/general-1/tools"),
        reload_record(
            "2026-10-18T03:47:19.600Z", "reload", "agents/general-1/loop"
        ),  # a reload of the child's
    )
    lines = text(laid(file(CONVERSATION), file(CHILD, agent="general-1"), rows=rows))
    start = lines.index("        sub-agent general-1")
    assert lines[start + 1 : start + 4] == [
        "          row first load  20:47:18.000  4 rows in 0.50s",
        "          conversation 1  transcript.jsonl  2026-10-17 20:47:19.000",
        "            reply 1  2026-10-17 20:47:19.000  count the files",
    ]
    assert [line.strip() for line in lines if "row " in line] == [
        "row first load  20:47:18.000  4 rows in 0.50s",
        "row reload agents/general-1/loop  20:47:19.600",  # placed by the child's lines
        "row first load agents  20:47:18.015",  # the session's own row, a line of its own, by the session's
    ]


def test_a_row_that_comes_up_later_is_a_line_of_its_own_and_not_part_of_the_boot() -> None:
    rows = jsonl(
        *came_up(BOOT, "loader", "loop", "ui"),
        *came_up(BOOT + datetime.timedelta(minutes=7, seconds=25), "added-by-a-layer-edit"),
    )
    lines = text(laid(file(CONVERSATION), rows=rows))
    assert [line.strip() for line in lines if "row " in line] == [
        "row first load  20:40:00.000  3 rows in 0.02s",
        "row first load added-by-a-layer-edit  20:47:25.000",
    ]
    assert (
        lines.index("    row first load added-by-a-layer-edit  20:47:25.000")
        == lines.index(
            "    step 2  20:47:31.000  first chunk 0.50s  generated in 1.00s  30.0 tokens/s"
            "  in 1,500 tokens  out 30 tokens"
        )
        - 1
    )


def test_a_session_with_rows_but_no_conversation_has_its_first_loads_as_one_line() -> None:
    assert text(laid(rows=jsonl(*came_up(BOOT, "loader", "loop")))) == [
        "row first load  2026-10-17 20:40:00.000  2 rows in 0.01s"
    ]


def test_while_the_files_are_written_the_first_loads_at_the_end_wait_for_something_after_them() -> None:
    boot = jsonl(*came_up(BOOT, "loader", "loop", "ui"))
    assert text(laid(rows=boot), live=True) == []  # more rows may be coming: no line to print a count of
    failed = reload_record("2026-10-18T03:40:01.000Z", "failed", "model", error="boom")
    assert text(laid(rows=boot + jsonl(failed)), live=True) == [
        "row first load  2026-10-17 20:40:00.000  3 rows in 0.02s",  # a failure came after them
        "row failed model  2026-10-17 20:40:01.000  boom",
    ]
    lines = text(laid(file(CONVERSATION), rows=boot), live=True)
    assert lines[0] == "row first load  20:40:00.000  3 rows in 0.02s"  # the session's first line came after
    assert text(laid(file(CONVERSATION), rows=boot))[0] == lines[0]  # not live, it is there anyway
    assert text(laid(rows=boot)) == ["row first load  2026-10-17 20:40:00.000  3 rows in 0.02s"]


def test_a_first_load_line_keeps_its_key_as_rows_come_up_and_the_files_grow() -> None:
    few = jsonl(*came_up(BOOT, "loader", "loop"))
    more = jsonl(*came_up(BOOT, "loader", "loop", "ui", "tools"))
    (alone,) = [line for line in rendered(laid(file(CONVERSATION), rows=few), LOCAL) if line.key[0] == "rows"]
    (grown,) = [
        line for line in rendered(laid(file(CONVERSATION), rows=more), LOCAL) if line.key[0] == "rows"
    ]
    assert alone.key == grown.key and alone.text != grown.text
    keys = [
        line.key
        for line in rendered(laid(file(CONVERSATION), rows=more + jsonl(*came_up(BOOT, "loop"))), LOCAL)
    ]
    assert len(set(keys)) == len(keys)


# --- runs -------------------------------------------------------------------------------------------------

RESUME = BOOT + datetime.timedelta(hours=1)  # 21:40:00 here: a later run of the same session
CAME_UP = ("loader", "loop", "transcript", "ui", "tools")


def run_record(at: datetime.datetime) -> Json:
    """The line the shell writes when it opens the log: a run's start, which names no row."""
    return {"at": at.isoformat(timespec="milliseconds").replace("+00:00", "Z"), "kind": "run"}


def test_a_resumed_runs_boot_is_one_line_like_the_first_and_a_restart_after_it_is_a_reload() -> None:
    """A session resumed goes on in the same `rows.jsonl`: the rows of its second run were all seen in the
    first, and the `run` line is what says the second run's start."""
    rows = jsonl(
        run_record(BOOT),
        *came_up(BOOT, *CAME_UP),
        run_record(RESUME),
        *came_up(RESUME, *CAME_UP),
        reload_record("2026-10-18T04:50:00.000Z", "reload", "loop"),  # a restart in the second run
    )
    lines = text(laid(file(CONVERSATION), rows=rows))
    assert [line.strip() for line in lines if "row " in line] == [
        "row first load  20:40:00.000  5 rows in 0.04s",
        "row first load  21:40:00.000  5 rows in 0.04s",  # the resumed run's boot, one line
        "row reload loop  21:50:00.000",  # a reload of a running session's row is still its own line
    ]
    assert not any("run" in line.split("  ")[0] for line in lines)  # the marker prints no line of its own


def test_the_boots_of_two_runs_with_nothing_between_them_are_two_lines() -> None:
    rows = jsonl(
        run_record(BOOT),
        *came_up(BOOT, *CAME_UP),
        run_record(RESUME),  # the first run ended before it said anything, and the next one began
        *came_up(RESUME, *CAME_UP),
    )
    assert text(laid(rows=rows)) == [
        "row first load  2026-10-17 20:40:00.000  5 rows in 0.04s",
        "row first load  2026-10-17 21:40:00.000  5 rows in 0.04s",
    ]


def test_the_rows_of_a_resumed_run_are_first_loads_again_a_sub_agents_and_a_failed_ones_too() -> None:
    child = ("agents/general-1", "agents/general-1/loop")
    first = [
        run_record(BOOT),
        *came_up(BOOT, "loader", "loop"),
        *came_up(BOOT + datetime.timedelta(seconds=1), *child),
        reload_record("2026-10-18T03:40:02.000Z", "failed", "model", error="boom"),
    ]
    second = [
        run_record(RESUME),
        *came_up(RESUME, "loader", "loop", "model"),  # "model" failed in the run before
        *came_up(RESUME + datetime.timedelta(seconds=1), *child),
    ]
    reloads = laid(rows=jsonl(*first, *second)).reloads
    assert [(r.run, r.kind, r.row, r.first) for r in reloads if r.run == 2] == [
        (2, "reload", "loader", True),
        (2, "reload", "loop", True),
        (2, "reload", "model", True),
        (2, "reload", "agents/general-1", True),
        (2, "reload", "agents/general-1/loop", True),
    ]
    last = [(r.run, r.kind, r.row, r.first) for r in reloads if r.run == 1][-1]
    assert last == (1, "failed", "model", False)  # a failure is never a first load


def test_a_run_line_is_a_start_and_not_a_reload_and_one_that_is_not_a_time_starts_nothing() -> None:
    rows = jsonl(
        reload_record("2026-10-18T03:40:00.000Z", "reload", "loop"),
        {"at": "yesterday", "kind": "run"},  # not a time: it is not a record, so no run began
        reload_record("2026-10-18T03:41:00.000Z", "reload", "loop"),
        run_record(datetime.datetime(2026, 10, 18, 3, 42, tzinfo=datetime.UTC)),
        reload_record("2026-10-18T03:43:00.000Z", "reload", "loop"),
    )
    assert [(r.kind, r.row, r.first, r.run) for r in laid(rows=rows).reloads] == [
        ("reload", "loop", True, 0),  # before any run line: the file's start is a run's start
        ("reload", "loop", False, 0),
        ("reload", "loop", True, 1),  # the run line starts the next run, and is not a reload of its own
    ]


def test_a_first_load_never_puts_a_control_character_on_the_terminal() -> None:
    hostile = "\x1b[2J\x07 name \u202etxt.exe"
    (one,) = text(laid(rows=jsonl(*came_up(BOOT, f"agents/{hostile}"))))
    assert "name" in one and not UNSAFE.search(one)


def test_a_line_keeps_its_key_as_the_files_grow_so_a_follower_prints_it_once() -> None:
    cut = CONVERSATION.splitlines(keepends=True)
    keys = [
        [line.key for line in rendered(laid(file(b"".join(cut[:n]))), LOCAL)] for n in range(3, len(cut) + 1)
    ]
    for shorter, longer in zip(keys, keys[1:], strict=False):
        assert set(shorter) <= set(longer)
    assert len({k for line in keys[-1:] for k in line}) == len(keys[-1])  # and no two lines share one


def test_reloads_have_keys_of_their_own_that_stay_as_the_rows_file_and_the_conversation_grow() -> None:
    same = reload_record("2026-10-18T03:00:00.000Z", "reload", "loop")
    first = jsonl(same, same, reload_record("2026-10-18T03:00:00.500Z", "reload", "ui"))
    later = first + jsonl(reload_record("2026-10-18T04:00:00.000Z", "reload", "loop"))
    cut = CONVERSATION.splitlines(keepends=True)
    before = rendered(laid(file(b"".join(cut[:4])), rows=first), LOCAL)
    after = rendered(laid(file(CONVERSATION), rows=later), LOCAL)
    assert len({line.key for line in before}) == len(before)  # two alike are two keys
    assert {line.key for line in before if line.key[0] == "rows"} <= {line.key for line in after}
    assert len({line.key for line in after}) == len(after)


def test_a_conversation_keeps_its_key_when_a_clear_renames_its_file_and_a_new_one_has_another() -> None:
    old = jsonl(user("old", "2026-10-18T02:00:00.000Z"), assistant("a", step("2026-10-18T02:00:01.000Z")))
    before = {line.key for line in rendered(laid(file(old)), LOCAL)}
    new = jsonl(user("new", "2026-10-18T03:00:00.000Z"))
    after = rendered(laid(file(old, "transcript.jsonl.bak"), file(new)), LOCAL)
    assert before <= {line.key for line in after}
    assert len({line.key for line in after}) == len(after)


def test_the_same_conversation_seen_twice_while_a_rewrite_copies_it_has_the_same_keys() -> None:
    one = jsonl(user("old", "2026-10-18T02:00:00.000Z"))
    both = rendered(laid(file(one, "transcript.jsonl.bak"), file(one)), LOCAL)
    assert {line.key for line in both} == {line.key for line in rendered(laid(file(one)), LOCAL)}


def test_which_files_are_conversations() -> None:
    names = ["transcript.jsonl", "transcript.jsonl.bak", "transcript.jsonl.bak.2", "transcript.jsonl.bak.17"]
    assert all(is_conversation_file(name) for name in names)
    for other in (
        "transcript.jsonl.new",
        "transcript.jsonl.bak.",
        "transcript.jsonl.bak.x",
        "events.jsonl",
        "xtranscript.jsonl",
        "transcript.jsonl.bak.2.new",
        "transcript.jsonl\n",
        "",
    ):
        assert not is_conversation_file(other)


def test_lines_are_what_rendered_returns() -> None:
    (first, *_) = rendered(laid(file(CONVERSATION)), LOCAL)
    assert isinstance(first, Line) and first.text.startswith("conversation 1  transcript.jsonl")


def test_the_whole_layout_of_a_session(tmp_path: Path) -> None:
    lines = text(laid(file(CONVERSATION), file(CHILD, agent="general-1")))
    assert "\n".join(lines) == "\n".join(
        [
            "conversation 1  transcript.jsonl  2026-10-17 20:47:12.345",
            "  reply 1  2026-10-17 20:47:12.345  fix the bug in foo",
            "    step 1  20:47:12.400  claude-opus-5-5  first chunk 1.20s  generated in 3.40s  62.4 tokens/s"
            "  in 1,200 tokens  out 212 tokens  cache read 1,000  cost $0.0312",
            "      settings: work/opus via claude-code, max_tokens 4096, temperature 0.2",
            "      call python  20:47:17.000  answer yes (waited 4.20s)  ran 0.80s",
            "        nested call read_file  20:47:17.100  answer unasked  ran 0.01s",
            "      call agent  20:47:18.000  answer unasked  ran 12.00s  started sub-agent general-1",
            "        sub-agent general-1",
            "          conversation 1  transcript.jsonl  2026-10-17 20:47:19.000",
            "            reply 1  2026-10-17 20:47:19.000  count the files",
            "              step 1  20:47:20.000  claude-haiku-5  first chunk 0.30s  generated in 0.70s",
            "    step 2  20:47:31.000  first chunk 0.50s  generated in 1.00s  30.0 tokens/s"
            "  in 1,500 tokens  out 30 tokens",
            "  reply 2  2026-10-17 20:48:00.000  and bar?",
            "    step 1  20:48:01.000  no chunk came",
            "      call python  no result recorded",
        ]
    )
