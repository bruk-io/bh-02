import difflib
import json

import pytest

from claude_code.hook import Mode, mode_of
from evals.l2 import (
    BASH_CONDITIONS,
    HOOK_MODE,
    MCP_CONDITIONS,
    implied_input_price,
    merged,
    parse_stream,
    patched,
    report,
    rescored,
)
from evals.real import renamed
from evals.truth import Edited, Items


def _stream() -> list[str]:
    def assistant(mid, blocks, usage):
        return json.dumps({"type": "assistant", "message": {"id": mid, "content": blocks, "usage": usage}})

    u1 = {
        "input_tokens": 5,
        "cache_read_input_tokens": 20000,
        "cache_creation_input_tokens": 3000,
        "output_tokens": 40,
    }
    u2 = {
        "input_tokens": 2,
        "cache_read_input_tokens": 23000,
        "cache_creation_input_tokens": 4000,
        "output_tokens": 60,
    }
    return [
        assistant("m1", [{"type": "tool_use", "name": "ToolSearch", "input": {}}], u1),
        assistant("m1", [{"type": "tool_use", "name": "mcp__fixture__list_pods", "input": {}}], u1),
        assistant(
            "m2",
            [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "lab-fold x.py | jq . a/tool-results/b.txt"},
                }
            ],
            u2,
        ),
        json.dumps(
            {
                "type": "result",
                "result": "...\nANSWER: web-1",
                "num_turns": 3,
                "total_cost_usd": 0.01,
                "duration_ms": 9000,
            }
        ),
    ]


def test_a_session_is_read_per_request_with_its_final_context():
    s = parse_stream(_stream())
    assert (s.tool_calls, s.read_saved_file, s.ran_fold, s.requests) == (2, True, True, 2)
    assert (s.input_tokens, s.cache_read, s.cache_write, s.output_tokens) == (7, 43000, 7000, 100)
    assert s.final_context == 2 + 23000 + 4000
    assert s.answer.endswith("ANSWER: web-1") and s.error is None


def _rows(n: int = 5) -> list[dict]:
    rows = []
    for i in range(n):
        for cond, correct, ctx in (("native", True, 50000), ("fold", True, 30000)):
            row = {
                "task_id": f"json-M-spot-{i}",
                "fmt": "json",
                "kind": "spot",
                "band": "M",
                "condition": cond,
            }
            row |= {"rep": 0, "correct": correct, "parsed": True, "cost_usd": 0.01, "final_context": ctx}
            rows.append(
                row
                | {
                    "tool_calls": 2,
                    "duration_ms": 9000,
                    "error": None,
                    "read_saved_file": False,
                    "ran_fold": False,
                    "input_tokens": 10,
                    "cache_read": ctx,
                    "cache_write": 0,
                    "output_tokens": 50,
                    "requests": 2,
                }
            )
    return rows


def test_the_report_pairs_conditions_and_five_agreeing_pairs_cannot_show_accuracy_kept():
    text = report(_rows(), "test")
    assert "| json | M | fold | 5 | +0% [" in text and "| 0/0, p 1.00 |" in text
    assert "undecided (indicative: under 30 pairs)" in text


def test_enough_agreeing_pairs_and_a_smaller_context_pass():
    text = report(_rows(150), "test")  # 150 pairs, all right: the interval's lower bound is -2.5 points
    assert "| json | M | fold | 150 | +0% [-2%, +2%] | 0/0, p 1.00 |" in text and "| passes |" in text
    assert "| M | fold | 150 | +0%" in text  # every format together
    assert "| -20000 [-20000, -20000] | -20000 [-20000, -20000] |" in text  # final context and input


def test_a_run_that_failed_to_answer_is_listed_not_scored_or_paired():
    rows = _rows()
    rows[1] |= {
        "correct": False,
        "cost_usd": 0.0,
        "final_context": 0,
        "error": "no result event",
    }  # a fold run
    text = report(rows, "test")
    assert "9 scored, 1 failed to answer" in text
    assert "| json | spot | M | fold | 4/4" in text and "| json | M | fold | 4 | +0%" in text
    assert "- json-M-spot-0 fold: no result event" in text


def _result(**fields) -> list[str]:
    return [json.dumps({"type": "result", "result": "", "num_turns": 25, **fields})]


def test_an_api_or_usage_error_is_a_failed_run_and_running_out_of_turns_is_a_wrong_answer():
    limit = parse_stream(_result(is_error=True, subtype="success", result="Claude AI usage limit reached"))
    assert limit.error == "success: Claude AI usage limit reached"
    crash = parse_stream(_result(is_error=True, subtype="error_during_execution"))
    assert crash.error is not None and crash.error.startswith("error_during_execution")
    turns = parse_stream(_result(is_error=True, subtype="error_max_turns"))
    assert turns.error is None and turns.hit_max_turns
    assert parse_stream([]).error == "no result event"


def test_runs_merge_into_one_report_and_a_repeated_repetition_is_refused():
    first, later = _rows(2), [r | {"rep": 1} for r in _rows(2)]
    for r in first + later:
        r["model"] = "m"
    assert len(merged({"a": first, "b": later})) == 8
    with pytest.raises(ValueError, match="run later repetitions with --first-rep"):
        merged({"a": first, "b": first})
    with pytest.raises(ValueError, match="different models"):
        merged({"a": first, "b": [r | {"rep": 1, "model": "n"} for r in first]})


def test_a_saved_run_is_rescored_from_its_answer_line_and_a_failed_one_is_left_alone():
    truth = Items(frozenset({"Card N7697"}), frozenset({"Card N7697", "Card M4557"}))
    row = {"error": None, "answer_line": "N7697", "answer": "...", "correct": False}
    assert rescored(row, truth)["correct"]
    failed = row | {"error": "no result event"}
    assert rescored(failed, truth) is failed


def test_every_hook_condition_names_a_mode_the_hook_accepts():
    assert set(HOOK_MODE) == (set(MCP_CONDITIONS) | set(BASH_CONDITIONS)) - {"native", "bash-native"}
    assert {mode_of(m) for m in HOOK_MODE.values()} == set(Mode)


def test_noshell_fold_is_paired_against_noshell_and_noshell_against_native():
    rows = []
    for cond, ctx in (("native", 50000), ("noshell", 48000), ("noshell-fold", 40000)):
        for r in _rows(3):
            if r["condition"] == "native":
                rows.append(r | {"condition": cond, "final_context": ctx, "cache_read": ctx, "fmt": "python"})
    text = report(rows, "test")
    assert "| python | M | noshell-fold (against noshell) | 3 |" in text and "| -8000 [" in text
    assert "| python | M | noshell | 3 |" in text and "| -2000 [" in text


def test_an_edit_is_checked_again_on_its_file_rebuilt_from_the_saved_diff():
    original = "class A:\n    def m(self):\n        return self.m()\n" + "x = 1\n" * 50
    edited = original.replace("m(", "n(")
    diff = "".join(difflib.unified_diff(original.splitlines(True), edited.splitlines(True), n=1))
    assert patched(original, diff) == edited and patched(original, "") == original
    assert patched(original.replace("x = 1", "y = 2", 1), diff) is None  # its context line changed
    assert patched("something else\n", diff) is None
    truth = Edited("def m", renamed("m", "n"))
    row = {
        "error": None,
        "kind": "edit",
        "answer_line": "done",
        "answer": "",
        "correct": False,
        "edit_diff": diff,
    }
    assert rescored(row, truth, original)["correct"]
    assert rescored(row | {"edit_diff_cut": True}, truth, original) == row | {"edit_diff_cut": True}
    assert rescored(row, truth) is row  # no original to rebuild from


def test_runs_folded_with_different_settings_are_not_merged():
    first = [r | {"model": "m", "view": "schema", "config": "defaults"} for r in _rows(2)]
    later = [r | {"model": "m", "rep": 1, "view": "schema", "config": "schema.rare=0.2"} for r in _rows(2)]
    with pytest.raises(ValueError, match="folded with different settings"):
        merged({"a": first, "b": later})


def test_a_runs_cost_implies_the_input_price_under_the_price_structure():
    # one real Haiku run: 4 uncached, 18,094 one-hour writes, 69,315 reads, 139 out, $0.00438185
    row = {"input_tokens": 4, "cache_write": 18094, "cache_write_1h": 18094, "cache_read": 69315}
    row |= {"output_tokens": 139, "cost_usd": 0.00438185}
    assert round(implied_input_price(row) * 1e6, 5) == 0.1  # exactly $0.10 per million: the structure holds


def test_the_report_has_a_cache_section_with_what_each_later_request_pays():
    text = report(_rows(40), "test")
    assert "## Cache and requests" in text and "| M | fold | 40 |" in text.split("## Cache and requests")[1]
    assert "-20,000 tokens" in text
