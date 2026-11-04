"""Layer 1's own checks, on inputs made here: coverage of line markers, and the JSONL note."""

import json

from compressors.route import fold
from evals.l1 import coverage, jsonl_note


def test_coverage_catches_a_marker_that_skips_or_overlaps():
    source = "\n".join(f"line {i}" for i in range(1, 11))
    good = "line 1\n[... lines 2-9 omitted (8 lines)]\nline 10"
    assert coverage(source, good, numbered=False) == []
    assert coverage(source, "line 1\n[... lines 3-9 omitted (7 lines)]\nline 10", numbered=False)
    assert coverage(source, "line 1\n[... lines 2-9 omitted (8 lines)]", numbered=False)


def test_the_jsonl_note_is_checked_against_the_lines_it_names():
    rows = [json.dumps({"name": f"pod-{i:04d}", "phase": "Running"}) for i in range(300)]
    for raw in ("\n".join(rows), "\n" + "\n\n".join(rows)):
        folded = fold(raw, budget_tokens=300)
        assert folded is not None and jsonl_note(raw, folded.body) == []
    gappy = "\n" + "\n\n".join(rows)
    false = fold("\n".join(rows), budget_tokens=300)  # claims index i is line i+1
    assert false is not None
    assert jsonl_note(gappy, false.body) == [
        "the JSONL note maps index i to line i+1, and a record is not there"
    ]
