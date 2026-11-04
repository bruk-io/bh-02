"""Input nested deeper than Python's recursion limit folds like any other (review R18)."""

import json

import pytest

from compressors.cli import fold_text
from compressors.common import split_lines
from compressors.envelope_tree import envelope
from compressors.tree import indent_tree
from evals.envelope_check import text_problems


def _else_if_chain(branches: int) -> str:
    arms = "".join(f" else if (x === {i}) {{\n    return {i};\n  }}" for i in range(1, branches))
    return f"function f(x) {{\n  if (x === 0) {{\n    return 0;\n  }}{arms}\n}}\n"


def test_an_else_if_chain_that_nests_a_level_per_branch_folds_as_code():
    r = fold_text(_else_if_chain(400), budget=500, path="a.js")  # failed from 248 branches
    assert (r.branch, r.language) == ("code", "javascript")


@pytest.mark.parametrize("budget", [500, 60_000])  # the large budget opens hundreds of levels
def test_an_outline_1200_levels_deep_folds_and_every_claim_holds(budget):
    raw = "".join(" " * i + f"- item {i}\n" for i in range(1200))  # failed from 992
    r = fold_text(raw, budget=budget, quiet=True)
    lines = tuple(split_lines(raw))
    env = envelope(lines, indent_tree(list(lines)), frozenset(), budget)
    assert r.branch == "outline" and r.text == env.text() and text_problems(raw, env, run_tools=False) == []


def test_xml_1200_elements_deep_folds_as_xml_one_per_line_or_packed():
    lines = (
        "".join(f"<a{i}>\n" for i in range(1200))
        + "x\n"
        + "".join(f"</a{i}>\n" for i in reversed(range(1200)))
    )
    assert fold_text(lines, budget=300).branch == "xml"
    packed = "<r>" + "<a>" * 1200 + "x" + "</a>" * 1200 + "</r>"  # too deep for minidom to pretty-print
    r = fold_text(packed, budget=300)
    assert r.branch == "xml" and r.source is not None  # it was taken for HTML


def test_json_nested_past_the_parsers_stack_is_cut_as_text_and_forcing_it_says_why():
    raw = "[" * 200_000 + "]" * 200_000
    assert fold_text(raw, budget=300).branch == "text"
    with pytest.raises(ValueError, match="nests deeper than the parser allows"):
        fold_text(raw, budget=300, fmt="json")


def test_json_deeper_than_the_fold_shows_is_marked_not_dropped():
    value: object = 1
    for _ in range(2000):
        value = {"k": value, "pad": "x" * 20}
    r = fold_text(json.dumps(value), budget=300)
    assert r.branch == "json" and "nested deeper than" in r.text
