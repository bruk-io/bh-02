"""What events, lifecycle changes and a jail's grades say: text, or Content styled in theme tokens."""

from textual.content import Content

from tui_cordis_plugin import render


def _styles(content: Content) -> dict[str, str]:
    """Each styled run of text in `content`, and its style."""
    return {content.plain[span.start : span.end]: str(span.style) for span in content.spans}


def test_a_cell_is_its_name_over_its_code_highlighted_and_other_calls_one_line() -> None:
    cell = {"name": "python", "input": {"code": "x = 1\nprint(x)"}}
    assert render.tool_call_head(cell) == "python"
    code = render.tool_call_code(cell)
    assert code is not None and code.plain == "x = 1\nprint(x)"
    assert _styles(code).get("print", "").startswith("$")  # highlighted, in the theme's tokens
    invented = {"name": "read_file", "input": {"path": "a.txt"}}  # a call a model made up
    assert render.tool_call_head(invented) == "read_file(path='a.txt')"
    assert render.tool_call_code(invented) is None


def test_long_code_is_cut_and_says_how_much() -> None:
    code = render.tool_call_code({"name": "python", "input": {"code": "\n".join(map(str, range(45)))}})
    assert code is not None and code.plain.splitlines()[-2:] == ["39", "… 5 more lines"]


def test_a_long_result_is_cut_to_a_glance() -> None:
    body = render.tool_result_body({"content": "\n".join(str(n) for n in range(20))})
    assert body.plain.splitlines() == [*map(str, range(12)), "… 8 more lines"]
    assert _styles(body) == {"\n… 8 more lines": "$text-muted"}
    assert render.tool_result_body({"content": ""}).plain == "(no output)"


def test_a_unified_diff_is_coloured_line_by_line() -> None:
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n keep\n-old\n+new"
    body = render.tool_result_body({"content": diff, "is_error": False})
    assert body.plain == diff
    assert _styles(body) == {
        "--- a/x.py": "bold",
        "+++ b/x.py": "bold",
        "@@ -1,2 +1,2 @@": "$text-accent",
        "-old": "$text-error",
        "+new": "$text-success",
    }
    # an error is never read as a diff (its colour is the widget's), and text with a stray
    # `+` or `-` is not a diff without a hunk header
    assert render.tool_result_body({"content": diff, "is_error": True}).spans == []
    assert render.tool_result_body({"content": "-1\n+2"}).spans == []


def test_markdown_ish_prose() -> None:
    text = "# Plan\nuse `x` **now**, *not* later\n- one\n2. two\n> quoted\nplain_snake_case * 2"
    shown = render.markdown(text)
    assert shown.plain == "Plan\nuse x now, not later\n• one\n• two\n▎ quoted\nplain_snake_case * 2"
    styles = _styles(shown)
    assert styles["Plan"] == "bold $text-primary" and styles["x"] == "$text-accent"
    assert styles["now"] == "bold" and styles["not"] == "italic"
    assert "snake" not in "".join(styles)  # underscores and a lone `*` are left alone


def test_a_fenced_block_is_highlighted_and_its_fences_hidden() -> None:
    shown = render.markdown("look:\n```python\nimport os\n```\ndone")
    assert shown.plain == "look:\nimport os\ndone"
    assert _styles(shown).get("import", "").startswith("$")


def test_a_reply_can_be_drawn_in_pieces_split_at_any_line() -> None:
    """A streamed reply is settled into pieces; a piece that ends inside a fence hands the
    fence to the next one, so the code is still drawn as code."""
    text = "intro\n```python\na = 1\nb = 2\n```\nafter"
    lines = text.split("\n")
    whole = render.markdown(text)
    for cut in range(1, len(lines)):
        head, tail = "\n".join(lines[:cut]), "\n".join(lines[cut:])
        pieces = [render.markdown(head), render.markdown(tail, render.fence_after(head))]
        assert "\n".join(p.plain for p in pieces if p.plain) == whole.plain, cut
    assert render.fence_after("```py\nx = 1") == "py"
    assert render.fence_after("```\nx\n```") is None


def test_a_piece_settles_once_it_holds_enough_full_lines() -> None:
    assert render.settle_point("a\nb", 2, 100) == 0  # one full line: keep growing
    assert render.settle_point("a\nb\nc", 2, 100) == 4  # past the last full line
    assert render.settle_point("a\nb\n", 2, 100) == 4
    assert render.settle_point("a\nb\nc\nd", 2, 100) == 4  # never more than `limit` lines at once


def test_a_long_paragraph_settles_at_a_space_once_it_is_long_enough() -> None:
    words = "word " * 30  # 150 characters, no newline
    assert render.settle_point(words[:40], 24, 50) == 0  # short: keep growing
    assert render.settle_point(words, 24, 48) == 45  # after the last space before 48
    assert render.settle_point("intro\n" + words, 24, 50) == 6  # a line end before it wins
    assert render.settle_point("x" * 120, 24, 50) == 50  # no space at all: a hard cut


def test_usage_and_stops() -> None:
    usage = {"input_tokens": 1200, "output_tokens": 30, "cost_usd": 0.01}
    assert render.usage_line(usage) == "1,200 in · 30 out · $0.0100"
    cached = {"input_tokens": 6393, "output_tokens": 5, "cache_read_input_tokens": 6378, "cost_usd": 0.0007}
    assert render.usage_line(cached) == "6,393 in · 6,378 cached · 5 out · $0.0007"
    read = {"input_tokens": 8119, "output_tokens": 0, "cache_read_input_tokens": 8062, "cost_usd": 0.0009}
    started = read | {"partial": True}  # what was read, sent as the turn started
    assert render.usage_line(started) == "8,119 in · 8,062 cached · output not counted · $0.0009 for input"
    rest = {"input_tokens": 0, "output_tokens": 150, "cost_usd": 0.0008}
    whole = render.usage_sum(started, rest)  # the output count came: the turn is whole
    assert "partial" not in whole and render.usage_line(whole).endswith("150 out · $0.0017")
    assert render.usage_sum(started, started)["partial"] is True  # nothing brought it yet
    assert render.is_quiet_stop({"reason": "end_turn"})
    assert not render.is_quiet_stop({"reason": "interrupted"})
    assert render.stop_line({"reason": "interrupted"}) == "stopped: interrupted"


def test_only_a_reload_or_a_failure_is_worth_a_note() -> None:
    assert render.lifecycle_line("active", "loop", None, seen=False) is None  # starting up
    assert render.lifecycle_line("active", "loop", None, seen=True) == "↻ loop reloaded"
    assert render.lifecycle_line("failed", "kernel", "boom", seen=False) == "✗ kernel failed: boom"
    assert render.lifecycle_line("bind", "loop", None, seen=True) is None


def test_an_approval_names_the_cell_and_shows_its_code_whole() -> None:
    cell = {"name": "python", "input": {"code": "a = 1\nb = 2"}}
    assert render.approval_title(cell) == "Run this python cell (2 lines)?"
    assert render.approval_lines(cell) == ["a = 1", "b = 2"]
    empty = {"name": "python", "input": {"code": ""}}
    assert render.approval_title(empty) == "Run this python cell (0 lines)?"
    assert render.approval_lines(empty) == []
    # a request about something other than a cell (an extension to load) asks its own question
    asked = {"name": "extension", "title": "Load extension todo, unjailed?", "input": {"code": "x = 1"}}
    assert render.approval_title(asked) == "Load extension todo, unjailed (1 line)?"
    assert render.approval_lines(asked) == ["x = 1"]


def test_the_jail_in_a_status_bar() -> None:
    graded = {"fs_write": "enforced", "network": "enforced", "fs_read": "best_effort", "limits": "unenforced"}
    assert render.jail_forms(True, graded) == (
        "jailed fs_write ✓ network ✓ fs_read ~",
        "jailed w✓ n✓ r~",
        "jailed w✓n✓r~",
        "jailed ✓✓~",
    )
    assert render.jail_forms(False, {"fs_write": "unenforced"})[0] == "unjailed fs_write ✗"
    assert render.jail_forms(False, {}) == ("unjailed",)


def test_the_session_field_s_short_form_is_the_id_s_last_part_which_resume_takes() -> None:
    assert render.session_forms("20260923-011910-58d9") == ("20260923-011910-58d9", "58d9")
    resumed = render.session_forms("20260923-011910-58d9", resumed=True)
    assert resumed == ("20260923-011910-58d9 (resumed)", "58d9 ↻")
