"""The policy as a function, and the row. Real cells in a real jail are
bh-02/app/tests/test_python_cells.py's: they need a kernel, which is another plugin."""

import asyncio
import contextlib
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from brig_cordis_plugin import (
    MARK,
    SYSTEM_READABLE,
    BrigConfig,
    BrigJail,
    allowlisted,
    git_author,
    graded,
    held,
    holding,
    identity,
    jail,
    made_by_the_jail,
    mountable,
    notice_for,
    readable_roots,
    record_text,
    recorded,
    recorded_group,
    records_dir,
    released_for,
    remove_placeholders,
    self_modify_denied,
    spec_for,
    stack_for,
    still_made,
    told_reads,
    uncovered,
)
from cordis.testing import drive


@dataclass(frozen=True)
class Layers:
    paths: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()


def test_the_spec_denies_what_would_reach_outside_the_jail_later() -> None:
    spec = spec_for(
        root="/w/app",
        endpoint="/tmp/k/k.sock",
        scratch="/tmp/j/tmp",
        home="/Users/me",
        config=BrigConfig(),
        layers=("/w/app/mine.toml", "/elsewhere/chat.toml"),
        host=("/w/app/src", "/usr/lib/python3.15", "/w/app/.venv", "/w/app"),
        secrets=("/src/bh/local.env",),
    )
    assert spec.fs.write_allows == ("/tmp/j/tmp", "/w/app")
    denies = set(spec.fs.write_denies)
    assert {"/w/app/mine.toml", "/elsewhere/chat.toml"} <= denies  # the composition's own files
    assert {
        "/w/app/src",
        "/w/app/.venv",
    } <= denies and "/usr/lib/python3.15" not in denies  # host code inside
    assert "/w/app" not in denies  # the project itself on sys.path (`python -m`) stays writable
    assert {
        "/w/app/.git/hooks",
        "/w/app/.git/config",
        "/w/app/.claude",
    } <= denies  # brig's self-modify list
    assert not {"/w/app/CLAUDE.md", "/w/app/AGENTS.md"} & denies  # but the guidance files: `allow`'s default
    assert "/Users/me/.ssh" in spec.fs.read_denies
    assert "/w/app/local.env" in spec.fs.read_denies  # a credential beside the project
    assert "/src/bh/local.env" in spec.fs.read_denies  # bh-02's own, wherever the project is
    assert "/w/app/local.env" in denies  # one it may not read it may not overwrite either
    assert "/src/bh/local.env" not in denies  # outside every writable root: nothing to deny
    assert dict(spec.env.set) == {"TMPDIR": "/tmp/j/tmp"} and "PATH" in spec.env.allow_names
    assert [c.endpoint for c in spec.channels] == ["/tmp/k/k.sock"]


def test_allow_takes_names_off_brig_s_self_modification_list_and_only_those() -> None:
    assert "CLAUDE.md" not in self_modify_denied(("CLAUDE.md",))
    assert {".git/hooks", ".git/config", "AGENTS.md"} <= set(self_modify_denied(("CLAUDE.md",)))
    assert ".git/config" in self_modify_denied(())  # nothing allowed: the whole list
    with pytest.raises(ValueError) as raised:
        self_modify_denied(("README.md",))
    assert "'README.md'" in str(raised.value) and "use `write`" in str(raised.value)


async def test_the_row_binds_a_brig_jail_over_the_layers_it_was_given() -> None:
    effects = await drive(jail(config=BrigConfig(), layers=Layers()))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "jail")]
    assert isinstance(effects[0].args[1], BrigJail)


def test_on_linux_the_policy_reads_by_allowlist_and_keeps_every_deny() -> None:
    """The same policy, one read model over: what is readable is named, and every read deny
    (credentials, `hide`, `secrets`) is a carve-out inside it; writes and env are untouched,
    but for a secret under the project, whose read mask refuses writes by itself. One the jail
    must `hold` (absent, where bh-02 looks for its credential) keeps its write deny, the only
    thing that stops a cell creating it."""
    policy = spec_for(
        root="/w/app",
        endpoint="/tmp/k/k.sock",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(),
        layers=("/w/app/mine.toml",),
        host=(),
        secrets=("/src/bh/local.env",),
    )
    holding = allowlisted(policy, ("/usr", "/etc", "/opt/py"), hold={"/w/app/local.env"})
    assert holding.fs.write_denies == policy.fs.write_denies  # absent where bh-02 looks: held
    linux = allowlisted(policy, ("/usr", "/etc", "/opt/py"))
    assert linux.fs.read_allows == ("/etc", "/opt/py", "/usr")
    assert linux.fs.read_denies == policy.fs.read_denies
    assert {"/w/app/local.env", "/src/bh/local.env", "/home/me/.ssh"} <= set(linux.fs.read_denies)
    assert "/w/app/local.env" in policy.fs.write_denies and "/w/app/local.env" not in linux.fs.write_denies
    kept = tuple(d for d in policy.fs.write_denies if d != "/w/app/local.env")
    assert (linux.fs.write_allows, linux.fs.write_denies) == (policy.fs.write_allows, kept)
    assert (linux.env, linux.channels) == (policy.env, policy.channels)
    assert linux.fs.read_model.value == "allow_list" and policy.fs.read_model.value == "deny_list"


def test_a_linux_jail_reads_the_system_the_interpreter_and_what_the_command_names() -> None:
    readable = readable_roots(
        argv=["/w/.venv/bin/python", "-I", "/w/src/kernel/worker.py", "/tmp/k/k.sock"],
        interpreter=("/opt/py", "/w/.venv"),
        system=SYSTEM_READABLE,
    )
    assert readable[: len(SYSTEM_READABLE)] == SYSTEM_READABLE
    assert {"/opt/py", "/w/.venv", "/w/.venv/bin", "/w/src/kernel"} <= set(readable)
    assert "/w" not in readable  # not the workspace root, whose local.env a cell must not read
    assert len(readable) == len(set(readable))


def test_what_the_jail_made_on_the_host_is_removed_deepest_first() -> None:
    made = made_by_the_jail(["/w/.git/hooks", "/w/.git", "/w/.envrc", "/w/.git/hooks"])
    assert made == ("/w/.git/hooks", "/w/.envrc", "/w/.git")


def test_a_deny_inside_another_is_left_to_the_outer_one() -> None:
    """An absent secret in a directory the host imports code from: that directory is bound
    read-only already, and a mount point for the secret can't be made on it."""
    denies = uncovered(["/w/pkg/src", "/w/pkg/src/local.env", "/w/pkg/local.env", "/w/pkg/srcx"])
    assert denies == ("/w/pkg/src", "/w/pkg/local.env", "/w/pkg/srcx")


def test_a_linux_jail_holds_the_secrets_under_a_writable_root_and_says_so() -> None:
    """What the jail holds with a mount (a secret under the project) can be undone by the host:
    the grade says best-effort, and the person is told which paths at the start of a session.
    darwin's seatbelt matches paths, so there is nothing to say there."""
    spec = spec_for(
        root="/w/app",
        endpoint="/tmp/k/k.sock",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(),
        layers=(),
        host=(),
        secrets=("/w/app/pkg/local.env", "/src/bh/local.env"),
    )
    assert held(spec) == ("/w/app/local.env", "/w/app/pkg/local.env")  # not ~/.ssh, not /src/bh
    notice = notice_for("linux", held(spec))
    assert "/w/app/local.env, /w/app/pkg/local.env" in notice and "renaming a new file over it" in notice
    assert "`/restart kernel`" in notice and "`/release`" in notice
    assert notice_for("darwin", held(spec)) == "" and notice_for("linux", ()) == ""
    report = {"fs_read": "enforced", "fs_write": "enforced"}
    assert graded(report, held(spec)) == {"fs_read": "best_effort", "fs_write": "enforced"}
    assert graded(report, ()) == report


def test_release_says_where_the_credential_can_go_now_and_what_another_session_still_holds() -> None:
    assert holding(("/w/a/local.env", "/w/local.env", "/x/local.env"), ("/w/.envrc", "/w/local.env")) == (
        "/w/local.env",
    )  # only what the jail mounts over
    free = released_for(["/w/local.env"], [])
    assert free.startswith("Nothing holds /w/local.env until the kernel starts again")
    assert "`/restart model`" in free and "stays held" not in free
    still = released_for([], ["/w/local.env"])
    assert still.startswith("/w/local.env stays held") and "/release again" in still
    assert released_for([], []) == ""


def test_a_linux_jail_carries_the_person_s_git_identity_and_nothing_else_of_their_config() -> None:
    assert git_author("Pat Person", "pat@example.invalid") == (
        ("GIT_AUTHOR_NAME", "Pat Person"),
        ("GIT_AUTHOR_EMAIL", "pat@example.invalid"),
        ("GIT_COMMITTER_NAME", "Pat Person"),
        ("GIT_COMMITTER_EMAIL", "pat@example.invalid"),
    )
    assert git_author("", "pat@example.invalid") == (
        ("GIT_AUTHOR_EMAIL", "pat@example.invalid"),
        ("GIT_COMMITTER_EMAIL", "pat@example.invalid"),
    )  # what git doesn't know is left for git to say
    assert git_author("", "") == ()


def test_a_deny_under_a_file_becomes_a_deny_of_the_file() -> None:
    """A worktree's `.git` is a `gitdir:` file: no mount point can be made under it, so its
    carve-outs become the file itself, once."""
    blocked = {"/w/.git/hooks": "/w/.git", "/w/.git/config": "/w/.git"}
    denies = mountable(["/w/.git/hooks", "/w/.git/config", "/w/.envrc"], blocked)
    assert denies == ("/w/.git", "/w/.envrc")


_LISTEN_THEN_WRITE = """
import os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
while True:
    time.sleep(0.1)
    try:
        os.makedirs(sys.argv[2], exist_ok=True)
        open(os.path.join(sys.argv[2], "settings.json"), "w").write("x")
    except OSError:
        pass
"""


_LISTEN_THEN_READ_AND_PLANT = """
import os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
secret, absent, seen = sys.argv[2:5]
while True:
    time.sleep(0.1)
    try:
        text = open(secret).read()
        open(seen, "w").write(text)
    except OSError:
        pass
    try:
        open(absent, "w").write("PLANTED=1")
    except OSError:
        pass
"""


async def test_a_linux_jail_s_hold_on_a_secret_ends_when_the_host_replaces_or_removes_it(
    tmp_path: Path,
) -> None:
    """What bubblewrap can't close, measured so the grade and the notice stay honest: the jail
    holds a secret under the project with a mount on its path (a `/dev/null` over the file, an
    empty directory where there is none). Replace the file on the host the way an editor saves
    (a new file renamed over it), or remove the empty directory, and the mount is detached
    inside the jail: the workload reads the new file, and creates the absent one. Until then it
    can do neither. So `fs_read` is best-effort and the jail names both paths in its notice."""
    if sys.platform != "linux" or not Path("/usr/bin/bwrap").exists():
        pytest.skip("the mounts are bubblewrap's: Linux with /usr/bin/bwrap only")
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    secret, absent, seen = project / "local.env", project / "pkg" / "local.env", project / "seen"
    secret.write_text("OLD=1\n")  # a stand-in: never the real file
    one = BrigJail(BrigConfig(), Layers(credentials=(str(absent),), secrets=(str(absent),)))
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [
        sys.executable,
        "-I",
        "-c",
        _LISTEN_THEN_READ_AND_PLANT,
        endpoint,
        str(secret),
        str(absent),
        str(seen),
    ]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
    try:
        assert one.report()["fs_read"] == "best_effort"
        assert f"{secret}, {absent}" in one.notice()
        await asyncio.sleep(0.5)
        assert not seen.exists() and absent.is_dir()  # held: neither read nor created
        (project / "saved.tmp").write_text("NEW=1\n")
        (project / "saved.tmp").replace(secret)  # an editor's save
        absent.rmdir()  # a placeholder removed by hand
        await asyncio.sleep(1.0)
        assert seen.read_text() == "NEW=1\n"  # the new file reads inside the jail
        assert absent.read_text() == "PLANTED=1"  # and the absent one was created
    finally:
        await started.stop()


_LISTEN_THEN_APPEND = """
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
while True:
    time.sleep(0.1)
    try:
        with open(sys.argv[2], "a") as config:
            config.write("# planted by the jail\\n")
    except OSError:
        pass
"""


async def test_a_linux_write_deny_ends_when_the_host_renames_over_it_until_a_new_jail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What `fs_write`'s `enforced` does not cover, measured so the docs stay honest: the jail
    holds `.git/config` read-only with a bind mount on its path. A host `git config` saves the
    file by renaming a new one over it, which detaches that mount inside the jail, and the
    workload can then write the file. A new jail (`/restart kernel`) holds it again."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    made = await asyncio.create_subprocess_exec("git", "init", "-q", str(project))
    assert await made.wait() == 0
    config = project / ".git" / "config"

    async def jailed() -> Any:
        sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
        endpoint = str(sock_dir / "k.sock")
        argv = [sys.executable, "-I", "-c", _LISTEN_THEN_APPEND, endpoint, str(config)]
        return await BrigJail(BrigConfig(), Layers()).start(argv, cwd=str(project), endpoint=endpoint)

    started = await jailed()
    try:
        await asyncio.sleep(0.5)
        assert "planted" not in config.read_text()  # held
        git = await asyncio.create_subprocess_exec("git", "-C", str(project), "config", "user.name", "Pat")
        assert await git.wait() == 0
        await asyncio.sleep(0.5)
        assert "planted" in config.read_text()  # the host's rename lifted the deny
    finally:
        await started.stop()
    git = await asyncio.create_subprocess_exec("git", "-C", str(project), "config", "--unset", "user.name")
    assert await git.wait() == 0
    config.write_text(config.read_text().replace("# planted by the jail\n", ""))
    started = await jailed()
    try:
        await asyncio.sleep(0.5)
        assert "planted" not in config.read_text()  # a new jail holds it again
    finally:
        await started.stop()


def test_a_jail_s_record_of_its_placeholders_is_in_bh_02_s_state_directory() -> None:
    assert records_dir({"XDG_STATE_HOME": "/x"}, "/home/me") == "/x/bh-02/jails"
    assert records_dir({}, "/home/me") == "/home/me/.local/state/bh-02/jails"
    made = [("/w/.git/hooks", "12:1700000000000000000"), ("/w/.git", None)]
    assert recorded(record_text(made)) == made
    assert recorded("not json") == [] and recorded('{"made": 3}') == []  # a broken record names none


def test_only_a_placeholder_still_as_the_jail_made_it_is_removed(tmp_path: Path) -> None:
    """Empty and unchanged: removed, deepest first. One the person put a file in, one they
    replaced with a directory of their own (even on the same inode), and one recorded by path
    alone (an older record, with nothing to prove a jail made it) are kept."""
    ours, early, filled, theirs = (tmp_path / n for n in ("ours", "early", "filled", "theirs"))
    for path in (ours, early / "inner", filled, theirs):
        path.mkdir(parents=True)
    made = [(str(p), identity(p.stat())) for p in (ours, filled, theirs)]
    made += [(str(early / "inner"), None), (str(early), None), (str(tmp_path / "gone"), None)]
    (filled / "mine.txt").write_text("x")
    theirs.rmdir()
    time.sleep(0.05)  # the person's own comes later: a later change time, on the kernel's clock tick
    theirs.mkdir()
    remove_placeholders(made)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["early", "filled", "theirs"]
    assert (early / "inner").is_dir()


def test_a_placeholder_is_known_by_the_jail_s_mark_else_by_its_identity() -> None:
    assert not still_made(None, "1:2", None)  # by path alone: nothing proves a jail made it
    assert not still_made(None, "1:2", "bh-j-1")
    assert still_made("mark:bh-j-1", "1:2", "bh-j-1") and not still_made("mark:bh-j-1", "1:2", None)
    assert not still_made("mark:bh-j-1", "1:2", "bh-j-2")  # another jail's
    assert still_made("1:2", "1:2", None) and not still_made("1:2", "1:3", None)


def test_the_model_is_told_the_trees_a_jail_reads_the_same_at_every_start() -> None:
    trees = ("/usr", "/tmp/bh-k-a1", "/w/app", "/tmp/bh-j-b2/tmp", "/usr")
    assert told_reads(trees, ("/tmp/bh-j-b2", "/tmp/bh-k-a1")) == ("/usr", "/w/app", "$TMPDIR")


def _needs_bwrap() -> None:
    if sys.platform != "linux" or not Path("/usr/bin/bwrap").exists():
        pytest.skip("the placeholders are bubblewrap's: Linux with /usr/bin/bwrap only")


# A bh-02 that crashes once its jailed kernel is up: no `stop`, so nothing it made is removed.
# Its worker listens for a moment and exits, as an orphaned kernel with no host would be ended.
_CRASH = """
import asyncio, os, sys, tempfile
from pathlib import Path
from brig_cordis_plugin import BrigConfig, BrigJail

class Layers:
    paths, credentials, secrets = (), (), ()

async def main():
    sock = str(Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"), "k.sock"))
    worker = (
        "import socket, sys, time; s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); "
        "s.listen(1); time.sleep(2)"
    )
    argv = [sys.executable, "-I", "-c", worker, sock]
    await BrigJail(BrigConfig(), Layers()).start(argv, cwd=sys.argv[1], endpoint=sock)
    os._exit(9)

asyncio.run(main())
"""


# A bh-02 killed while its kernel runs a cell's background program, which keeps trying to write
# under `.claude/` (Claude Code would run hooks from its settings) and says it is alive: the real
# kernel, in the real jail. argv: the project, then "setsid" to start the program in a session
# of its own (out of the jail's process group), else "group". It says "started" and waits to be
# killed.
_KILLED_WITH_A_BACKGROUND_CELL = """
import asyncio, sys, time
from brig_cordis_plugin import BrigConfig, BrigJail
from kernel_cordis_plugin import Kernel, KernelConfig

class Layers:
    paths, credentials, secrets = (), (), ()

LOOP = (
    "import os, sys, time\\n"
    "open(sys.argv[1] + '.pid', 'w').write(str(os.getpid()))\\n"
    "while True:\\n"
    "    open(sys.argv[1], 'w').write(str(time.time()))\\n"
    "    try:\\n"
    "        os.makedirs('.claude', exist_ok=True)\\n"
    "        open('.claude/settings.json', 'w').write('{}')\\n"
    "    except OSError:\\n"
    "        pass\\n"
    "    time.sleep(0.1)\\n"
)

async def main():
    kernel = Kernel(BrigJail(BrigConfig(), Layers()), KernelConfig(root=sys.argv[1]))
    await kernel.__aenter__()
    setsid = sys.argv[2] == "setsid"
    cell = (
        "import subprocess, sys\\n"
        f"subprocess.Popen([sys.executable, '-c', {LOOP!r}, 'alive'], start_new_session={setsid})\\n"
        "print('started')"
    )
    print(await kernel.run(cell), flush=True)
    time.sleep(600)

asyncio.run(main())
"""


async def _killed_with_a_background_cell(project: Path, how: str) -> None:
    """Run `_KILLED_WITH_A_BACKGROUND_CELL` in `project`, see the program write, then `SIGKILL`
    the stand-in bh-02, as a crash or `kill -9` would end it."""
    killed = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _KILLED_WITH_A_BACKGROUND_CELL,
        str(project),
        how,
        stdout=asyncio.subprocess.PIPE,
    )
    assert killed.stdout is not None
    said = await asyncio.wait_for(killed.stdout.readline(), 30)
    assert b"started" in said, said
    alive = project / "alive"
    for _ in range(50):
        if alive.exists():
            break
        await asyncio.sleep(0.1)
    killed.kill()
    assert await killed.wait() == -signal.SIGKILL


async def _still_writing(alive: Path) -> bool:
    last = alive.read_text()
    await asyncio.sleep(0.6)
    return alive.read_text() != last


async def test_a_killed_bh_02_s_jail_ends_with_it_and_the_next_jail_removes_what_it_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bh-02 killed with SIGKILL while a program a cell started runs in the background, in a
    session of its own: the jail ends with bh-02 (brig's tether: the kernel closes bh-02's end,
    and brig's watcher kills the jail's process group, bubblewrap's namespace with it, so a
    program that left the group goes too). Its record now names a group that is gone, so the
    next jail's sweep removes its placeholders and the record."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    await _killed_with_a_background_cell(project, "setsid")
    (record,) = (tmp_path / "state" / "bh-02" / "jails").iterdir()
    group = recorded_group(record.read_text())
    assert group is not None
    await asyncio.sleep(1.0)
    try:
        assert not await _still_writing(project / "alive")  # the program is gone
        with pytest.raises(ProcessLookupError):
            os.killpg(group, 0)  # and the whole jail
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(group, signal.SIGKILL)
    assert (project / ".claude").is_dir() and not list((project / ".claude").iterdir())
    one = BrigJail(BrigConfig(), Layers())
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()  # the sweep ran
    assert sorted(p.name for p in project.iterdir()) == ["alive", "alive.pid"]
    assert list((tmp_path / "state" / "bh-02" / "jails").iterdir()) == []


async def test_a_killed_bh_02_s_seatbelt_jail_ends_with_it_but_not_a_program_that_left_its_group(
    tmp_path: Path,
) -> None:
    """darwin: bh-02 killed with SIGKILL takes a program a cell left running with it (brig's
    tether kills the jail's process group). seatbelt has no namespace, so a program a cell
    started in a session of its own is out of that group and lives on, as it does past a normal
    stop (brig's teardown is group-shaped too): measured, so the README's gap stays honest."""
    if sys.platform != "darwin":
        pytest.skip("seatbelt is darwin's")
    grouped, setsid = tmp_path / "grouped", tmp_path / "setsid"
    grouped.mkdir()
    setsid.mkdir()
    await _killed_with_a_background_cell(grouped, "group")
    await _killed_with_a_background_cell(setsid, "setsid")
    escaped = int((setsid / "alive.pid").read_text())
    await asyncio.sleep(1.0)
    try:
        assert not await _still_writing(grouped / "alive")
        with pytest.raises(ProcessLookupError):
            os.kill(int((grouped / "alive.pid").read_text()), 0)
        assert await _still_writing(setsid / "alive")  # the gap
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(escaped, signal.SIGKILL)


async def test_the_sweep_leaves_a_record_whose_process_group_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tether ends a killed bh-02's jail at once, but not before the next jail can look
    (and a jail brig launched some other way has none): a record whose process group runs is
    left, placeholders and all, since removing one would detach that jail's mount. A process
    group of the test's own stands in for the jail."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    held = project / ".claude"
    held.mkdir(parents=True)
    records = tmp_path / "state" / "bh-02" / "jails"
    records.mkdir(parents=True)
    living = await asyncio.create_subprocess_exec("sleep", "60", start_new_session=True)
    record = records / "bh-j-living.json"
    record.write_text(record_text([(str(held), identity(held.stat()))], living.pid))
    try:
        one = BrigJail(BrigConfig(), Layers())
        sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
        endpoint = str(sock_dir / "k.sock")
        argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
        await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()
        assert held.is_dir() and record.exists()
    finally:
        living.kill()
        await living.wait()
    one = BrigJail(BrigConfig(), Layers())
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()
    assert not held.exists() and not record.exists()  # its group gone, so are they


# A bh-02 that crashes the moment it would start bubblewrap: what its jail holds on the host is
# there, and nothing of it was mounted yet.
_CRASH_AT_LAUNCH = """
import os, sys, tempfile
from pathlib import Path
import asyncio
from brig.run import SubprocessLauncher
from brig_cordis_plugin import BrigConfig, BrigJail

class Layers:
    paths, credentials, secrets = (), (), ()

def crash(self, *args, **kwargs):
    os._exit(9)

SubprocessLauncher.launch = crash
sock = str(Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"), "k.sock"))
argv = [sys.executable, "-c", "pass"]
asyncio.run(BrigJail(BrigConfig(), Layers()).start(argv, cwd=sys.argv[1], endpoint=sock))
"""


async def test_a_placeholder_is_made_and_marked_before_bubblewrap_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The jail makes each placeholder itself, marked as its own (`MARK`) the moment it is made,
    and only then starts bubblewrap, which finds it there. So a bh-02 that dies before its jail
    is up leaves only placeholders the next sweep can prove are a jail's, and removes."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    crash = await asyncio.create_subprocess_exec(sys.executable, "-c", _CRASH_AT_LAUNCH, str(project))
    assert await crash.wait() == 9
    (record,) = (tmp_path / "state" / "bh-02" / "jails").iterdir()
    left = sorted(p.name for p in project.iterdir())
    assert {".claude", ".vscode", ".envrc", ".git"} <= set(left), left
    if sys.platform == "linux":  # os.getxattr is Linux's
        assert {os.getxattr(project / name, MARK).decode() for name in left} == {record.stem}
    one = BrigJail(BrigConfig(), Layers())
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()
    assert list(project.iterdir()) == [] and not record.exists()


async def test_a_jail_that_fails_to_launch_leaves_nothing_on_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its placeholders are made before bubblewrap starts, so a launch that fails (or is
    cancelled) removes them again, with its record, as a stop would."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()

    def refused(self: object, *args: object, **kwargs: object) -> None:
        raise RuntimeError("no launch today")

    monkeypatch.setattr("brig.run.SubprocessLauncher.launch", refused)
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    with pytest.raises(RuntimeError, match="no launch today"):
        await BrigJail(BrigConfig(), Layers()).start(
            [sys.executable, "-c", "pass"], cwd=str(project), endpoint=str(sock_dir / "k.sock")
        )
    assert list(project.iterdir()) == []
    assert list((tmp_path / "state" / "bh-02" / "jails").iterdir()) == []


async def test_a_jail_start_cancelled_while_it_launches_ends_what_the_launch_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launch runs in a thread, which a cancellation doesn't stop: the start waits for it,
    ends the jail it started, and only then removes the placeholders and closes the tether."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    real = subprocess.Popen
    groups: list[int] = []

    def slow(args: Sequence[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        if any("brig exit wrapper" in str(arg) for arg in args):  # brig's launch, in its thread
            time.sleep(0.5)
            launched = real(args, **kwargs)
            groups.append(launched.pid)  # a new session: its pid is its group
            return launched
        return real(args, **kwargs)

    monkeypatch.setattr("subprocess.Popen", slow)
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    starting = asyncio.ensure_future(
        BrigJail(BrigConfig(), Layers()).start(argv, cwd=str(project), endpoint=endpoint)
    )
    await asyncio.sleep(0.1)
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    assert groups  # the start returned only once the launch had
    await asyncio.sleep(1.0)
    (group,) = groups
    with pytest.raises(ProcessLookupError):
        os.killpg(group, 0)
    assert list(project.iterdir()) == []
    assert list((tmp_path / "state" / "bh-02" / "jails").iterdir()) == []


async def test_a_record_with_unmarked_paths_removes_nothing_it_can_t_prove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record by path alone (what a crash between writing a record and marking left, before
    placeholders were marked as they were made): the person has since made an empty directory
    at one of its paths. The sweep can't tell it from a placeholder, so it leaves it, and the
    record goes."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    mine = project / "build"
    mine.mkdir(parents=True)  # the person's, empty
    records = tmp_path / "state" / "bh-02" / "jails"
    records.mkdir(parents=True)
    record = records / "bh-j-crashed.json"
    record.write_text(record_text([(str(mine), None), (str(project / "gone"), None)]))
    one = BrigJail(BrigConfig(), Layers())
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()
    assert mine.is_dir() and not record.exists()


def test_a_record_names_the_jail_s_process_group() -> None:
    text = record_text([("/w/.claude", None)], 4242)
    assert recorded_group(text) == 4242 and recorded(text) == [("/w/.claude", None)]
    assert recorded_group(record_text([("/w/.claude", None)])) is None  # before bwrap started
    assert recorded_group("not json") is None


async def _crashed_in(project: Path) -> None:
    crash = await asyncio.create_subprocess_exec(sys.executable, "-c", _CRASH, str(project))
    assert await crash.wait() == 9
    await asyncio.sleep(3.0)  # its orphaned worker ends, and with it the jail's mounts


async def test_placeholders_a_crashed_session_left_are_removed_by_the_next_jail_and_only_those(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session that crashes never removes its placeholders. The next jail to start with no
    other bh-02 jail running removes them, by the record the crashed one kept in the user's
    state directory: only an empty directory still the one it made. `.claude/` the person has
    put a file in, and a `.vscode/` the person made again after the crash, stay."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    await _crashed_in(project)
    left = sorted(p.name for p in project.iterdir())
    assert {".claude", ".vscode", ".envrc", ".git"} <= set(left), left  # what the crash left
    assert list((tmp_path / "state" / "bh-02" / "jails").iterdir())  # and its record
    (project / ".claude" / "mine.json").write_text("{}")  # the person's, since
    (project / ".vscode").rmdir()
    (project / ".vscode").mkdir()  # the person's own, made again
    one = BrigJail(BrigConfig(), Layers())
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
    await started.stop()
    assert sorted(p.name for p in project.iterdir()) == [".claude", ".vscode"]
    assert list((project / ".claude").iterdir()) == [project / ".claude" / "mine.json"]
    assert list((tmp_path / "state" / "bh-02" / "jails").iterdir()) == []  # no record outlives its jail


async def test_git_init_on_the_host_works_while_a_jail_runs_in_a_project_that_is_no_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project that isn't a repository has no `.git`, so the jail holds `.git` itself (an empty
    directory) rather than a `.git/config` directory inside it, which would break the person's
    own `git init`. That works on the host while the kernel runs; inside the jail `.git` stays
    what it was held as, and the new repository outlives the jail."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    one = BrigJail(BrigConfig(), Layers())
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    git_config = project / ".git" / "config"
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(git_config)]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
    try:
        assert (project / ".git").is_dir() and not git_config.exists()  # held whole: nothing inside
        made = await asyncio.create_subprocess_exec("git", "init", "-q", str(project))
        assert await made.wait() == 0
        assert git_config.is_file()
        await asyncio.sleep(0.5)  # the workload keeps trying to write under .git/config
        assert not (git_config / "settings.json").exists()
    finally:
        await started.stop()
    assert git_config.is_file()  # the person's repository stays


async def test_a_second_jail_s_carve_out_outlives_the_first_jail_in_the_same_project(
    tmp_path: Path,
) -> None:
    """Two kernels in one project (two sessions). The first makes the empty `.claude/` it mounts
    over; the second, starting while it lives, binds that directory read-only over itself. When
    the first stops it must not remove it: removed on the host, the second's bind is detached
    and the second writes `.claude/settings.json`, which Claude Code would run hooks from.
    Linux only, with bubblewrap: the placeholders are bubblewrap's."""
    if sys.platform != "linux" or not Path("/usr/bin/bwrap").exists():
        pytest.skip("the placeholders are bubblewrap's: Linux with /usr/bin/bwrap only")
    project = tmp_path / "project"
    project.mkdir()
    claude = project / ".claude"
    jails = [BrigJail(BrigConfig(), Layers()) for _ in range(2)]
    started = []
    for n, one in enumerate(jails):
        sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
        endpoint = str(sock_dir / "k.sock")
        argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(claude)]
        started.append(await one.start(argv, cwd=str(project), endpoint=endpoint))
        assert claude.is_dir(), n  # the first made it; the second found it
    await started[0].stop()
    await asyncio.sleep(1.0)  # the second's workload keeps trying to write under .claude
    try:
        assert claude.is_dir() and not (claude / "settings.json").exists()
    finally:
        await started[1].stop()
    assert not (claude / "settings.json").exists()


def test_a_platform_brig_has_no_preset_for_is_refused_by_name() -> None:
    assert stack_for("darwin") and stack_for("linux")
    with pytest.raises(RuntimeError, match=r"this is freebsd.*`kernel:unjailed`"):
        stack_for("freebsd")
    assert BrigJail(BrigConfig(), Layers(), platform="freebsd").report() == {}


def test_the_linux_jail_compiles_the_policy_with_bubblewrap_and_masks_the_project_s_secret(
    tmp_path: Path,
) -> None:
    """The compile half of the Linux jail, which runs anywhere (the enforcement half is
    `scripts/linux-jail-check`'s): the grades a cell is confined by, and the project's own
    `local.env` masked on the command line, because it exists; absent, named instead, and held
    by a read-only empty directory only where bh-02 looks for its credential. Either way
    `fs_read` is best-effort: the mount is on the host's directory entry, which the host can
    replace (an editor's save)."""
    project = tmp_path / "project"
    project.mkdir()
    secret = project / "local.env"
    jail = BrigJail(BrigConfig(), Layers(), platform="linux")
    report = jail.report()
    assert report["fs_write"] == report["network"] == report["env"] == "enforced"

    compiled, graded = jail.compile(str(tmp_path / "j"), str(tmp_path / "k" / "k.sock"), str(project), ())
    detail = next(g.detail for axis, g in compiled.report.axes.items() if axis.value == "fs_read")
    assert graded["fs_read"] == "best_effort" and str(secret.resolve()) in detail
    assert str(secret.resolve()) not in compiled.wrap(("w",))  # the project's own: nothing made
    looked = BrigJail(BrigConfig(), Layers(credentials=(str(secret.resolve()),)), platform="linux")
    compiled, graded = looked.compile(str(tmp_path / "j"), str(tmp_path / "k" / "k.sock"), str(project), ())
    argv = compiled.wrap(("w",))
    at = argv.index(str(secret.resolve()))
    assert argv[at - 1 : at + 3] == ("--tmpfs", str(secret.resolve()), "--remount-ro", str(secret.resolve()))

    secret.write_text("NOT_A_REAL_CREDENTIAL=placeholder\n")  # a stand-in: never the real file
    compiled, graded = jail.compile(str(tmp_path / "j"), str(tmp_path / "k" / "k.sock"), str(project), ())
    argv = compiled.wrap(("w",))
    at = argv.index(str(secret.resolve()))
    assert argv[at - 2 : at + 1] == ("--ro-bind", "/dev/null", str(secret.resolve()))
    assert argv.count(str(secret.resolve())) == 1  # the mask alone: no write deny under it
    assert graded["fs_read"] == "best_effort"
    assert graded["fs_write"] == graded["network"] == "enforced"
