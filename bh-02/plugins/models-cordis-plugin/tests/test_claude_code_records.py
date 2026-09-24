"""The transcript as a Claude Code session file: pure records, and where they are written."""

import json
from datetime import UTC, datetime
from pathlib import Path

from models_cordis_plugin.claude_code import project_dir, records_for, session_file, write_session

_NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
_TRANSCRIPT = [
    {"role": "user", "content": "run it"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "t1", "name": "python", "input": {"code": "1"}}],
        "provider": {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "hm", "signature": "sig"},
                {"type": "tool_use", "id": "t1", "name": "python", "input": {"code": "1"}},  # anthropic-era
            ],
        },
    },
    {"role": "tool", "content": "1", "call_id": "t1"},
    {"role": "assistant", "content": "done"},  # no provider: from text
    {"role": "assistant", "content": ""},  # a silent step: nothing to write
    {"role": "user", "content": "more"},
]


def test_records_are_a_linear_chain_in_claude_code_s_shape() -> None:
    ids = [f"id-{n}" for n in range(len(_TRANSCRIPT))]
    records = records_for(_TRANSCRIPT, session="s1", cwd="/w", model="claude-sonnet-5", now=_NOW, ids=ids)
    assert [r["type"] for r in records] == ["user", "assistant", "user", "assistant", "user"]
    assert [r["parentUuid"] for r in records] == [None, "id-0", "id-1", "id-2", "id-3"]
    assert all(r["sessionId"] == "s1" and r["cwd"] == "/w" for r in records)
    assert records[0]["message"] == {"role": "user", "content": "run it"}
    thinking, call = records[1]["message"]["content"]
    assert thinking["signature"] == "sig" and call["name"] == "mcp__bh__python"  # prefixed for Claude Code
    assert (
        records[1]["message"]["model"] == "claude-sonnet-5"
        and records[1]["message"]["stop_reason"] == "tool_use"
    )
    assert records[2]["message"]["content"] == [
        {"tool_use_id": "t1", "type": "tool_result", "content": [{"type": "text", "text": "1"}]}
    ]
    assert records[3]["message"]["content"] == [{"type": "text", "text": "done"}]
    assert records[4]["uuid"] == "id-5" and records[4]["parentUuid"] == "id-3"


def test_the_project_directory_is_the_cwd_with_non_alphanumerics_as_dashes(tmp_path: Path) -> None:
    assert project_dir(tmp_path, "/Users/me/my.project") == tmp_path / "projects" / "-Users-me-my-project"
    long = "/" + "x" * 250
    assert project_dir(tmp_path, long) is None  # Claude Code's own hash follows the cut
    seen = tmp_path / "projects" / ("-" + "x" * 199 + "-abc123")
    seen.mkdir(parents=True)
    assert project_dir(tmp_path, long) == seen


def test_write_session_writes_a_new_file_each_time(tmp_path: Path) -> None:
    first = write_session(tmp_path, "/w", _TRANSCRIPT, "claude-sonnet-5")
    second = write_session(tmp_path, "/w", _TRANSCRIPT, "claude-sonnet-5")
    assert first and second and first != second
    found = session_file(tmp_path, first)
    assert found == tmp_path / "projects" / "-w" / f"{first}.jsonl"
    lines = [json.loads(line) for line in found.read_text().splitlines()]
    assert len(lines) == 5 and lines[0]["sessionId"] == first
    assert session_file(tmp_path, "no-such-session") is None


def test_an_openai_model_s_turn_is_rebuilt_from_the_transcript_s_text_and_calls() -> None:
    """After `/model sonnet` from an OpenAI-compatible model, its turns carry that API's
    message (`content` a string, arguments as JSON text): Claude Code gets them rebuilt."""
    openai_turn = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call_1", "name": "python", "input": {"code": "print(1)"}}],
        "provider": {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "python", "arguments": '{"code": "print(1)"}'},
                }
            ],
        },
    }
    transcript = [
        {"role": "user", "content": "run it"},
        openai_turn,
        {"role": "tool", "content": "1", "call_id": "call_1"},
        {
            "role": "assistant",
            "content": "it said 1",
            "provider": {"role": "assistant", "content": "it said 1"},
        },
    ]
    records = records_for(
        transcript, session="s", cwd="/w", model="claude-sonnet-5", now=_NOW, ids=list("abcd")
    )
    (call,) = records[1]["message"]["content"]
    assert call == {
        "type": "tool_use",
        "id": "call_1",
        "name": "mcp__bh__python",
        "input": {"code": "print(1)"},
    }
    assert records[3]["message"]["content"] == [{"type": "text", "text": "it said 1"}]
