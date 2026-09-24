"""The sessions in the sidebar: which is marked, how each reads, what choosing one says, and
the row that pushes them (driven by hand)."""

from collections.abc import Mapping, Sequence
from typing import Any

from cordis.testing import drive
from tui_cordis_plugin import Frame, marked, resume_note, session_label, session_list


def test_only_the_running_session_is_marked_current() -> None:
    items = [{"id": "a", "stack": "claude"}, {"id": "b", "stack": "ollama"}]
    assert marked("b", items) == [
        {"id": "a", "stack": "claude", "current": False},
        {"id": "b", "stack": "ollama", "current": True},
    ]
    assert marked("", items)[0]["current"] is False


def test_a_session_reads_as_its_id_then_its_title_or_when_and_on_what() -> None:
    item = {"id": "20260922-101500-ab12", "created": "2026-09-22T10:15:00", "stack": "claude"}
    assert session_label(item) == ("20260922-101500-ab12", "2026-09-22 10:15 · claude")
    assert session_label({**item, "title": "fix the loader"}) == ("20260922-101500-ab12", "fix the loader")
    patched = {**item, "patches": ["echo.toml"]}  # the model row may not be claude's at all
    assert session_label(patched)[1:] == ("2026-09-22 10:15 · claude", "patched: echo.toml")


def test_choosing_a_session_says_how_to_continue_it() -> None:
    assert resume_note({"id": "x1"}) == "to continue session x1, leave (Ctrl-Q) and run `bh-02 --resume x1`"
    assert "is this one" in resume_note({"id": "x1", "current": True})
    claude = {"id": "x1", "resume": "uv run bh-02 --resume x1"}
    assert resume_note(claude).endswith("run `uv run bh-02 --resume x1`")
    assert "`uv run bh-02 --resume x1` continues it" in resume_note(claude | {"current": True})
    retired = {"id": "x0", "retired": "session x0 can't be continued: ...; start a new session"}
    assert resume_note(retired) == retired["retired"]  # not a resume that can only fail


def test_a_broken_record_reads_as_broken_and_choosing_it_says_what_is_wrong() -> None:
    item = {"id": "20260101-dead", "broken": "session record /s/meta.json can't be read; fix it"}
    assert session_label(item) == ("20260101-dead", "broken · Enter says why")
    assert resume_note(item) == item["broken"]  # not how to resume it: it can't be


async def test_the_sessions_row_pushes_the_listing_with_the_running_one_marked() -> None:
    class Sessions:
        current = "b"
        reads = 0

        def listed(self) -> Sequence[Mapping[str, Any]]:
            self.reads += 1
            return [
                {"id": "b", "created": "t2", "stack": "claude"},
                {"id": "a", "created": "t1", "stack": "claude"},
            ]

    frame = Frame(lambda message: True)
    sessions = Sessions()
    effects = await drive(session_list(sessions=sessions, frame=frame))
    assert [e.name for e in effects] == ["acquire"]
    assert effects[0].args[0] == frame.sessions
    assert sessions.reads == 0  # the row only acquires: the directory is read when the sidebar asks
    assert [(i["id"], i["current"]) for i in effects[0].args[1]()] == [("b", True), ("a", False)]
    assert sessions.reads == 1
