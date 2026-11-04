"""Where a project's always-grants are kept (`host.grants`) and that they outlive bh-02: the
directory is keyed as auto memory is, so a restart in the same project finds them and another
project does not."""

import os
import subprocess
import sys
from pathlib import Path

from bh_02.bootstrap import grants_directory, memory_directory
from runner_cordis_plugin.grants import Asker, Grant, Kind, Request, Source
from runner_cordis_plugin.store import read, write

_ASKED = Request(Grant(Kind.NET, "example.com", 443), Asker(Source.ROW, "python"), "fetch packages")

# The part of a bh-02 start that matters here, as a program of its own: make the project's directory
# (as the command line does) and print what the store holds, one grant a line.
_START = """
import os, sys
from pathlib import Path
from bh_02.bootstrap import grants_directory
from runner_cordis_plugin.store import read, write
from runner_cordis_plugin.grants import Asker, Grant, Kind, Request, Source
directory = Path(grants_directory(Path(sys.argv[1]), os.environ, Path.home()))
directory.mkdir(mode=0o700, parents=True, exist_ok=True)
if sys.argv[2] == "grant":
    ask = Request(Grant(Kind.NET, "example.com", 443), Asker(Source.ROW, "python"), "fetch packages")
    write(directory, [ask])
print("\\n".join(str(r.grant) for r in read(directory)))
"""


def test_the_directory_is_beside_auto_memory_keyed_the_same_way(tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert grants_directory(Path("/home/me/my.app"), {}, home) == str(
        home / ".local/state/bh-02/projects/-home-me-my-app/grants"
    )
    assert (
        grants_directory(Path("/w"), {"XDG_STATE_HOME": "/state"}, home) == "/state/bh-02/projects/-w/grants"
    )
    memory = Path(memory_directory(Path("/w"), {}, home))
    assert Path(grants_directory(Path("/w"), {}, home)).parent == memory.parent


def test_an_always_grant_survives_a_restart_in_the_same_project_and_is_absent_in_another(
    tmp_path: Path,
) -> None:
    environment = {**os.environ, "HOME": str(tmp_path / "home"), "XDG_STATE_HOME": str(tmp_path / "state")}

    def start(project: str, what: str) -> list[str]:
        done = subprocess.run(
            [sys.executable, "-I", "-c", _START, project, what],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        return [line for line in done.stdout.splitlines() if line]

    assert start("/w/one", "none") == []
    assert start("/w/one", "grant") == ["net: example.com:443"]
    assert start("/w/one", "none") == ["net: example.com:443"]  # a new process: it was kept
    assert start("/w/two", "none") == []  # another project has none
    directory = Path(environment["XDG_STATE_HOME"], "bh-02/projects/-w-one/grants")
    assert read(directory) == (_ASKED,)
    assert oct(directory.stat().st_mode & 0o777) == "0o700"
    assert oct((directory / "grants.toml").stat().st_mode & 0o777) == "0o600"
    write(directory, ())
    assert start("/w/one", "none") == []
