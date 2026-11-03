import json

from evals.l2 import parse_stream, report, select


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


def test_jobs_pair_every_task_with_its_channels_conditions():
    jobs = select(["json"], ["spot"], ["M"], None)
    assert {c for _, c in jobs} == {"native", "fold", "fold-all"}
    jobs = select(["python"], ["locate"], ["L"], None)
    assert {c for _, c in jobs} == {"native", "fold-tool"} and all(t.path for t, _ in jobs)


def test_the_report_pairs_conditions_and_labels_small_samples():
    rows = []
    for i in range(5):
        for cond, correct, ctx in (("native", True, 50000), ("fold", True, 30000)):
            row = {
                "task_id": f"json-M-spot-{i}",
                "fmt": "json",
                "kind": "spot",
                "band": "M",
                "condition": cond,
            }
            row |= {"rep": 0, "correct": correct, "parsed": True, "cost_usd": 0.01, "final_context": ctx}
            rows.append(row | {"tool_calls": 2, "duration_ms": 9000, "error": None})
    text = report(rows, "test")
    assert "| json | fold | 5 | +0%" in text and "passes (indicative: under 30 pairs)" in text
