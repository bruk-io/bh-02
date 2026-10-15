"""How a startup file's helpers are told to the model: the Python process's line, read as data it
may have made anything of, and the aside it becomes. Pure: no process."""

import json

from python_cordis_plugin.client import signed, startup_ran


def _line(helpers: list[list[str | None]], hidden: int) -> str:
    """What the startup input prints last: one line of JSON."""
    return json.dumps({"helpers": helpers, "hidden": hidden})


def test_a_helper_is_its_name_and_its_signature() -> None:
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


def test_the_aside_lists_the_helpers_and_counts_the_other_names() -> None:
    line = _line([["run_tests", "(path='.', *, quiet=True)"], ["changed", "()"]], 3)
    assert startup_ran("PATH", "first", line) == (
        "PATH ran first: helpers run_tests(path='.', *, quiet=True), changed(); 3 other names hidden"
    )
    assert startup_ran("PATH", "next", _line([["a", "(x)"]], 1)) == (
        "PATH ran next: helpers a(x); 1 other name hidden"
    )
    assert startup_ran("PATH", "first", _line([["a", "(x)"]], 0)) == "PATH ran first: helpers a(x)"


def test_a_file_with_no_helper_says_how_many_names_it_hides() -> None:
    assert startup_ran("PATH", "first", _line([], 3)) == "PATH ran first: no helpers; 3 names hidden"
    assert startup_ran("PATH", "next", _line([], 1)) == "PATH ran next: no helpers; 1 name hidden"


def test_a_file_that_bound_nothing_keeps_the_word_it_always_had() -> None:
    assert startup_ran("PATH", "first", _line([], 0)) == "PATH ran first and defined: nothing"


def test_each_helper_in_the_aside_is_cleaned_and_cut_and_one_unreadable_is_dots() -> None:
    line = _line([["a", "(x='\x1b[2J')"], ["b", None], ["c", "(" + "z" * 300 + ")"]], 0)
    told = startup_ran("PATH", "first", line)
    assert told == "PATH ran first: helpers a(x='[2J'), b(...), c" + "(" + "z" * 159 + "…"
    assert not any(ord(char) < 32 for char in told)


def test_a_line_that_is_not_the_listing_is_said_not_to_be_listed() -> None:
    """The line is the Python process's, the model's own at its most untrusted: anything but the
    shape asked for is not quoted."""
    said = "PATH ran first; what it bound could not be listed (its input's last line was not the listing)"
    for line in (
        "",
        "not json",
        "[]",
        '{"helpers": "x", "hidden": 1}',
        '{"helpers": [["a"]], "hidden": 1}',
        '{"helpers": [[1, "()"]], "hidden": 1}',
        '{"helpers": [], "hidden": -1}',
        '{"helpers": [], "hidden": "3"}',
        '{"helpers": []}',
    ):
        assert startup_ran("PATH", "first", line) == said, line
