"""Every marker an envelope writes reads back with the pattern that goes with it."""

from compressors import markers


def test_a_clipped_line_says_how_much_was_cut_and_reads_back():
    assert markers.CLIPPED.search(markers.clipped("x" * 50, 10))["chars"] == "40"
    assert markers.clipped("short", 10) == "short"


def test_the_jsonl_note_reads_back():
    m = markers.JSONL_NOTE.match(markers.jsonl_note(300, by_line=False) + "\nshape:")
    assert m["records"] == "300" and m["where"] == "blank lines are skipped, so index i is not line i+1"


def test_keys_that_are_not_identifiers_are_quoted_so_the_jq_path_is_valid():
    from compressors.envelope_json import envelope

    text = envelope({"pod-list": [{"n": i} for i in range(9)]}, frozenset(), 2000, view="schema").text()
    assert '["pod-list"]: array[9] of object' in text
