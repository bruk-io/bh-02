"""Conversations are built from the registry's count tasks (the registry reads real files on this
host), and each turn is scored from its own part of one session's stream."""

import json

from evals.dials import settings
from evals.sessions import jobs, turn_rows
from evals.tasks import conversations, task
from evals.truth import Exact, Items


def test_a_conversation_asks_follow_ups_on_its_count_tasks_payload():
    convs = conversations(["S", "M"], ["json"])
    assert [c.conv_id for c in convs] == [
        "json-S-count-k3",
        "json-S-count-k7",
        "json-M-count-k3",
        "json-M-count-k7",
        "json-M-count-k12",
        "json-M-count-k20",
    ]
    conv = convs[3]
    first = task("json-M-count-k7")
    assert conv.turns[0] is not first and conv.turns[0].task_id == first.task_id
    assert [t.kind for t in conv.turns] == ["count", "enumerate", *["lookup"] * 4]
    assert {t.payload() for t in conv.turns} == {first.payload()}
    assert conv.turns[0].prompt.startswith("Use the list_pods tool.")
    assert all("tool" not in t.prompt for t in conv.turns[1:])
    enumerate_truth = conv.turns[1].truth
    assert isinstance(enumerate_truth, Items) and len(enumerate_truth.expected) == 7
    for t in conv.turns[2:]:
        assert isinstance(t.truth, Exact) and t.query in t.prompt and t.truth.value in first.payload()
    assert len({t.task_id for c in convs for t in c.turns}) == sum(len(c.turns) for c in convs)


def _turn(answer: str, cost: float, hour: int) -> list[str]:
    usage = {"input_tokens": 2, "cache_read_input_tokens": 40000, "cache_creation_input_tokens": 500}
    return [
        json.dumps({"type": "assistant", "message": {"id": answer, "content": [], "usage": usage}}),
        json.dumps(
            {
                "type": "result",
                "result": f"...\nANSWER: {answer}",
                "num_turns": 1,
                "total_cost_usd": cost,
                "duration_ms": 3000,
                "usage": usage,
                "modelUsage": {"m": {"cacheCreationEphemeral1hInputTokens": hour}},
            }
        ),
    ]


def test_each_turn_is_scored_with_its_own_cost_and_an_unreached_one_carries_the_error():
    conv = conversations(["M"], ["json"])[1]
    turns = [_turn("7", 0.004, 20000), _turn("wrong", 0.006, 20500)]
    rows = turn_rows(conv, {"condition": "fold", "rep": 0}, turns, "turn 3 timed out after 600s")
    assert [r["correct"] for r in rows[:2]] == [True, False]
    assert [round(r["cost_usd"], 6) for r in rows[:2]] == [0.004, 0.002]
    assert [r["cache_write_1h"] for r in rows[:2]] == [20000, 500]
    assert rows[1]["final_context"] == 40502 and rows[1]["duration_ms"] == 3000
    assert all(r["error"] == "turn 3 timed out after 600s" for r in rows[2:]) and len(rows) == 6
    assert rows[0]["conv_id"] == "json-M-count-k7" and rows[5]["turn"] == 6


def test_session_jobs_pair_native_with_each_setting_that_covers_the_format():
    spec = {"bands": ["M"], "reps": 2, "formats": ["json", "log"]}
    spec["setting"] = [
        {"name": "fold", "mode": "all"},
        {"name": "schema", "view": "schema", "formats": ["json"]},
    ]
    planned = jobs(spec, settings(spec))
    assert len(planned) == 2 * (4 * 3 + 4 * 2)  # reps x (json: native, fold, schema; log: native, fold)
    assert [c for conv, c, rep, _ in planned if conv.conv_id == "json-M-count-k3" and rep == 0] == [
        "native",
        "fold",
        "schema",
    ]
