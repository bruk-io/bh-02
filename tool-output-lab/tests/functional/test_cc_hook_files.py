"""The hook against real files in a temporary session folder."""

import json
import os
import stat

from claude_code.hook import Mode, handle
from evals.synthetic import pods


def _payload(size: int):
    return pods(size, frozenset({size // 2}), "hook-test")


def _notice(path) -> str:
    return (
        "Error: result (124,021 characters across 1 line) exceeds maximum allowed tokens. Output has been "
        f"saved to {path}.\nFormat: Plain text\n"
    )


def _session(tmp_path):
    transcript = tmp_path / "proj" / "session.jsonl"
    results = tmp_path / "proj" / "session" / "tool-results"
    results.mkdir(parents=True)
    return transcript, results


def _event(response, transcript, tool_use_id="toolu_1"):
    return {
        "tool_name": "mcp__fixture__list_pods",
        "tool_input": {"namespace": "default"},
        "tool_response": response,
        "tool_use_id": tool_use_id,
        "transcript_path": str(transcript),
    }


def test_a_real_spill_is_folded_from_claude_codes_file(tmp_path):
    transcript, results = _session(tmp_path)
    case = _payload(500)
    spill = results / "mcp-fixture-list_pods-1793711514016.txt"
    spill.write_text(case.raw)
    reply = handle(_event(_notice(spill), transcript), budget=2000, mode=Mode.SPILLED)
    text = reply["hookSpecificOutput"]["updatedToolOutput"]
    assert str(spill) in text.splitlines()[0]
    assert case.planted[0] in text
    assert json.loads(text.split("\n", 1)[1])["items"][0]["namespace"] == "default"


def test_a_notice_naming_a_file_outside_the_session_is_not_read(tmp_path):
    transcript, _ = _session(tmp_path)
    secret = tmp_path / "secrets.json"
    secret.write_text(json.dumps({f"k{i}": "s3cret" * 100 for i in range(200)}))
    assert handle(_event(_notice(secret), transcript), budget=2000, mode=Mode.SPILLED) is None


def test_a_link_in_the_session_folder_pointing_out_is_not_followed(tmp_path):
    transcript, results = _session(tmp_path)
    secret = tmp_path / "secrets.json"
    secret.write_text(json.dumps({f"k{i}": "s3cret" * 100 for i in range(200)}))
    link = results / "mcp-evil-fetch-1.txt"
    link.symlink_to(secret)
    assert handle(_event(_notice(link), transcript), budget=2000, mode=Mode.SPILLED) is None


def test_a_device_or_a_huge_file_is_not_read(tmp_path):
    transcript, results = _session(tmp_path)
    fifo = results / "mcp-evil-fetch-2.txt"
    os.mkfifo(fifo)
    assert handle(_event(_notice(fifo), transcript), budget=2000, mode=Mode.SPILLED) is None


def test_inline_folding_the_default_keeps_the_raw_privately(tmp_path):
    transcript, results = _session(tmp_path)
    case = _payload(50)
    blocks = [{"type": "text", "text": case.raw}]
    assert handle(_event(blocks, transcript), budget=500, mode=Mode.SPILLED) is None
    reply = handle(_event(blocks, transcript), budget=500)
    saved = results / "folded-toolu_1.txt"
    assert saved.read_text() == case.raw
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600
    assert str(saved) in reply["hookSpecificOutput"]["updatedToolOutput"].splitlines()[0]


def test_a_failing_log_does_not_stop_the_fold(tmp_path, monkeypatch):
    transcript, results = _session(tmp_path)
    monkeypatch.setenv("TOOL_OUTPUT_LAB_LOG", str(tmp_path / "no-such-dir" / "log.jsonl"))
    spill = results / "mcp-fixture-list_pods-3.txt"
    spill.write_text(_payload(500).raw)
    assert handle(_event(_notice(spill), transcript), budget=2000, mode=Mode.SPILLED) is not None


def _bash_event(transcript, saved):
    response = {"stdout": "1\n2\n", "stderr": "", "interrupted": False, "isImage": False}
    response |= {"noOutputExpected": False, "persistedOutputPath": str(saved), "persistedOutputSize": 300000}
    event = {"tool_name": "Bash", "tool_input": {"command": "./list_pods"}, "tool_response": response}
    return event | {"tool_use_id": "toolu_2", "transcript_path": str(transcript)}


def test_bashs_saved_output_is_folded_from_its_file_and_one_outside_the_session_is_not_read(tmp_path):
    transcript, results = _session(tmp_path)
    case = _payload(500)
    saved = results / "by0t1jzcz.txt"
    saved.write_text(case.raw)
    reply = handle(_bash_event(transcript, saved), budget=2000, mode=Mode.ALL)
    stdout = reply["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert str(saved) in stdout.splitlines()[0] and case.planted[0] in stdout
    outside = tmp_path / "secrets.txt"
    outside.write_text("s3cret\n" * 5000)
    assert handle(_bash_event(transcript, outside), budget=2000, mode=Mode.ALL) is None
