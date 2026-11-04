"""`bh-02 grants` and `bh-02 grants revoke ID`: the project's always-grants, listed and taken back
outside a session, through the runner plugin's broker booted by name (the app imports no plugin)."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from bh_02 import main
from bh_02.bootstrap import grants_directory
from runner_cordis_plugin import Broker
from runner_cordis_plugin.grants import Asker, Grant, Kind, Request, Source
from runner_cordis_plugin.store import FILE, read, write

_NET = Request(Grant(Kind.NET, "example.com", 443), Asker(Source.ROW, "python"), "fetch packages")
_DATA = Request(Grant(Kind.READ, "/data/in"), Asker(Source.INPUT, "python"), "reads the data")


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """This project's grants store, as a start of bh-02 here would make it."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    directory = Path(grants_directory(work.resolve(), {"XDG_STATE_HOME": str(tmp_path / "state")}, tmp_path))
    directory.mkdir(parents=True, mode=0o700)
    yield directory


def test_it_lists_what_the_project_always_grants_with_who_asked_and_why(store: Path) -> None:
    write(store, [_NET, _DATA])
    result = CliRunner().invoke(main, ["grants"])
    assert result.exit_code == 0, result.output
    first, second = result.output.splitlines()
    assert "net example.com:443" in first and "always (project)" in first
    assert "row python: fetch packages" in first
    assert "read /data/in" in second and "input python: reads the data" in second


def test_it_says_when_nothing_is_granted_and_when_the_project_has_no_store_yet(
    store: Path, tmp_path: Path
) -> None:
    result = CliRunner().invoke(main, ["grants"])
    assert result.exit_code == 0 and "nothing is granted" in result.output
    store.rmdir()
    result = CliRunner().invoke(main, ["grants"])
    assert result.exit_code == 0 and "nothing is granted" in result.output


def test_a_revoked_always_grant_is_gone_at_the_next_start(store: Path) -> None:
    write(store, [_NET, _DATA])
    (id_net, _) = (line.split()[0] for line in CliRunner().invoke(main, ["grants"]).output.splitlines())
    result = CliRunner().invoke(main, ["grants", "revoke", id_net])
    assert result.exit_code == 0, result.output
    assert result.output.startswith(f"revoked: {id_net}")
    assert "A session running now keeps it until its next start" in result.output
    assert "`/grants revoke` it in that session" in result.output
    assert read(store) == (_DATA,)
    # a session's next start reads the store afresh
    assert asyncio.run(Broker(store).granted()).items == (_DATA.grant,)
    assert [line.split()[0] for line in CliRunner().invoke(main, ["grants"]).output.splitlines()] != [id_net]


def test_an_unknown_id_exits_1_and_lists_the_ids_there_are(store: Path) -> None:
    write(store, [_NET])
    (listed,) = CliRunner().invoke(main, ["grants"]).output.splitlines()
    result = CliRunner().invoke(main, ["grants", "revoke", "deadbeef"])
    assert result.exit_code == 1
    assert "no grant has id 'deadbeef'" in result.output and listed.split()[0] in result.output
    assert read(store) == (_NET,)


def test_a_store_that_cannot_be_used_is_said_and_never_written_over(store: Path) -> None:
    (store / FILE).write_text("not toml = =")
    result = CliRunner().invoke(main, ["grants"])
    assert result.exit_code == 0 and "not TOML" in result.output
    result = CliRunner().invoke(main, ["grants", "revoke", "deadbeef"])
    assert result.exit_code == 1 and "not TOML" in result.output
    assert (store / FILE).read_text() == "not toml = ="


def test_revoking_where_the_project_has_no_store_says_so(store: Path) -> None:
    store.rmdir()
    result = CliRunner().invoke(main, ["grants", "revoke", "deadbeef"])
    assert result.exit_code == 1 and "no grants yet" in result.output
