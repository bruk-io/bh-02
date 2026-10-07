"""`/compact` booted from the shipped layers: a real loop, transcript, kernel and loader; only the
model is a fake, which runs scripted inputs and answers bh-02's summary request."""

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path

from bh_02.bootstrap import layers, run


async def test_compact_begins_a_new_conversation_from_the_summary_and_the_kernel_keeps_its_namespace(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """An input sets `x`; `/compact` asks the model for a summary (the conversation as the loop
    sends it, the one tool offered) and writes the new conversation over the transcript's file,
    the old kept as `.bak`; the loop and the transcript restart, and the next input still reads
    `x`, since the kernel was not restarted. The next request begins with the prompt as it reads
    now, then bh-02's note and the summary, and holds nothing of the old conversation."""
    history = tmp_path / "transcript.jsonl"
    patch = composition(
        '[[plugin]]\nid = "model"\nuse = "fragile:compacting_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:scripted_ui"\n'
        f'[[plugin]]\nid = "transcript"\nconfig = {{ path = "{history}" }}\n'
    )
    import fragile  # the module the fixture wrote, imported by the composition

    fragile.script("py:x = 6 * 7", "/compact", "py:print(x)", "and now?")
    fragile.answers(True, True)  # unjailed: each input is put to the person
    await asyncio.wait_for(run([*layers(), patch]), 30)

    (note,) = [n for n in fragile.NOTES if n.startswith("the conversation was compacted")]
    assert note.endswith(f"the old transcript is {history}.bak):\n\nSUMMARY: x holds 42")
    assert "ran: 42" in fragile.shown()  # the namespace outlived the compaction
    (asked,) = [(m, tools) for m, tools in fragile.SENT if str(m[-1]["content"]).startswith("(bh-02: the")]
    messages, tools = asked
    assert tools == ["python"] and messages[0]["role"] == "system"  # as the loop sends it
    assert any(str(m["content"]).endswith("py:x = 6 * 7") for m in messages)  # the old conversation
    last, _ = fragile.SENT[-1]  # the request for "and now?"
    assert [m["role"] for m in last] == [
        "system",  # the prompt as it reads now
        "user",  # bh-02: this conversation carries on from an earlier one ...
        "assistant",  # the summary
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
    ]
    assert str(last[1]["content"]).startswith("(bh-02: this conversation carries on from an earlier one")
    assert last[2]["content"] == "SUMMARY: x holds 42"
    assert str(last[3]["content"]).startswith("(Today's date: ")  # told again in the new one
    assert not any("6 * 7" in str(m["content"]) for m in last)
    kept = [json.loads(line) for line in history.read_text().splitlines()]
    assert kept[:2] == last[1:3] and kept[2]["role"] == "system"  # the prompt, kept when first read
    assert "py:x = 6 * 7" in Path(f"{history}.bak").read_text()


async def test_quitting_while_the_model_writes_the_summary_ends_bh_02_at_once_and_changes_nothing(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The ui ending (Ctrl-Q, /exit, the terminal gone) stops /compact as it stops a reply: the
    summary step is closed, so its provider stops, nothing is written, and bh-02 ends rather
    than wait out the step."""
    history = tmp_path / "transcript.jsonl"
    patch = composition(
        '[[plugin]]\nid = "model"\nuse = "fragile:slow_summary_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:quitting_ui"\n'
        f'[[plugin]]\nid = "transcript"\nconfig = {{ path = "{history}" }}\n'
    )
    import fragile  # the module the fixture wrote, imported by the composition

    fragile.script("hello", "/compact")
    started = time.monotonic()
    await asyncio.wait_for(run([*layers(), patch]), 30)
    assert time.monotonic() - started < 15  # not the minute the summary would take
    assert fragile.CLOSED == [True]  # the step was closed
    assert "hello" in history.read_text() and not (tmp_path / "transcript.jsonl.bak").exists()
    assert not [n for n in fragile.NOTES if n.startswith("the conversation was compacted")]


async def test_however_many_usage_events_the_summary_sends_its_whole_answer_is_shown(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The restart is queued only once the answer is read to its end: an output that gives the
    loop a turn after every event (as the app's does) is shown `cleared`, the note carrying the
    summary and `restarting`, however many usage events come before them."""
    history = tmp_path / "transcript.jsonl"
    patch = composition(
        '[[plugin]]\nid = "model"\nuse = "fragile:compacting_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:drawing_ui"\n'
        f'[[plugin]]\nid = "transcript"\nconfig = {{ path = "{history}" }}\n'
    )
    import fragile  # the module the fixture wrote, imported by the composition

    fragile.script("hello", "/compact", "and now?")
    fragile.usages(16)
    await asyncio.wait_for(run([*layers(), patch]), 30)
    start = fragile.DRAWN.index("usage")
    assert fragile.DRAWN[start : start + 19] == ["usage"] * 16 + ["cleared", "note", "restarting"]
    (note,) = [n for n in fragile.NOTES if n.startswith("the conversation was compacted")]
    assert note.endswith("SUMMARY: x holds 42")
    last, _ = fragile.SENT[-1]  # the request for "and now?", in the new conversation
    assert last[2]["content"] == "SUMMARY: x holds 42"
