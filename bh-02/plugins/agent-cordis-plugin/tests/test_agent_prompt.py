"""`changes`: what the model is told when its instructions read differently from what it was
told; `edits` and `latest`: how the transcript keeps a later reading without a whole copy."""

from hypothesis import given
from hypothesis import strategies as st

from agent_cordis_plugin import changes, edits, latest

_BEGAN = "You are the model.\n\nWorking directory: /p\nGit branch: main\n\nUse python."


def test_nothing_changed_tells_nothing() -> None:
    assert changes(_BEGAN, _BEGAN) == "" == changes(_BEGAN, _BEGAN + "\n\n")


def test_a_part_that_reads_differently_is_told_whole_and_not_also_as_gone() -> None:
    told = changes(_BEGAN, _BEGAN.replace("main", "feature"))
    assert told.startswith("(bh-02: your instructions have changed since this conversation began.")
    assert "Working directory: /p\nGit branch: feature" in told
    assert "No longer" not in told and "You are the model" not in told and "Use python" not in told
    assert told.endswith("(End of what changed.)")


def test_a_new_part_is_told_and_a_gone_one_is_named_by_its_first_line() -> None:
    extended = _BEGAN + "\n\nExtensions here: sh. How each one is, is in status.json."
    assert "\n\nExtensions here: sh." in changes(_BEGAN, extended)
    gone = changes(extended, _BEGAN)
    assert gone == (
        "(bh-02: your instructions have changed since this conversation began. No longer in them: "
        '"Extensions here: sh. How each one is, is in status.json.".)'
    )
    long = "x" * 300
    assert f'"{"x" * 99}…"' in changes(f"{_BEGAN}\n\n{long}", _BEGAN)


def test_edits_hold_only_the_paragraphs_that_changed_and_give_the_reading_back_exactly() -> None:
    switched = _BEGAN.replace("main", "feature")
    kept = edits(_BEGAN, switched)
    assert kept == [{"at": 1, "drop": 1, "add": ["Working directory: /p\nGit branch: feature"]}]
    assert latest([{"role": "system", "content": _BEGAN}, {"role": "system", "edits": kept}]) == switched
    assert edits(_BEGAN, _BEGAN) == []
    extended = f"{_BEGAN}\n\nExtensions here: sh."
    assert edits(_BEGAN, extended) == [{"at": 3, "drop": 0, "add": ["Extensions here: sh."]}]
    assert edits(extended, _BEGAN) == [{"at": 3, "drop": 1, "add": []}]


def test_latest_is_what_the_model_was_last_told_whether_kept_whole_or_as_edits() -> None:
    """A transcript from before the loop kept edits has every reading whole; one resumed since
    has edits after them, from the last whole one."""
    a, b, c = _BEGAN, _BEGAN.replace("main", "b"), _BEGAN.replace("main", "c") + "\n\nMore."
    assert latest([]) is None
    assert latest([{"role": "system", "content": a}, {"role": "system", "content": b}]) == b
    entries = [
        {"role": "system", "content": a},
        {"role": "system", "content": b},
        {"role": "system", "edits": edits(b, c)},
    ]
    assert latest(entries) == c


# Readings made of a few paragraphs that repeat and differ, with the odd stray blank line or
# space, so the edits between them insert, drop, replace and keep in every combination.
_PARAGRAPHS = st.sampled_from(["a", "b", "c", "Git branch: main", "Git branch: x", "", " ", "\n", "d\ne"])
_READINGS = st.lists(_PARAGRAPHS, max_size=8).map("\n\n".join) | st.text(alphabet="ab \n", max_size=20)


@given(st.lists(_READINGS, min_size=1, max_size=6))
def test_a_chain_of_edits_gives_back_every_reading_to_the_character(readings: list[str]) -> None:
    entries: list[dict[str, object]] = [{"role": "system", "content": readings[0]}]
    for before, after in zip(readings, readings[1:], strict=False):
        entries.append({"role": "system", "edits": edits(before, after)})
        assert latest(entries) == after
    assert latest(entries) == readings[-1]
