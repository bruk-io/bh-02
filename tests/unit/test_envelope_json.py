from dataclasses import replace

import pytest

from compressors.config import CHOICES, DEFAULT, with_sets
from compressors.envelope import Count, Lists, Role, Verbatim
from compressors.envelope_json import ANOMALIES, NAVS, SAMPLES, SHAPES, envelope
from evals.envelope_check import problems, wrong


def _pods(n: int = 40, failing: tuple[int, ...] = (7, 31)) -> dict:
    items = []
    for i in range(n):
        bad = i in failing
        items.append(
            {
                "name": f"web-{i:04x}a1b2c3",
                "phase": "CrashLoopBackOff" if bad else "Running",
                "ready": not bad,
                "restarts": i % 3,
            }
        )
    return {"kind": "PodList", "items": items}


def _config(*sets: str):
    return with_sets(DEFAULT, list(sets))


def test_the_default_recipe_is_the_schema_views_parts_and_every_claim_holds():
    value = _pods()
    env = envelope(value, frozenset(), 2000)
    text = env.text()
    assert text.startswith('shape:\n  .kind  "PodList"\n  .items: array[40] of object')
    assert (
        "anomalies: 2 rows, all listed" in text
        and '.items[7] web-0007a1b2c3: .phase "CrashLoopBackOff"' in text
    )
    assert "get more:\n  jq '.items[] | select(.phase != \"Running\") | .name' FILE" in text
    assert "samples:" not in text  # no query, so no matching rows
    assert problems("", value, env, run_jq=False) == []
    assert any(isinstance(c, Lists) for c in env.claims())  # the list of failing pods claims to be complete


def test_the_sample_recipe_shows_stand_outs_head_and_tail_and_how_to_read_any_row():
    value = _pods()
    config = _config("json_envelope.shape=summary", "json_envelope.anomalies=standouts")
    config = with_sets(config, ["json_envelope.samples=head-tail", "json_envelope.nav=rows"])
    env = envelope(value, frozenset(), 2000, config=config)
    text = env.text()
    assert "anomalies: 2 items stand out, all listed" in text and ".items[7] (" in text
    assert ".items[0]: {" in text and ".items[39]: {" in text
    assert "jq '.items[I]' FILE" in text and "jq '.items[A:B]' FILE" in text
    assert problems("", value, env, run_jq=False) == []


def test_a_typical_sample_is_a_row_that_breaks_nothing():
    value = _pods(failing=(0, 1))
    env = envelope(value, frozenset(), 2000, config=_config("json_envelope.samples=typical"))
    samples = env.level(Role.SAMPLES)
    assert [c.at for c in samples.claims if isinstance(c, Verbatim)] == [".items[2]"]
    assert problems("", value, env, run_jq=False) == []


def test_a_tight_budget_cuts_the_anomalies_and_says_how_many_it_left_out():
    value = _pods(200, failing=tuple(range(0, 200, 10)))  # 20 failing, a tenth: still rare
    env = envelope(value, frozenset(), 150)
    anomalies = env.level(Role.ANOMALIES)
    assert anomalies.head == "20 rows, 3 listed" and anomalies.body[-1] == "[... 17 more rows of .items]"
    assert not any(isinstance(c, Lists) for c in anomalies.claims)  # a cut list claims no completeness
    assert problems("", value, env, run_jq=False) == []


def test_a_claim_the_data_does_not_bear_out_is_caught():
    value = _pods()
    assert wrong("", value, Count(".items", 41)) == [".items: says 41 rows, it has 40"]
    assert wrong("", value, Verbatim(".items[3]", '{"name":"web-9999', False)) == [
        ".items[3]: the sample is not the item's text"
    ]
    missing = Lists(".items", ".phase", '"Running"', (".items[7]",))
    assert wrong("", value, missing) == [
        '.items: .items[31] holds .phase other than "Running" and is not listed'
    ]
    env = envelope(value, frozenset(), 2000)
    shape = env.parts[0]
    lying = replace(
        shape, levels=(replace(shape.levels[0], claims=(Count(".items", 40), Count(".items", 7))),)
    )
    told = replace(env, parts=(lying, *env.parts[1:]))
    assert any("says 7 rows" in p for p in problems("", value, told, run_jq=False))


def test_standouts_say_nothing_of_items_they_cannot_read():
    value = {"rows": [[i, i + 1] for i in range(30)]}
    env = envelope(value, frozenset(), 2000, config=_config("json_envelope.anomalies=standouts"))
    assert env.level(Role.ANOMALIES).empty


def test_each_part_knob_names_exactly_the_producers_there_are():
    assert set(CHOICES["json_envelope.shape"]) == set(SHAPES)
    assert set(CHOICES["json_envelope.anomalies"]) == set(ANOMALIES)
    assert set(CHOICES["json_envelope.samples"]) == set(SAMPLES)
    assert set(CHOICES["json_envelope.nav"]) == set(NAVS)
    with pytest.raises(ValueError, match=r"json_envelope\.samples is one of matches, typical"):
        _config("json_envelope.samples=some")
    with pytest.raises(ValueError, match="names each part once"):
        _config("json_envelope.priority=shape,shape,nav,samples")
