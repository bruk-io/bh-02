"""The findings page's builder: what it marks in envelope text, how markers nest, and what its charts draw."""

import re

import pytest

from pages.findings import Block, Mark, Wrap, annotated, blocks, highlight, paired, stacked, tree


def test_a_section_name_and_its_counts_are_marked():
    line = highlight("anomalies: 2 rows, all listed")
    assert '<span class="k">anomalies:</span>' in line
    assert '<span class="n">2</span>' in line


def test_a_line_the_output_said_keeps_only_its_line_number_marked():
    line = highlight('    188: 2026-11-03T00:03:07Z ERROR payment failed "x"')
    assert re.findall(r'<span class="(\w+)">', line) == ["p"]


def test_a_command_its_argument_and_its_note_are_marked():
    line = highlight("  jq '.invoices[16]' FILE  (reads any path above)")
    assert re.findall(r'<span class="(\w+)">', line) == ["x", "s", "x", "c"]


def test_markers_enclose_what_lies_between_them():
    nodes = tree(blocks("<!-- more: Show it -->\n\nInside.\n\n<!-- /more -->\n\n<!-- pair -->\n\nAfter."))
    assert nodes == (Wrap("more", "Show it", (Block(("Inside.",)),)), Mark("pair", ""), Block(("After.",)))


def test_an_unclosed_fold_says_how_to_close_it():
    with pytest.raises(ValueError, match="end it with <!-- /more -->"):
        tree(blocks("<!-- more: Show it -->\n\nInside."))


def test_a_closing_marker_with_nothing_open_is_refused():
    with pytest.raises(ValueError, match="closes nothing open"):
        tree(blocks("Text.\n\n<!-- /grid -->"))


_ANSWERS = (
    "| Answers right | With the envelope | Without |",
    "|---|---|---|",
    "| Haiku | 80 of 80 | 72 of 80 |",
)


def test_a_paired_chart_draws_each_share_of_its_whole():
    html = paired("Answers", _ANSWERS)
    assert re.findall(r"width:([\d.]+)%", html) == ["100.0", "90.0"]
    assert "80 of 80" in html and "72 of 80" in html


def test_a_paired_chart_refuses_a_cell_that_is_not_a_share():
    with pytest.raises(ValueError, match="'a of b'"):
        paired("Answers", (*_ANSWERS[:2], "| Haiku | 80 | 72 |"))


def test_a_stacked_chart_prints_only_the_shares_that_fit_and_draws_no_empty_segment():
    html = stacked(
        "Reads",
        (
            "| Read | Sonnet |",
            "|---|---|",
            "| Ran a command | 0% |",
            "| Own search | 72% |",
            "| Whole file | 1% |",
        ),
    )
    segments = re.findall(r'<span class="sg (\w+)"[^>]*>([^<]*)</span>', html)
    assert segments == [("acc2", "72%"), ("mut", "")]


_ENVELOPE = ("shape:", "  .a: int", "anomalies: none found")


def test_an_annotated_envelope_puts_each_note_beside_its_section():
    html = annotated(_ENVELOPE, ("- `shape:` What it is.", "- `anomalies:` What differs."))
    assert html.count('<div class="ar ') == 2
    assert html.index("What it is.") < html.index("anomalies:</span>")


def test_an_annotated_envelope_needs_a_note_for_every_section():
    with pytest.raises(ValueError, match="every section needs one note"):
        annotated(_ENVELOPE, ("- `shape:` What it is.",))
