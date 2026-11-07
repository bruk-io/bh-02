"""The scenario harness's parts that need no model: what a session is given, and what it did."""

import json

from evals.truth import Exact
from scenarios import code
from scenarios.l2 import calls_in, prompt_for, report, tools_for, unprefixed


def _task(kind: str) -> code.Task:
    return code.Task(f"code-M-0-{kind}", "edit" if kind == "edit" else "enumerate", "Do it.", Exact("1"), ())


def test_only_an_edit_task_may_edit_and_every_prompt_asks_for_its_answer_line():
    assert tools_for(_task("edit")).endswith(",Edit")
    assert "Edit" not in tools_for(_task("failing"))
    assert "ANSWER: <every item" in prompt_for(_task("failing"))
    assert "ANSWER: done" in prompt_for(_task("edit"))


def _stream(*events: dict) -> list[str]:
    return [json.dumps(e) for e in events]


def test_each_call_is_named_by_what_it_was_given_and_sized_by_what_came_back():
    lines = _stream(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "./run-tests -v"}},
                    {
                        "type": "tool_use",
                        "id": "b",
                        "name": "Read",
                        "input": {"file_path": "shop/pricing.py"},
                    },
                    {"type": "tool_use", "id": "c", "name": "ToolSearch", "input": {"query": "x"}},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "a", "content": "x" * 8000},
                    {
                        "type": "tool_result",
                        "tool_use_id": "b",
                        "content": [{"type": "text", "text": "y" * 40}],
                    },
                ]
            },
        },
        "not json",
    )
    assert calls_in(lines) == [
        {"tool": "Bash", "input": "./run-tests -v", "tokens": 2000},
        {"tool": "Read", "input": "shop/pricing.py", "tokens": 10},
    ]


def test_a_report_counts_right_answers_by_task_size_and_condition_and_leaves_failed_runs_out():
    base = {
        "size": "M",
        "turns": 4,
        "final_context": 30000,
        "cost_usd": 0.01,
        "large_calls": 1,
        "answer_line": "x",
    }
    rows = [
        {
            **base,
            "task_id": "code-M-0-failing",
            "kind": "failing",
            "condition": "native",
            "correct": True,
            "error": None,
            "calls": [{"tool": "Bash", "input": "./run-tests -v", "tokens": 7000}],
        },
        {
            **base,
            "task_id": "code-M-1-failing",
            "kind": "failing",
            "condition": "native",
            "correct": False,
            "error": None,
            "calls": [],
        },
        {
            **base,
            "task_id": "code-M-2-failing",
            "kind": "failing",
            "condition": "native",
            "correct": False,
            "error": "timed out",
            "calls": [],
        },
    ]
    text = report(rows, "claude-haiku-5-5")
    assert "| failing | M | native | 1 of 2 (50%) |" in text
    assert "1 failed to produce an answer" in text
    assert "`Bash: ./run-tests -v` | 1 | 7,000 |" in text


def test_an_event_whose_message_is_text_is_passed_over():
    lines = _stream(
        {"type": "system", "message": "compacting"}, {"type": "assistant", "message": {"content": "hi"}}
    )
    assert calls_in(lines) == []


def test_a_name_given_with_the_package_before_it_is_the_name_it_names():
    assert (
        unprefixed("ANSWER: shop.orders.total_1, carts.total_2", "shop.")
        == "ANSWER: orders.total_1, carts.total_2"
    )
    assert unprefixed("ANSWER: workshop.orders.x", "shop.") == "ANSWER: workshop.orders.x"
    assert unprefixed("ANSWER: shop.orders.x", "") == "ANSWER: shop.orders.x"
