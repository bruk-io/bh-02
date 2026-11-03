import random

import pytest

from harness.needle import JSON_KINDS, LOG_KINDS, evaluate, json_case, log_case


@pytest.mark.parametrize("kind", JSON_KINDS)
def test_every_json_case_holds_its_needle_once(kind):
    case = json_case(kind, 50, 0.5, random.Random(1))
    assert case.raw.count(case.needle) == 1


@pytest.mark.parametrize("kind", LOG_KINDS)
def test_every_log_case_holds_its_needle_once(kind):
    case = log_case(kind, 200, 0.5, random.Random(1))
    assert case.raw.count(case.needle) == 1


def test_cases_are_reproducible_from_the_seed():
    assert json_case("bool_flip", 50, 0.25, random.Random(7)) == json_case(
        "bool_flip", 50, 0.25, random.Random(7)
    )


def test_an_error_line_mid_log_survives_and_a_quiet_one_does_not():
    loud = log_case("error_word", 2000, 0.5, random.Random(3))
    quiet = log_case("quiet_line", 2000, 0.5, random.Random(3))
    assert evaluate(loud, use_query=False).survived
    assert not evaluate(quiet, use_query=False).survived
