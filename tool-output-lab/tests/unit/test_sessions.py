import json

from evals.dials import Setting
from evals.l2 import Dials
from evals.sessions import report, split_turns


def test_a_session_splits_into_turns_at_each_result_and_drops_an_unfinished_one():
    lines = [
        json.dumps({"type": "system"}),
        json.dumps({"type": "assistant", "message": {"id": "a"}}),
        json.dumps({"type": "result", "result": "ANSWER: 7"}),
        "not json",
        json.dumps({"type": "result", "result": "ANSWER: 8"}),
        json.dumps({"type": "assistant", "message": {"id": "b"}}),
    ]
    turns = split_turns(lines)
    assert [len(t) for t in turns] == [3, 2]
    assert json.loads(turns[1][-1])["result"] == "ANSWER: 8"


def _rows() -> list[dict]:
    rows = []
    for c in range(3):
        for cond, ctx, cost in (("native", 60000, 0.004), ("fold", 52000, 0.003)):
            for turn, kind in enumerate(("count", "enumerate", "lookup"), 1):
                rows.append(
                    {
                        "conv_id": f"json-M-count-k{c}",
                        "task_id": f"json-M-count-k{c}+{turn}",
                        "turn": turn,
                        "kind": kind,
                        "fmt": "json",
                        "band": "M",
                        "condition": cond,
                        "rep": 0,
                        "error": None,
                        "correct": not (cond == "fold" and turn == 3 and c == 0),
                        "cost_usd": cost,
                        "duration_ms": 5000,
                        "requests": 2,
                        "input_tokens": 4,
                        "cache_read": ctx,
                        "cache_write": 1000,
                        "final_context": ctx + 1000 * turn,
                        "read_saved_file": cond == "fold",
                    }
                )
    return rows


def test_the_report_pairs_sessions_and_follows_the_context_turn_by_turn():
    fold = Setting("fold", Dials(mode="all"), frozenset({"json"}))
    text = report(_rows(), [fold], "test", "m")
    assert "6 sessions, $0.06; 0 with a failed turn" in text and "## Band M" in text
    assert "| fold | 3 | 8/9 (native 9/9) | -11% [" in text and "0/1, p 1.00 |" in text
    assert "| -25% ($-0.0030) |" in text  # three turns at $0.001 less, against $0.012
    assert "| native: context, right | 61,000, 3/3 | 62,000, 3/3 | 63,000, 3/3 |" in text
    assert (
        "| fold: context, cost, right | -8,000, -25%, 3/3 | -8,000, -25%, 3/3 | -8,000, -25%, 2/3 |" in text
    )
    assert "| json | fold | 3 | 8/9 (9/9) | -25% |" in text and "| 63,000, -8,000 | 3/3 (0/3) |" in text


def test_a_session_with_a_failed_turn_is_left_out_whole():
    rows = _rows()
    rows[3] |= {"error": "turn 1 timed out"}  # a fold session's first turn
    text = report(rows, [Setting("fold", Dials(mode="all"), frozenset({"json"}))], "test", "m")
    assert "1 with a failed turn" in text and "| fold | 2 | 6/6 (native 6/6) |" in text
    assert "- json-M-count-k0+1 fold: turn 1 timed out" in text
