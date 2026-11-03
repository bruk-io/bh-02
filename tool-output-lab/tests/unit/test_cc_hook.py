import json
import random

from claude_code.hook import Inline, Spilled, handle, plan
from harness.needle import json_case

_NOTICE = (
    "Error: result (124,021 characters across 1 line) exceeds maximum allowed tokens. Output has been saved "
    "to /root/.claude/projects/p/s/tool-results/mcp-fixture-list_pods-1.txt.\nFormat: Plain text\n"
    "- For targeted searches (find a string): use grep on the file directly."
)


def _event(response, tool="mcp__fixture__list_pods", transcript="/tmp/t/session.jsonl"):
    return {
        "tool_name": tool,
        "tool_input": {"namespace": "default"},
        "tool_response": response,
        "tool_use_id": "toolu_1",
        "transcript_path": transcript,
    }


def test_only_mcp_tools_are_touched():
    assert plan(_event("x" * 50_000, tool="Bash")) is None


def test_claude_codes_spill_notice_is_read_as_a_path():
    assert plan(_event(_NOTICE)) == Spilled(
        "/root/.claude/projects/p/s/tool-results/mcp-fixture-list_pods-1.txt"
    )


def test_text_blocks_are_joined_and_other_content_is_left_alone():
    assert plan(_event([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])) == Inline("a\nb")
    assert plan(_event([{"type": "image", "data": ""}])) is None


def test_a_small_result_is_left_alone(tmp_path):
    assert handle(_event('{"items": []}', transcript=str(tmp_path / "s.jsonl")), budget=2000) is None


def test_an_inline_result_is_saved_and_replaced_with_the_fold(tmp_path):
    case = json_case("rare_value", 50, 0.5, random.Random(1))
    reply = handle(_event(case.raw, transcript=str(tmp_path / "s.jsonl")), budget=500)
    text = reply["hookSpecificOutput"]["updatedToolOutput"]
    saved = tmp_path / "s" / "tool-results" / "folded-toolu_1.txt"
    assert saved.read_text() == case.raw
    assert str(saved) in text.splitlines()[0]
    assert "jq '.items[2:7]'" in text.splitlines()[0]
    assert case.needle in text


def test_a_spilled_result_is_folded_from_claude_codes_file(tmp_path):
    case = json_case("error_key", 500, 0.5, random.Random(2))
    spill = tmp_path / "spill.txt"
    spill.write_text(case.raw)
    reply = handle(
        _event(
            _NOTICE.replace("/root/.claude/projects/p/s/tool-results/mcp-fixture-list_pods-1.txt", str(spill))
        ),
        budget=2000,
    )
    text = reply["hookSpecificOutput"]["updatedToolOutput"]
    assert str(spill) in text.splitlines()[0]
    assert case.needle in text
    assert json.loads(text.split("\n", 1)[1])["items"][0]["namespace"] == "default"
