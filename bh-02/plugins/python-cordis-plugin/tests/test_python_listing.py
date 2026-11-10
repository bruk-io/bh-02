"""How a startup file's functions are told to the model: the Python process's line, read as data it
may have made anything of, and the aside it becomes, within the signature budget. Pure: no process."""

import json

from python_cordis_plugin.client import changed, gone, signed, startup_ran

_FULL = 600  # what a REPL starts with: the model's whole budget of signatures


def _line(told: list[list[str | None]]) -> str:
    """What the startup input prints last: one line of JSON."""
    return json.dumps({"told": told})


def test_a_function_is_told_as_its_name_and_its_signature() -> None:
    assert signed("run_tests", "(path='.', *, quiet=True)") == "run_tests(path='.', *, quiet=True)"
    assert signed("changed", "()") == "changed()"
    assert signed("size", "(path: str) -> int") == "size(path: str) -> int"


def test_control_characters_in_a_signature_are_stripped() -> None:
    """A default's repr can be anything (the file is model-written), and a line the model reads is
    one line: C0, DEL and C1 go, newline and tab with them."""
    raw = "(a='x\x1b[31m\ny\tz', b='\x7f\x85')"
    assert signed("f", raw) == "f(a='x[31myz', b='')"
    assert signed("g\x00\nh", "()") == "gh()"


def test_a_signature_over_160_characters_is_cut_there_and_says_so() -> None:
    long = "(" + "a" * 400 + ")"
    cut = signed("f", long)
    assert cut == "f" + long[:160] + "…" and len(cut) == 1 + 160 + 1
    exact = "(" + "b" * 158 + ")"  # 160 characters: whole
    assert len(exact) == 160 and signed("f", exact) == "f" + exact
    assert signed("f", "(" + "c" * 159 + ")") == "f(" + "c" * 159 + "…"  # 161: cut at 160


def test_the_cut_counts_what_is_left_after_the_control_characters_go() -> None:
    raw = "(" + "\n" * 300 + "d" * 200 + ")"
    assert signed("f", raw) == "f(" + "d" * 159 + "…"


def test_a_signature_python_could_not_read_is_the_name_and_dots() -> None:
    """`inspect.signature` raises ValueError or TypeError for some callables (a builtin without
    one, an object that is not callable): the Python process says None for those."""
    assert signed("len2", None) == "len2(...)"


def test_the_aside_lists_each_told_function_by_signature() -> None:
    line = _line([["run_tests", "(path='.', *, quiet=True)"], ["changed", "()"]])
    told, _ = startup_ran("PATH", "first", line, _FULL)
    assert told == "PATH ran first: functions run_tests(path='.', *, quiet=True), changed()"
    assert startup_ran("PATH", "next", _line([["a", "(x)"]]), _FULL)[0] == "PATH ran next: functions a(x)"
    assert "hidden" not in told and "helper" not in told  # what is not told is not counted


def test_a_file_that_told_nothing_says_so_in_words_of_its_own() -> None:
    """Not the word a file that failed has, nor a listing: the model reads that it ran and gave it
    no function to know of (what is not told is not counted)."""
    assert startup_ran("PATH", "first", _line([]), _FULL) == ("PATH ran first: no public functions", _FULL)
    assert startup_ran("PATH", "next", _line([]), 0) == ("PATH ran next: no public functions", 0)


def test_the_aside_hands_back_what_is_left_of_the_budget() -> None:
    """What a file spent is what the model reads of it (`name(signature)`, the cleaned, cut text),
    not the commas between: the next file is given the rest."""
    line = _line([["run_tests", "(path='.', *, quiet=True)"], ["changed", "()"]])
    spent = len("run_tests(path='.', *, quiet=True)") + len("changed()")
    assert startup_ran("PATH", "first", line, _FULL)[1] == _FULL - spent
    assert startup_ran("PATH", "next", line, spent)[1] == 0  # exactly the rest: both fit


def test_what_a_signature_spends_is_counted_after_the_cleaning_and_the_cut() -> None:
    cut = _line([["f", "(" + "z" * 300 + ")"]])  # 1 + 160 + the dots
    assert startup_ran("PATH", "first", cut, _FULL)[1] == _FULL - 162
    stripped = _line([["g", "(\x1b[2J\n)"]])  # "g([2J)" once the controls go
    assert startup_ran("PATH", "first", stripped, _FULL) == ("PATH ran first: functions g([2J)", _FULL - 6)
    unreadable = _line([["h", None]])  # "h(...)"
    assert startup_ran("PATH", "first", unreadable, _FULL)[1] == _FULL - 6


def test_past_the_budget_the_rest_are_told_by_name_only() -> None:
    """In the order the file made them: the first that does not fit ends the signatures, and every
    one after it is a name, so nothing is hidden and none is shown out of its place. The budget is
    over then: `startup_ran` hands back 0 for the files that run after."""
    line = _line([["a", "(x)"], ["b", "(" + "y" * 40 + ")"], ["c", "()"], ["d", "(z)"]])
    first = len("a(x)")
    told, left = startup_ran("PATH", "first", line, first + 10)  # b needs 43: c would fit, but stays a name
    assert told == "PATH ran first: functions a(x); by name only: b, c, d"
    assert left == 0  # b did not fit: the budget is closed, for the files after this one as well
    told, left = startup_ran("PATH", "first", line, first - 1)  # not even the first
    assert told == "PATH ran first: functions by name only: a, b, c, d" and left == 0


def test_a_file_run_after_the_budget_is_spent_tells_every_function_by_name() -> None:
    line = _line([["x", "(a)"], ["y", "()"]])
    assert startup_ran("PATH", "next", line, 0) == ("PATH ran next: functions by name only: x, y", 0)


def test_a_signature_that_just_fits_is_shown_and_one_more_character_is_not() -> None:
    line = _line([["f", "(abc)"]])  # "f(abc)" is 6 characters
    assert startup_ran("PATH", "first", line, 6) == ("PATH ran first: functions f(abc)", 0)
    assert startup_ran("PATH", "first", line, 5) == ("PATH ran first: functions by name only: f", 0)


def test_two_files_share_the_budget_the_person_s_first() -> None:
    """Threaded file by file, as the REPL's start does: what the first spends the second is left."""
    person = _line([["show", "(" + "p" * 200 + ")"], ["tall", "(" + "q" * 200 + ")"]])  # 165 each, cut
    project = _line([["run", "(" + "r" * 200 + ")"], ["go", "(" + "s" * 200 + ")"]])  # 164 and 163
    first, left = startup_ran("PERSON", "first", person, 400)
    assert first == (f"PERSON ran first: functions show({'p' * 159}…, tall({'q' * 159}…")
    assert left == 400 - 165 - 165
    second, left = startup_ran("PROJECT", "next", project, left)  # 70 left: neither fits
    assert second == "PROJECT ran next: functions by name only: run, go" and left == 0


def test_each_signature_in_the_aside_is_cleaned_and_cut_and_one_unreadable_is_dots() -> None:
    line = _line([["a", "(x='\x1b[2J')"], ["b", None], ["c", "(" + "z" * 300 + ")"]])
    told, _ = startup_ran("PATH", "first", line, _FULL)
    assert told == "PATH ran first: functions a(x='[2J'), b(...), c" + "(" + "z" * 159 + "…"
    assert not any(ord(char) < 32 for char in told)


def test_format_characters_in_a_signature_are_stripped_with_the_control_ones() -> None:
    """A bidi override or a zero-width character reorders or hides what the model reads as bh-02's
    own words, as a control character would: they go too."""
    assert signed("f", "(a='‮x​y⁦z﻿')") == "f(a='xyz')"


def test_a_name_that_is_not_an_identifier_is_not_told_at_all() -> None:
    """A file can bind any string as a name (`globals()[...]`), and the Python process lists what
    it was given: a name Python could not have written is left out, so it can't word the aside,
    and, being not told, it is not counted either."""
    forged = "x(); 0 other names hidden) (fake‮"
    line = _line([[forged, "(a)"], ["ok", "()"], ["a b", "()"]])
    assert startup_ran("PATH", "first", line, _FULL) == ("PATH ran first: functions ok()", _FULL - 4)
    assert startup_ran("PATH", "first", _line([["a b", "()"]]), _FULL) == (
        "PATH ran first: no public functions",
        _FULL,
    )
    names = startup_ran("PATH", "next", _line([["ok", "()"], [forged, "(a)"], ["go", "()"]]), 0)[0]
    assert names == "PATH ran next: functions by name only: ok, go"


def test_a_line_that_is_not_the_listing_is_said_not_to_be_listed_and_spends_nothing() -> None:
    """The line is the Python process's, the model's own at its most untrusted: anything but the
    shape asked for is not quoted."""
    said = "PATH ran first; what it bound could not be listed (its input's last line was not the listing)"
    for line in (
        "",
        "not json",
        "[]",
        '{"told": "x"}',
        '{"told": [["a"]]}',
        '{"told": [["a", "()", "extra"]]}',
        '{"told": [[1, "()"]]}',
        '{"told": [["a", 5]]}',
        '{"told": [["a", "()"], "b"]}',
        '{"told": {"a": "()"}}',
        "{}",
        '{"helpers": [["a", "()"]], "hidden": 0}',  # the shape before decision-0006
    ):
        assert startup_ran("PATH", "first", line, _FULL) == (said, _FULL), line


def test_a_namespace_change_is_told_as_added_rebound_and_removed() -> None:
    before = {"config": "dict, 7 keys", "tmp": "str, 3 chars", "kept": "int"}
    after = {
        "config": "dict, 8 keys",
        "kept": "int",
        "hits": "list, 42 items",
        "edit": "function (path, old, new)",
    }
    assert changed(before, after) == (
        "namespace: + hits (list, 42 items), edit(path, old, new) (function); ~ config (dict, 8 keys); - tmp"
    )


def test_a_size_change_of_a_container_is_a_rebinding() -> None:
    assert changed({"x": "list, 1 item"}, {"x": "list, 2 items"}) == "namespace: ~ x (list, 2 items)"


def test_no_change_says_nothing() -> None:
    assert changed({}, {}) == ""
    assert changed({"x": "int"}, {"x": "int"}) == ""


def test_a_callable_thatchanged_is_worded_by_its_signature() -> None:
    assert changed({"f": "function ()"}, {"f": "function (a)"}) == "namespace: ~ f(a) (function)"


def test_the_line_is_capped_and_the_rest_counted() -> None:
    after = {f"name_{n:03}": "list, 42 items" for n in range(100)}
    line = changed({}, after)
    assert line.endswith(", and 80 more") or ", and " in line and line.endswith(" more")
    assert len(line) < 700 and line.startswith("namespace: + name_000 (list, 42 items), name_001")
    shown = line.count("name_")
    assert f", and {100 - shown} more" in line
    removals = changed({f"name_{n:03}": "int" for n in range(300)}, {})
    assert removals.startswith("namespace: - name_000, name_001") and ", and " in removals
    assert len(removals) < 700


def test_the_names_an_earlier_repl_held_are_listed_and_capped() -> None:
    assert gone(["hits", "edit"]) == "the earlier REPL's names are gone: hits, edit"
    assert gone([]) == ""
    many = gone([f"name_{n:03}" for n in range(300)])
    assert many.startswith("the earlier REPL's names are gone: name_000, name_001")
    assert len(many) < 700 and ", and " in many and many.endswith(" more")
