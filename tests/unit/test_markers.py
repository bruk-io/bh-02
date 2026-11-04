"""Every marker a fold writes reads back with the pattern that goes with it."""

from compressors import markers


def test_line_markers_read_back():
    assert markers.LINE_RANGE.match(markers.lines_folded(4, 44, markers.siblings(40, 3))).group(
        "first", "last"
    ) == ("4", "44")
    assert markers.LINE_RANGE.match(markers.lines_omitted(16, 342)).group("first", "last") == ("16", "342")
    assert markers.LINE_RANGE.match(markers.repeated(9, 2, 10)).group("first", "last") == ("2", "10")
    assert markers.INLINE.search("12\tdef f():  " + markers.lines_folded(13, 40, "28 lines"))["first"] == "13"
    assert markers.SIBLING_RUN.search("  " + markers.lines_folded(3, 9, markers.siblings(5)))
    assert markers.NOTE.match(markers.signals_hidden(4))
    assert markers.CLIPPED.search(markers.clipped("x" * 50, 10))["chars"] == "40"
    assert markers.clipped("short", 10) == "short"


def test_the_jsonl_note_reads_back():
    m = markers.JSONL_NOTE.match(markers.jsonl_note(300, by_line=False) + "\nshape:")
    assert m["records"] == "300" and m["where"] == "blank lines are skipped, so index i is not line i+1"


def test_keys_that_are_not_identifiers_are_quoted_so_the_jq_path_is_valid():
    from compressors.envelope_json import envelope

    text = envelope({"pod-list": [{"n": i} for i in range(9)]}, frozenset(), 2000, view="schema").text()
    assert '["pod-list"]: array[9] of object' in text
