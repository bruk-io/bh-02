"""The three envelope patterns (full, lean, index) in every format, and the index's claims."""

from compressors.common import split_lines
from compressors.envelope import Role, Selects
from compressors.envelope_json import PRESETS as JSON_PRESETS
from compressors.envelope_json import envelope as json_envelope
from compressors.envelope_log import PRESETS as LOG_PRESETS
from compressors.envelope_log import envelope as log_envelope
from compressors.envelope_tree import PRESETS as TREE_PRESETS
from compressors.envelope_tree import envelope as tree_envelope
from compressors.tree import indent_tree
from evals.envelope_check import problems, text_problems, wrong


def _pods(n: int = 60, failing: tuple[int, ...] = (7, 31)) -> dict:
    return {
        "items": [
            {"name": f"web-{i:04d}", "phase": "Failed" if i in failing else "Running", "tier": "abc"[i % 3]}
            for i in range(n)
        ]
    }


def test_every_format_has_the_same_views():
    assert (
        set(JSON_PRESETS)
        == set(LOG_PRESETS)
        == set(TREE_PRESETS)
        == {
            "sample",
            "schema",
            "full",
            "lean",
            "index",
        }
    )


def test_the_json_index_gives_every_value_group_a_command_that_prints_its_rows():
    value = _pods()
    env = json_envelope(value, frozenset(), 2000, view="index")
    nav = env.level(Role.NAV)
    assert ".items: 60 rows; one: jq '.items[I]' FILE" in nav.body[0]
    assert "jq '.items[] | select(.phase == \"Failed\") | .name' FILE  (2 rows)" in nav.body
    assert nav.body.count("jq '.items[7]' FILE") == 1  # a listed row once, however many notes it has
    assert problems("", value, env, run_jq=False) == []
    wrong_count = Selects(
        "jq '.items[] | select(.tier == \"b\") | .name' FILE", ".items", ".tier", '"b"', ".name", 5
    )
    assert wrong("", value, wrong_count, run_jq=False) == [
        f'{wrong_count.command}: says 5 rows, 20 hold .tier "b"'
    ]


def test_the_log_index_greps_every_template_and_each_prints_exactly_its_lines():
    raw = "".join(f"INFO GET /a/{i} ok\n" if i % 2 else f"INFO POST /b/{i} done\n" for i in range(200))
    raw += "ERROR disk full on /dev/sda1\n"
    env = log_envelope(raw, frozenset(), 2000, view="index")
    nav = env.level(Role.NAV).body
    assert nav[0].startswith("grep -nF 'ERROR disk full on /dev/' FILE")  # the anomaly first
    assert sum(line.startswith("grep -nF") for line in nav) == 3
    assert text_problems(raw, env, run_tools=False) == []


def test_the_tree_index_gives_each_run_and_each_odd_item_its_lines():
    lines = ["- list:"] + [f"  - item {i}:\n    - button{' [disabled]' if i == 5 else ''}" for i in range(30)]
    raw = "\n".join(lines) + "\n"
    src = tuple(split_lines(raw))
    env = tree_envelope(src, indent_tree(list(src)), frozenset(), 2000, view="index")
    nav = env.level(Role.NAV).body
    assert nav[0].startswith("sed -n '2,61p' FILE  (30 items of line 1; 30 items like: - item <*>:)")
    assert "sed -n '12,13p' FILE  (12:   - item 5:)" in nav
    assert text_problems(raw, env, run_tools=False) == []


def test_full_fills_every_part_and_lean_drops_the_samples():
    value = _pods()
    full = json_envelope(value, frozenset(), 2000, view="full")
    lean = json_envelope(value, frozenset(), 2000, view="lean")
    assert all(not full.level(r).empty for r in Role)
    assert lean.level(Role.SAMPLES).empty and len(lean.text()) < len(full.text())
    assert problems("", value, full, run_jq=False) == [] and problems("", value, lean, run_jq=False) == []
