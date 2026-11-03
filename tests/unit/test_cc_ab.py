import json

from claude_code.ab import Case, cases, parse_stream


def _stream(*events: dict) -> list[str]:
    return [json.dumps(e) for e in events]


def test_a_session_is_read_into_the_numbers_compared():
    lines = _stream(
        {"type": "system", "subtype": "init"},
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "ToolSearch", "input": {}}]},
        },
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "mcp__fixture__list_pods", "input": {}}]},
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "jq . /x/tool-results/a.txt"}}
                ]
            },
        },
        {
            "type": "result",
            "result": "The pod needle-1 is crashing.",
            "num_turns": 4,
            "total_cost_usd": 0.01,
            "duration_ms": 900,
            "usage": {
                "input_tokens": 5,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 20,
                "output_tokens": 7,
            },
        },
    )
    s = parse_stream(lines, "needle-1")
    assert (s.correct, s.tool_calls, s.read_saved_file, s.turns, s.input_tokens, s.output_tokens) == (
        True, 2, True, 4, 125, 7,
    )  # fmt: skip
    assert s.error is None


def test_a_session_with_no_result_is_an_error_and_not_correct():
    s = parse_stream(["not json", json.dumps({"type": "assistant", "message": {"content": []}})], "needle-1")
    assert not s.correct and s.error == "no result event"


def test_the_grid_has_both_formats_and_the_needle_is_reproducible():
    grid = cases(seeds=1)
    assert {c.fmt for c in grid} == {"json", "log", "a11y", "figma"}
    c = Case("json", "rare_value", 50, 0.5, 0)
    assert c.needle() == c.needle() and c.needle().startswith("needle-")


def test_a_lookup_prompt_names_what_to_look_up_and_the_answer_is_not_in_it():
    c = Case("a11y", "lookup", 50, 0.5, 0)
    assert c.generated().args["invoice"] in c.prompt()
    assert c.needle() not in c.prompt()
