from dataclasses import replace

import pytest

from compressors.config import CHOICES, DEFAULT, with_sets
from compressors.envelope import Alike, Prints, Role, Shows
from compressors.envelope_log import ANOMALIES, NAVS, SAMPLES, SHAPES, envelope
from compressors.envelope_text import slots, template
from evals.envelope_check import text_problems, wrong_lines


def _log(
    n: int = 400, failed: tuple[int, ...] = (40, 310), quiet: int = -1, slow: tuple[int, ...] = ()
) -> str:
    lines = []
    for i in range(n):
        t = f"2026-11-03T00:{i // 60 % 60:02d}:{i % 60:02d}Z"
        if i in failed:
            lines.append(f"{t} ERROR payment failed for order ORD-{i:06x} req=req-{i:08x}")
        elif i == quiet:
            lines.append(f"{t} INFO  pool connections available=0 of 50 req=req-{i:08x}")
        else:
            status = 503 if i in slow else 200
            lines.append(f"{t} INFO  GET /api/orders req=req-{i:08x} user=u-{i:06x} {status} {i % 900}ms")
    return "\n".join(lines) + "\n"


def _config(*sets: str):
    return with_sets(DEFAULT, list(sets))


def test_a_hole_is_a_token_holding_a_digit_or_a_hex_id():
    assert (
        template("blk_-1608 to u-ebbadf at 10.0.0.1:50010 feedback")
        == "<*> to <*> at <*>.<*>.<*>.<*>:<*> feedback"
    )
    assert template('- button "Pay INV-1" [ref=e12]', quoted=True) == "- button <*> [ref=<*>]"
    assert slots("GET /x 200 12ms") == ["200", "12ms"]


def test_the_schema_view_counts_templates_lists_the_failures_and_greps_for_them():
    raw = _log()
    env = envelope(raw, frozenset(), 2000, view="schema")
    text = env.text()
    assert text.startswith("shape: 400 lines, 2 line templates")
    assert "   398  <*>:<*>:<*> INFO  GET /api/orders req=<*> user=<*> <*> <*>" in text
    assert "anomalies: 2 lines in 1 group, all listed" in text
    assert "41: 2026-11-03T00:00:40Z ERROR payment failed for order ORD-000028 req=req-00000028" in text
    assert "grep -nF 'ERROR payment failed for order' FILE  (the 2 lines like it)" in text
    assert text_problems(raw, env, run_tools=False) == []


def test_a_line_said_once_is_an_anomaly_with_no_rule_for_it():
    raw = _log(failed=(), quiet=200)
    anomalies = envelope(raw, frozenset(), 2000).level(Role.ANOMALIES)
    assert anomalies.head == "1 line in 1 group, all listed"
    assert any(isinstance(c, Shows) and c.first == 201 for c in anomalies.claims)


def test_a_rare_value_in_a_hole_one_value_dominates_is_an_anomaly():
    raw = _log(failed=(), slow=(7, 99))
    env = envelope(raw, frozenset(), 2000)
    text = env.text()
    assert "[<*>6: 200 398, 503 2]" in text  # the status hole: a field of the template
    assert "<*>6 is 503 in 2 lines like:" in text
    assert text_problems(raw, env, run_tools=False) == []


def test_a_query_term_few_lines_hold_picks_its_lines_as_samples():
    raw = _log()
    env = envelope(raw, frozenset({"req-0000012c"}), 2000, view="schema")
    samples = env.level(Role.SAMPLES)
    assert samples.head == "1 line matches the query" and samples.body[0].startswith("301: ")


def test_a_tight_budget_lists_some_lines_of_each_group_and_says_how_many():
    raw = _log(1000, failed=tuple(range(0, 1000, 100)), quiet=555)
    env = envelope(raw, frozenset(), 300, view="schema")
    anomalies = env.level(Role.ANOMALIES)
    assert anomalies.head.startswith("11 lines in 2 groups") and "all listed" not in anomalies.head
    assert text_problems(raw, env, run_tools=False) == []


def test_a_claim_the_lines_do_not_bear_out_is_caught():
    raw = _log()
    lines = raw.splitlines()
    tmpl = "<*>:<*>:<*> ERROR payment failed for order <*> req=<*>"
    assert wrong_lines(raw, lines, Alike(tmpl, 3, 1, 400)) == [f"lines 1-400: 2 lines like {tmpl!r}, not 3"]
    assert wrong_lines(raw, lines, Shows(41, ("an invented line",)))
    assert wrong_lines(raw, lines, Shows(41, (lines[40][:20] + "...[+9 chars]",)))  # the wrong count cut
    assert wrong_lines(raw, lines, Shows(41, (lines[40][:20] + f"...[+{len(lines[40]) - 20} chars]",))) == []
    grep = "grep -nF 'payment failed' FILE"
    assert wrong_lines(raw, lines, Prints(grep, (41,)), run_tools=False) == [
        f"{grep}: prints lines [41, 311], not [41]"
    ]
    env = envelope(raw, frozenset(), 2000)
    shape = env.parts[0]
    lying = replace(shape, levels=(replace(shape.levels[0], claims=(Alike(tmpl, 5, 1, 400),)),))
    told = replace(env, parts=(lying, *env.parts[1:]))
    found = text_problems(raw, told, run_tools=False)
    assert any("no line of it says so" in p for p in found) and any("not 5" in p for p in found)


def test_a_number_of_six_digits_or_more_measures_something_and_is_no_field():
    sizes = [67108864] * 50 + [3543612, 3536626]
    raw = "\n".join(f"INFO Received block blk_{i} of size {s}" for i, s in enumerate(sizes)) + "\n"
    env = envelope(raw, frozenset(), 2000)
    assert env.level(Role.ANOMALIES).head == "none" and "[<*>" not in env.text()


def test_each_log_part_knob_names_exactly_the_producers_there_are():
    assert set(CHOICES["log_envelope.shape"]) == {"", *SHAPES}
    assert set(CHOICES["log_envelope.anomalies"]) == {"", *ANOMALIES}
    assert set(CHOICES["log_envelope.samples"]) == {"", *SAMPLES}
    assert set(CHOICES["log_envelope.nav"]) == {"", *NAVS}
    with pytest.raises(ValueError, match=r"log_envelope\.nav is one of"):
        _config("log_envelope.nav=jq")
    terse = envelope(_log(), frozenset(), 2000, config=_config("log_envelope.shape=count"))
    assert terse.level(Role.SHAPE).body == ()
