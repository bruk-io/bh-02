"""The scorers (review 1, R6): answers are read from their ANSWER line; folds are judged by
structure, not by a number or a name that merely appears."""

import pytest

from evals.truth import (
    Absent,
    Exact,
    Items,
    Location,
    Needle,
    Number,
    answer_items,
    answer_line,
    mentions,
    promotes,
    score_answer,
    score_fold,
)


def test_the_answer_line_is_the_last_one_and_lists_split_cleanly():
    reply = "Thinking...\nANSWER: draft\nMore.\n**ANSWER:** `a1`, `a2` and a3."
    assert answer_line(reply) == "a1`, `a2` and a3"  # outer markup stripped
    assert answer_items(answer_line(reply)) == ["a1", "a2", "a3"]
    assert answer_items("none") == [] and answer_items("None.") == []


@pytest.mark.parametrize("wrong", [2, 4, 14, 16])
def test_a_count_or_a_line_off_by_any_amount_is_wrong(wrong):
    assert score_answer(Number(3), "ANSWER: 3").correct
    assert not score_answer(Number(3), f"There are 3 of the 300 ...\nANSWER: {wrong}").correct
    assert not score_answer(Location(15, "def x"), f"ANSWER: {wrong}").correct


def test_a_list_is_scored_on_what_it_lists_not_on_the_prose_around_it():
    truth = Items(frozenset({"a1", "a2"}), frozenset({"a1", "a2", "b1", "b2"}))
    assert score_answer(truth, "b1 and b2 are left out because ...\nANSWER: a1, a2").correct
    assert not score_answer(truth, "ANSWER: a1, a2, b1").correct  # precision 2/3
    assert not score_answer(truth, "ANSWER: a1").correct  # recall 1/2


def test_absent_needs_an_explicit_none_and_rejects_an_invented_anomaly():
    truth = Absent(frozenset({"web-1", "web-2"}))
    assert score_answer(truth, "Everything looks fine.\nANSWER: none").correct
    assert not score_answer(truth, "The payment for ORD-55555 failed.\nANSWER: ORD-55555").correct
    assert not score_answer(truth, "ANSWER: web-1").correct


def test_without_an_answer_line_the_prose_is_scored_and_flagged():
    s = score_answer(Needle("web-7"), "It is web-7.")
    assert s.correct and not s.parsed
    assert score_answer(Exact("e512"), "ANSWER: e512").parsed


def test_a_count_is_not_sufficient_from_a_number_that_merely_appears():
    truth = Number(15, frozenset({"def a", "def b"}))
    assert not score_fold(truth, "15\tdef a(self):\n\t[... lines 16-30 folded]").correct  # a line number
    assert score_fold(truth, "3\tdef a():\n9\tdef b():").correct  # every counted item visible
    stated = Number(3, frozenset({"x", "y", "z"}), ('"\\"CrashLoopBackOff\\"": 3',))
    assert score_fold(
        stated, '{"value_counts": {"phase": {"\\"Running\\"": 497, "\\"CrashLoopBackOff\\"": 3}}}'
    ).correct


def test_promotion_is_an_envelope_naming_anomalies_whatever_the_format():
    log = "shape: 300 lines, 5 line templates\nanomalies: 2 lines in 1 group, all listed\n  2 lines like: x"
    tree = "shape: 610 lines\nanomalies: 2 of 60 items in 1 run, all listed"
    assert promotes(log) and promotes(tree)
    assert not promotes("shape: 300 lines\nanomalies: none\nget more:\n  sed -n 'A,Bp' FILE")
    assert not score_fold(Absent(frozenset()), tree).correct


def test_mentions_is_a_whole_word():
    assert mentions("version 8.1.", "8.1") and not mentions("8.1.7", "8.1") and not mentions("e1234", "e123")


def test_a_listed_item_may_be_the_part_of_a_name_that_only_one_candidate_holds():
    cards = frozenset(f"Card {c}" for c in ("N7697", "M4557", "X6370", "K1203"))
    truth = Items(frozenset({"Card N7697", "Card M4557"}), cards)
    assert score_answer(truth, "ANSWER: N7697, M4557").correct
    assert score_answer(truth, "ANSWER: Card N7697 (hidden), Card M4557").correct
    assert not score_answer(truth, "ANSWER: Card").correct  # every card holds it: it names none
    wrong = score_answer(truth, "ANSWER: N7697, M4557, X6370")
    assert wrong.recall == 1.0 and wrong.precision == 2 / 3 and not wrong.correct


def test_a_needle_may_be_named_by_any_of_its_names():
    needle = Needle("ORD-5666fa", frozenset({"req-e47a37be"}))
    assert score_answer(needle, "ANSWER: req-e47a37be").correct
    assert score_answer(needle, "ANSWER: ORD-5666fa").correct
    assert not score_answer(needle, "ANSWER: u-ae87d2").correct
    assert score_fold(needle, "... req=req-e47a37be ...").correct
