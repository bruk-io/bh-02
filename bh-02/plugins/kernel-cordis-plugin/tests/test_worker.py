"""The worker's pure pieces, imported directly: no process, no socket."""

import ast

from kernel_cordis_plugin.worker import input_traceback, split_last_expression


def test_an_input_ending_in_an_expression_shows_it() -> None:
    body, last = split_last_expression("x = 2\nx * 21")
    assert len(body.body) == 1 and last is not None
    assert eval(compile(last, "<t>", "eval"), {"x": 2}) == 42
    body, last = split_last_expression("x = 2\nprint(x)\ny = 3")
    assert last is None and len(body.body) == 3
    assert isinstance(split_last_expression("")[0], ast.Module)


def test_a_failure_outside_any_input_keeps_every_frame() -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        shown = input_traceback(exc)
    assert "test_worker.py" in shown and shown.endswith("ValueError: boom")
