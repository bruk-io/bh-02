"""A session is held by the one bh-02 running it: a second `--resume` of it is refused before a row
starts, the lock goes with the process however it ends, and reading a held session takes no lock."""

import contextlib
import fcntl
import json
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from bh_02 import main
from bh_02.sessions import Held, Session, create, held

# Another bh-02 holding a session: a process of its own that takes the lock (`held`, as the command
# does) and starts a child that outlives it, since a child that kept the lock would keep the session
# held after the holder's death. It prints `held CHILD_PID` once the lock is taken.
_HOLDER = """
import subprocess
import sys
import time
from pathlib import Path

from bh_02.sessions import Session, held

directory = Path(sys.argv[1])
with held(Session(directory.name, directory, "", "", "")):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    print("held", child.pid, flush=True)
    time.sleep(600)
"""


class _Holder:
    """A running holder process, and the child it started."""

    def __init__(self, directory: Path) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-c", _HOLDER, str(directory)], stdout=subprocess.PIPE, text=True
        )
        assert self.process.stdout is not None
        word, child = self.process.stdout.readline().split()
        assert word == "held", "the holder did not take the lock"
        self.child = int(child)

    def crash(self) -> None:
        """Kill it as a crash does: no cleanup runs, the child lives on."""
        self.process.kill()
        self.process.wait()

    def close(self) -> None:
        self.process.kill()
        self.process.wait()
        assert self.process.stdout is not None
        self.process.stdout.close()
        with contextlib.suppress(ProcessLookupError):
            os.kill(self.child, signal.SIGKILL)


@pytest.fixture
def holding() -> Iterator[Callable[[Path], _Holder]]:
    started: list[_Holder] = []

    def start(directory: Path) -> _Holder:
        started.append(_Holder(directory))
        return started[-1]

    yield start
    for holder in started:
        holder.close()


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return tmp_path / "state" / "bh-02" / "sessions"


def _session(state: Path) -> Session:
    return create(state, str(Path.cwd()), model="work/opus", no_jail=True)


def _ran(composition: Callable[..., Path]) -> Path:
    """A layer that runs one message and ends, for a `--resume` that comes up and leaves."""
    return composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
    )


def test_a_session_is_held_by_one_holder_at_a_time_and_free_when_the_block_ends(state: Path) -> None:
    session = _session(state)
    with held(session):
        with pytest.raises(Held) as refused, held(session):
            pytest.fail("a second hold of a held session must be refused")
        assert refused.value.message.startswith(
            f"session {session.id} is held by bh-02 process {os.getpid()}"
        )
        assert "Leave that bh-02 first" in refused.value.message  # and what to do
    with held(session):  # the block ended: the lock went with it
        pass


def test_a_holder_whose_pid_is_not_written_yet_is_refused_without_a_process_named(state: Path) -> None:
    """The window between taking the lock and writing the pid: the lock is the claim, not the pid."""
    session = _session(state)
    descriptor = os.open(session.dir / "running.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(Held) as refused, held(session):
            pytest.fail("a held session must be refused")
        assert refused.value.message.startswith(f"session {session.id} is held by another bh-02,")
    finally:
        os.close(descriptor)


def test_the_lock_is_only_a_file_in_the_session_directory_made_for_its_owner_alone(state: Path) -> None:
    session = _session(state)
    with held(session):
        lock = session.dir / "running.lock"
        assert lock.read_text() == f"{os.getpid()}\n"
        assert lock.stat().st_mode & 0o777 == 0o600


def test_resume_of_a_session_another_process_holds_is_refused_before_any_row_starts(
    composition: Callable[..., Path],
    state: Path,
    tmp_path: Path,
    holding: Callable[[Path], _Holder],
) -> None:
    runner = CliRunner()
    patch = _ran(composition)
    assert runner.invoke(main, ["--no-jail", "--patch", str(patch)]).exit_code == 0
    (session,) = [path for path in state.iterdir() if path.is_dir()]
    layer = (session / "session.toml").read_text()
    other = holding(session)

    trace = tmp_path / "trace.log"
    refused = runner.invoke(
        main,
        ["--resume", session.name, "--model", "claude/haiku", "--patch", str(patch), "--trace", str(trace)],
    )

    assert refused.exit_code == 1, refused.output
    assert refused.stderr.startswith(
        f"error: session {session.name} is held by bh-02 process {other.process.pid}"
    )
    assert "Leave that bh-02 first" in refused.stderr
    assert not trace.exists()  # no row started: the trace file is opened by the run, which never began
    assert (session / "session.toml").read_text() == layer  # --model did not rewrite the held session's layer
    assert "did not start" not in refused.stderr and "to continue it" not in refused.stderr
    assert runner.invoke(main, ["sessions"]).stdout.count("\n") == 1  # and it was not discarded

    other.crash()  # the holder dies without cleaning up, its child still alive
    again = runner.invoke(main, ["--resume", session.name, "--patch", str(patch)])
    assert again.exit_code == 0, again.output  # the system released the lock; the child holds none
    assert "(uv run bh-02 --resume to continue it)" in again.stderr


def test_sessions_trajectory_and_watch_read_a_held_session_as_before(
    composition: Callable[..., Path], state: Path, holding: Callable[[Path], _Holder]
) -> None:
    session = _session(state)
    (session.dir / "transcript.jsonl").write_text(
        json.dumps({"role": "user", "content": "in the held one", "at": "2026-10-18T03:00:00.000Z"}) + "\n"
    )
    agent = session.dir / "agents" / "general-1"
    agent.mkdir(parents=True, mode=0o700)
    (agent / "events.jsonl").write_text(
        json.dumps({"at": "2026-10-18T03:00:01.000+00:00", "event": {"type": "text", "text": "counting"}})
        + "\n"
    )
    other = holding(session.dir)
    runner = CliRunner()

    listed = runner.invoke(main, ["sessions"])
    assert listed.exit_code == 0 and listed.stdout.startswith(session.id), listed.output
    shown = runner.invoke(main, ["trajectory", session.id])
    assert shown.exit_code == 0 and "in the held one" in shown.stdout, shown.output
    watched = runner.invoke(main, ["watch", session.id, "general-1", "--once"])
    assert watched.exit_code == 0 and "counting" in watched.stdout, watched.output

    # and they took nothing: the holder still holds it, and a resume still names it
    assert (session.dir / "running.lock").read_text() == f"{other.process.pid}\n"
    refused = runner.invoke(main, ["--resume", session.id, "--patch", str(_ran(composition))])
    assert refused.exit_code == 1 and f"bh-02 process {other.process.pid}" in refused.stderr
