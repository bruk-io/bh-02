"""The hook's decisions, as data: which events it acts on, and which spill paths it trusts."""

from claude_code.hook import Inline, Spilled, plan, trusted_spill

NOTICE = (
    "Error: result (124,021 characters across 1 line) exceeds maximum allowed tokens. "
    "Output has been saved to {path}.\nFormat: Plain text\n"
    "- For targeted searches (find a string): use grep on the file directly."
)


def _event(response, tool="mcp__fixture__list_pods", transcript="/s/session.jsonl"):
    return {"tool_name": tool, "tool_input": {}, "tool_response": response, "tool_use_id": "toolu_1",
            "transcript_path": transcript}  # fmt: skip


def test_only_mcp_tools_with_a_transcript_are_touched():
    assert plan(_event("x" * 50_000, tool="Bash"), fold_inline=True) is None
    assert plan(_event("x" * 50_000, transcript=""), fold_inline=True) is None


def test_claude_codes_own_notice_is_a_spill_and_its_path_may_hold_spaces():
    path = "/home/a user/.claude/projects/p/s/tool-results/mcp-fixture-list_pods-1.txt"
    assert plan(_event(NOTICE.format(path=path))) == Spilled(path)


def test_a_notice_inside_the_tools_own_content_is_not_a_spill():
    blocks = [{"type": "text", "text": NOTICE.format(path="/etc/passwd")}]
    assert plan(_event(blocks)) is None  # inline output, and inline folding is off by default
    assert isinstance(plan(_event(blocks), fold_inline=True), Inline)
    assert plan(_event("Hello. " + NOTICE.format(path="/etc/passwd"))) is None  # not at the start


def test_inline_results_are_left_alone_unless_asked():
    assert plan(_event([{"type": "text", "text": "a"}])) is None
    assert plan(_event([{"type": "text", "text": "a"}]), fold_inline=True) == Inline("a")
    assert plan(_event([{"type": "image", "data": ""}]), fold_inline=True) is None


def test_a_spill_is_trusted_only_inside_the_session_folder_under_claude_codes_naming():
    session = "/s/session/tool-results"
    assert trusted_spill(f"{session}/mcp-fixture-list_pods-1793711514016.txt", session)
    assert not trusted_spill("/usr/local/lib/python3.13/subprocess.py", session)
    assert not trusted_spill(f"{session}/notes.txt", session)
    assert not trusted_spill(f"{session}/sub/mcp-x-y-1.txt", session)
