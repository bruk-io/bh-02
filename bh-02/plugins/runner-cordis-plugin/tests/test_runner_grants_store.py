"""The always-grants file (`store`): kept whole, read through no link, refused when wrong."""

import os
import stat
from pathlib import Path

import pytest

from runner_cordis_plugin.grants import Asker, Grant, Kind, Request, Source
from runner_cordis_plugin.store import FILE, Refused, parsed, read, rendered, write

REQUESTS = (
    Request(Grant(Kind.NET, "example.com", 443), Asker(Source.ROW, "python"), 'fetch "packages"\nfast'),
    Request(Grant(Kind.READ, "/data/in"), Asker(Source.INPUT, "python"), "reads \\ the data"),
    Request(Grant(Kind.ENV, "AWS_PROFILE"), Asker(Source.AGENT, "reviewer"), "ünïcode ✓ 😀"),
    Request(Grant(Kind.WRITE, "/data/out"), Asker(Source.EXTENSION, "lint"), "writes"),
)


def test_what_is_rendered_parses_back_the_same() -> None:
    assert parsed(rendered(REQUESTS), "x") == REQUESTS
    assert rendered(()) == "" and parsed("", "x") == ()


def test_a_grant_is_kept_once_the_first_asker_stays() -> None:
    again = Request(REQUESTS[0].grant, Asker(Source.AGENT, "other"), "later")
    assert parsed(rendered([*REQUESTS, again]), "x") == REQUESTS


def test_written_at_0600_and_read_back(tmp_path: Path) -> None:
    directory = tmp_path / "grants"
    directory.mkdir(mode=0o700)
    assert read(directory) == ()
    write(directory, REQUESTS)
    assert stat.S_IMODE(os.stat(directory / FILE).st_mode) == 0o600
    assert read(directory) == REQUESTS
    write(directory, REQUESTS[:1])
    assert read(directory) == REQUESTS[:1]


def test_a_missing_directory_is_refused_saying_to_run_bh_02_again(tmp_path: Path) -> None:
    with pytest.raises(Refused, match="run bh-02 again"):
        read(tmp_path / "absent")
    with pytest.raises(Refused, match="can't write"):
        write(tmp_path / "absent", REQUESTS)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not [toml", "is not TOML"),
        ("a = 1", r"`\[\[grant\]\]` tables alone"),
        ("[[grant]]\nkind = 'read'\n", "`target` must be text"),
        ("[[grant]]\nkind = 'bogus'\ntarget = '/a'\nsource = 'row'\nname = 'n'\nreason = 'r'\n", "grant 1"),
        (
            "[[grant]]\nkind = 'read'\ntarget = 'rel'\nsource = 'row'\nname = 'n'\nreason = 'r'\n",
            "absolute path",
        ),
        ("[[grant]]\nkind = 'read'\ntarget = '/a'\nsource = 'row'\nname = 'n'\nreason = ''\n", "no reason"),
        (
            "[[grant]]\nkind = 'net'\ntarget = 'a.b'\nport = 'x'\nsource = 'row'\nname = 'n'\nreason = 'r'\n",
            "`port` must be",
        ),
        ("[[grant]]\nextra = 1\n", "must be a table of"),
    ],
)
def test_a_file_that_is_not_what_is_described_is_refused_with_where(text: str, message: str) -> None:
    with pytest.raises(Refused, match=message):
        parsed(text, "grants.toml")


def test_a_link_for_the_file_is_never_followed(tmp_path: Path) -> None:
    directory = tmp_path / "grants"
    directory.mkdir()
    elsewhere = tmp_path / "elsewhere.toml"
    elsewhere.write_text(rendered(REQUESTS))
    (directory / FILE).symlink_to(elsewhere)
    with pytest.raises(Refused, match="is a link"):
        read(directory)
    with pytest.raises(Refused, match="can't write"):
        write(directory, ())
    assert elsewhere.read_text() == rendered(REQUESTS)


def test_a_file_that_is_not_text_is_refused(tmp_path: Path) -> None:
    (tmp_path / FILE).write_bytes(b"\xff\xfe")
    with pytest.raises(Refused, match="not UTF-8"):
        read(tmp_path)
