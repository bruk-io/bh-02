"""`changes`: what the model is told when its instructions read differently from what it was told."""

from agent_cordis_plugin import changes

_BEGAN = "You are the model.\n\nWorking directory: /p\nGit branch: main\nToday: 2026-10-06\n\nUse python."


def test_nothing_changed_tells_nothing() -> None:
    assert changes(_BEGAN, _BEGAN) == "" == changes(_BEGAN, _BEGAN + "\n\n")


def test_a_part_that_reads_differently_is_told_whole_and_not_also_as_gone() -> None:
    told = changes(_BEGAN, _BEGAN.replace("main", "feature"))
    assert told.startswith("(bh-02: your instructions have changed since this conversation began.")
    assert "Working directory: /p\nGit branch: feature\nToday: 2026-10-06" in told
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
