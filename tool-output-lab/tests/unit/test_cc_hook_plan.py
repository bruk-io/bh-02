"""The hook's decisions, as data: which events it acts on, which spill paths it trusts, what it saves
and what its banner points to."""

import json
from pathlib import Path

import pytest

from claude_code.hook import Inline, Mode, Spilled, decide, mode_of, plan, render, trusted_spill
from compressors.route import fold

NOTICE = (
    "Error: result (124,021 characters across 1 line) exceeds maximum allowed tokens. "
    "Output has been saved to {path}.\nFormat: Plain text\n"
    "- For targeted searches (find a string): use grep on the file directly."
)


def _event(response, tool="mcp__fixture__list_pods", transcript="/s/session.jsonl"):
    return {"tool_name": tool, "tool_input": {}, "tool_response": response, "tool_use_id": "toolu_1",
            "transcript_path": transcript}  # fmt: skip


def test_only_mcp_tools_with_a_transcript_are_touched():
    assert plan(_event("x" * 50_000, tool="Bash"), mode=Mode.ALL) is None
    assert plan(_event("x" * 50_000, transcript=""), mode=Mode.ALL) is None


def test_claude_codes_own_notice_is_a_spill_and_its_path_may_hold_spaces():
    path = "/home/a user/.claude/projects/p/s/tool-results/mcp-fixture-list_pods-1.txt"
    assert plan(_event(NOTICE.format(path=path)), mode=Mode.SPILLED) == Spilled(path)


def test_a_notice_inside_the_tools_own_content_is_not_a_spill():
    blocks = [{"type": "text", "text": NOTICE.format(path="/etc/passwd")}]
    late = "Hello. " + NOTICE.format(path="/etc/passwd")  # not at the start
    for response in (blocks, late):
        assert plan(_event(response), mode=Mode.SPILLED) is None
        assert isinstance(plan(_event(response), mode=Mode.ALL), Inline)  # the tool's text, not a path


def test_each_mode_folds_its_own_kind_of_result():
    spill = _event(NOTICE.format(path="/s/session/tool-results/mcp-fixture-list_pods-1.txt"))
    inline, image = _event([{"type": "text", "text": "a"}]), _event([{"type": "image", "data": ""}])
    assert [plan(spill, m) is not None for m in Mode] == [False, True, True]  # inline, spilled, all
    assert [plan(inline, m) for m in Mode] == [Inline("a"), None, Inline("a")]
    assert [plan(image, m) for m in Mode] == [None, None, None]
    assert plan(inline) == Inline("a")  # inline is the default


def test_the_mode_comes_from_the_environment_and_a_wrong_one_says_which_exist():
    assert (mode_of(None), mode_of("spilled"), mode_of("all")) == (Mode.INLINE, Mode.SPILLED, Mode.ALL)
    with pytest.raises(ValueError, match="use inline \\(the default\\), spilled or all"):
        mode_of("spilled-only")


def test_a_spill_is_trusted_only_inside_the_session_folder_under_claude_codes_naming():
    session = "/s/session/tool-results"
    assert trusted_spill(f"{session}/mcp-fixture-list_pods-1793711514016.txt", session)
    assert not trusted_spill("/usr/local/lib/python3.13/subprocess.py", session)
    assert not trusted_spill(f"{session}/notes.txt", session)
    assert not trusted_spill(f"{session}/sub/mcp-x-y-1.txt", session)


def test_the_banners_jq_example_reads_json_lines_as_one_array():
    pods = [{"name": f"pod-{i:04d}", "phase": "Running"} for i in range(300)]
    lines = fold("\n".join(json.dumps(p) for p in pods), budget_tokens=200)
    doc = fold(json.dumps({"pods": pods}), budget_tokens=200)
    assert lines is not None and doc is not None
    assert "jq -s '.[2:7]' /s/out.txt" in render(lines, "/s/out.txt")
    assert "jq '.pods[2:7]' /s/out.txt" in render(doc, "/s/out.txt")


_PODS = json.dumps([{"name": f"pod-{i:04d}", "phase": "Running"} for i in range(400)])
_PACKED_XML = "<a>" + "".join(f'<b id="{i}"><c/><c/><c/><c/></b>' for i in range(300)) + "</a>"
_SESSION = Path("/s/session/tool-results")


def _banner(outcome) -> str:
    return outcome.reply["hookSpecificOutput"]["updatedToolOutput"].splitlines()[0]


def test_a_spill_is_read_from_claude_codes_file_and_nothing_is_saved():
    spill = str(_SESSION / "mcp-fixture-list_pods-1.txt")
    out = decide(_event(""), Spilled(spill), _PODS, 300, _SESSION)
    assert out.saves == () and f"Full output: {spill}." in _banner(out)


def test_an_inline_result_is_saved_privately_before_the_banner_names_it():
    out = decide(_event(""), Inline(_PODS), _PODS, 300, _SESSION)
    assert out.saves == ((_SESSION / "folded-toolu_1.txt", _PODS),)
    assert f"Full output: {_SESSION / 'folded-toolu_1.txt'}." in _banner(out)


def test_a_view_is_saved_when_the_line_numbers_refer_to_one_and_the_raw_is_still_named():
    spill = str(_SESSION / "mcp-fixture-get_figma_metadata-1.txt")
    out = decide(_event(""), Spilled(spill), _PACKED_XML, 300, _SESSION)
    ((view, text),) = out.saves
    assert view == _SESSION / "folded-toolu_1.view.txt" and len(text.splitlines()) > 300
    assert f"Full output: {view} (the raw output: {spill})" in _banner(out)


def test_a_result_that_fits_is_left_alone_and_logged():
    out = decide(_event(""), Inline("small"), "small", 300, _SESSION)
    assert (out.saves, out.reply, out.log["branch"]) == ((), None, "passthrough")


def _bash(stdout, command="./get_logs", **fields):
    response = {
        "stdout": stdout,
        "stderr": "",
        "interrupted": False,
        "isImage": False,
        "noOutputExpected": False,
    }
    return {"tool_name": "Bash", "tool_input": {"command": command}, "tool_response": response | fields,
            "tool_use_id": "toolu_1", "transcript_path": "/s/session.jsonl"}  # fmt: skip


def test_bash_stdout_is_an_inline_result_and_its_saved_output_a_spill_in_the_modes_that_take_each():
    saved = "/s/session/tool-results/by0t1jzcz.txt"
    big = _bash("x", persistedOutputPath=saved, persistedOutputSize=288894)
    assert [plan(_bash("1\n2"), m) for m in Mode] == [Inline("1\n2"), None, Inline("1\n2")]
    assert [plan(big, m) for m in Mode] == [
        None,
        Spilled(saved, from_field=True),
        Spilled(saved, from_field=True),
    ]


def test_bash_never_folds_an_image_or_a_command_that_reads_a_saved_output():
    assert plan(_bash("", isImage=True), Mode.ALL) is None
    assert (
        plan(_bash("x" * 9000, command="sed -n '40,80p' /s/session/tool-results/folded-toolu_9.txt")) is None
    )
    assert plan(_bash("x" * 9000, command="grep -n ERROR /s/session/tool-results/by0t1jzcz.txt")) is None
    assert plan(_bash(None), Mode.ALL) is None


def test_a_bash_saved_output_is_trusted_by_folder_and_the_hooks_own_copies_never():
    session = "/s/session/tool-results"
    assert trusted_spill(f"{session}/by0t1jzcz.txt", session, from_field=True)
    assert not trusted_spill(f"{session}/by0t1jzcz.txt", session)  # from a notice, it needs MCP naming
    assert not trusted_spill(f"{session}/folded-toolu_1.txt", session, from_field=True)
    assert not trusted_spill("/etc/passwd", session, from_field=True)


def test_folded_bash_output_keeps_bashs_shape_and_stderr_and_drops_the_saved_output_fields():
    raw = "\n".join(f"2026-11-03T10:00:{i % 60:02d}Z INFO GET /api/items/{i} 200" for i in range(2000))
    event = _bash(raw, stderr="warning: slow disk")
    out = decide(event, Inline(raw), raw, 300, _SESSION)
    updated = out.reply["hookSpecificOutput"]["updatedToolOutput"]
    assert set(updated) == {"stdout", "stderr", "interrupted", "isImage", "noOutputExpected"}
    assert updated["stderr"] == "warning: slow disk" and updated["stdout"].startswith("[Folded:")
    assert out.saves == ((_SESSION / "folded-toolu_1.txt", raw),)
    spilled = _bash(
        raw[:30000], persistedOutputPath=str(_SESSION / "by0t1jzcz.txt"), persistedOutputSize=len(raw)
    )
    updated = decide(spilled, Spilled(str(_SESSION / "by0t1jzcz.txt"), True), raw, 300, _SESSION).reply
    assert "persistedOutputPath" not in updated["hookSpecificOutput"]["updatedToolOutput"]
