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


def test_json_markers_read_back():
    m = markers.JSON_SLICE.match(markers.json_slice('$["pod-list"]', 2, 499, 500))
    assert m.group("path", "start", "stop", "count", "total") == ('$["pod-list"]', "2", "499", "497", "500")
    k = markers.JSON_KEYS.match(markers.json_keys(["a", "b"], 17, "$.releases"))
    assert k.group("omitted", "total", "path") == ("2", "17", "$.releases")
    text = '{"_folded": "' + markers.json_slice("$.items", 2, 9, 10) + '"}'
    assert markers.JSON_SLICE_IN_TEXT.search(text).group("path", "start") == ("$.items", "2")


def test_keys_that_are_not_identifiers_are_quoted_so_the_jq_path_is_valid():
    from compressors.json_fold import child_path

    assert child_path("$", "pod-list") == '$["pod-list"]' and child_path("$", "items") == "$.items"
