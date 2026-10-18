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


def test_a_conversation_from_before_the_records_prints_with_no_times_and_does_not_fail() -> None:
    before = jsonl(
        {"role": "system", "content": "the prompt"},
        {"role": "user", "content": "(Today's date: 2026-10-07.)\n\nhello", "today": "2026-10-07"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "python", "input": {"code": "1"}}],
            "provider": {"anything": 1},
        },
        {"role": "tool", "content": "1", "call_id": "c1"},
        {"role": "assistant", "content": "done"},
    )
    lines = text(laid(file(before)), tz=None)
    assert lines == [
        "conversation 1  transcript.jsonl",
        "  reply 1  hello",
        "    step 1",
        "      call python",
        "    step 2",
    ]
    assert not any(re.search(r"\d\d:\d\d", line) for line in lines)


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
            {"at": "2026-10-18T03:50:00.000Z", "kind": "restart", "row": "model"},
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
        ("restart", "model", None),
    ]
    assert laid(file(CONVERSATION)).reloads == ()


def test_a_line_keeps_its_key_as_the_files_grow_so_a_follower_prints_it_once() -> None:
    cut = CONVERSATION.splitlines(keepends=True)
    keys = [
        [line.key for line in rendered(laid(file(b"".join(cut[:n]))), LOCAL)] for n in range(3, len(cut) + 1)
    ]
    for shorter, longer in zip(keys, keys[1:], strict=False):
        assert set(shorter) <= set(longer)
    assert len({k for line in keys[-1:] for k in line}) == len(keys[-1])  # and no two lines share one


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
