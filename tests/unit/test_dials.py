"""A dials spec: its settings, and the table that sets each against native."""

import pytest

from evals.dials import dial_table, settings


def test_each_setting_has_its_dials_and_its_formats():
    spec = {
        "formats": ["json", "log"],
        "setting": [
            {"name": "default"},
            {"name": "small", "budget": 500, "set": ["schema.rare=0.15"]},
            {"name": "schema", "view": "schema", "formats": ["json"]},
        ],
    }
    got = {s.name: s for s in settings(spec)}
    assert got["default"].dials.budget == 2000 and got["default"].formats == {"json", "log"}
    assert got["small"].dials.budget == 500 and got["small"].dials.config.schema.rare == 0.15
    assert got["schema"].dials.view == "schema" and got["schema"].formats == {"json"}
    assert (
        got["default"].dials.mode_for("default") == "inline"
        and got["default"].dials.mode_for("native") is None
    )


def test_a_bad_setting_says_what_to_write():
    with pytest.raises(ValueError, match="at least one"):
        settings({})
    with pytest.raises(ValueError, match="a name of its own"):
        settings({"setting": [{"name": "a"}, {"name": "a"}]})
    with pytest.raises(ValueError, match="mode is one of inline, spilled, all"):
        settings({"setting": [{"name": "a", "mode": "sometimes"}]})
    with pytest.raises(ValueError, match="no knob"):
        settings({"setting": [{"name": "a", "set": ["schema.rarity=1"]}]})


def _row(task: int, cond: str, correct: bool, ctx: int, cost: float) -> dict:
    return {"task_id": f"t{task}", "rep": 0, "condition": cond, "error": None, "correct": correct,
            "final_context": ctx, "input_tokens": 5, "cache_read": ctx * 2, "cache_write": 1000,
            "output_tokens": 100, "cost_usd": cost, "duration_ms": 9000, "cache_write_1h": 1000}  # fmt: skip


def test_the_table_sets_each_setting_against_native_on_the_same_tasks():
    rows = [_row(i, "native", True, 58_000, 0.007) for i in range(40)]
    rows += [_row(i, "small", i != 3, 50_000, 0.006) for i in range(40)]
    chosen = settings({"setting": [{"name": "small", "budget": 500}]})
    table = "\n".join(dial_table(rows, chosen))
    assert "| native (absolute) | 40 | - | 0/40 | 100% | 58,000 |" in table
    line = next(x for x in table.splitlines() if x.startswith("| small |"))
    assert (
        "| 40 | 0/40 | 0/40 | -2% [" in line and "], 0/1 |" in line and "| -8,000 [-8,000, -8,000] |" in line
    )
    assert "-14% ($-0.0010)" in line


def test_the_acted_table_pairs_only_the_runs_whose_hook_folded_the_large_output():
    rows = [_row(i, "native", True, 58_000, 0.007) for i in range(40)]
    rows += [_row(i, "small", True, 50_000, 0.006) | {"large_folded": i < 30} for i in range(40)]
    chosen = settings({"setting": [{"name": "small", "budget": 500}]})
    line = next(x for x in dial_table(rows, chosen, acted_only=True) if x.startswith("| small |"))
    assert line.startswith("| small | 30 | 30/40 |")
