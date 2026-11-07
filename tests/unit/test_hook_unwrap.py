"""A result that only wraps its text, as FastMCP sends a text tool's result, is folded as its text."""

import json

from claude_code.hook import unwrapped


def test_a_result_that_only_wraps_text_is_that_text():
    text = "2026-11-03T14:00:24Z INFO search status=200\n" * 3
    assert unwrapped(json.dumps({"result": text})) == text


def test_any_other_result_is_left_as_it_is():
    for raw in (
        json.dumps({"result": {"rows": [1, 2]}}),  # structured data is data, to fold as JSON
        json.dumps({"result": "x", "isError": False}),  # more than the wrapper
        '{"result": "not closed',
        'plain text that mentions {"result": 1}',
    ):
        assert unwrapped(raw) == raw
