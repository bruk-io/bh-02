"""The policy as a function, and the row. Real inputs in a real jail are
bh-02/app/tests/test_python_repl.py's: they need a kernel, which is another plugin."""

import asyncio
import contextlib
import os
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brig_cordis_plugin import (
    MARK,
    SYSTEM_READABLE,
    BrigConfig,
    BrigJail,
    Tripwire,
    allowlisted,
    decoded,
    git_author,
    graded,
    held,
    holding,
    identity,
    jail,
    lifted,
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
    tripwired,
    uncovered,
    wires,
)
from cordis.testing import drive


@dataclass(frozen=True)
class Layers:
    paths: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    memory: str = ""


def test_the_project_s_auto_memory_directory_is_a_root_an_input_may_write() -> None:
    """Outside the project, so the model can keep notes across sessions that are never
    committed; no self-modification deny is made there, since only the memory row reads it."""
    spec = spec_for(
        root="/w/app",
        endpoint="/tmp/k/k.sock",
        scratch="/tmp/j/tmp",
        home="/Users/me",
        config=BrigConfig(),
        layers=(),
        host=(),
        memory="/Users/me/.local/state/bh-02/projects/-w-app/memory",
    )
    assert spec.fs.write_allows == (
        "/Users/me/.local/state/bh-02/projects/-w-app/memory",
        "/tmp/j/tmp",
        "/w/app",
    )
    assert not any(d.startswith("/Users/me/.local/state") for d in spec.fs.write_denies)
    assert spec_for(
        root="/w/app",
        endpoint="/tmp/k/k.sock",
        scratch="/tmp/j/tmp",
        home="/h",
        config=BrigConfig(),
        layers=(),
        host=(),
    ).fs.write_allows == ("/tmp/j/tmp", "/w/app")


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


def _denied(spec: Any, path: str) -> bool:
    """Whether `spec` denies writing `path`: it is a write deny, or under one."""
    return any(path == d or path.startswith(d + "/") for d in spec.fs.write_denies)


def test_bh_02_run_from_the_home_directory_may_not_write_its_configuration() -> None:
    """Run from the home directory, the home is a root an input may write, and bh-02's config
    directory is under it: the person's startup file, models file and context file, which a later
    session reads on the host and trusts (a startup file replaced with a link to a file the jail
    hides would be read there and handed to the model). So the directory is denied, this run's
    (`$XDG_CONFIG_HOME/bh-02`) and the default one alike; one outside every writable root needs
    no deny, and one the project is in (bh-02 run in its own config) is not denied, or the
    project would be read-only."""
    trusted = ("/home/me/xdg/bh-02", "/home/me/.config/bh-02", "/elsewhere/bh-02")

    def home_rooted(root: str, write: Sequence[str] = (".",)) -> Any:
        return spec_for(
            root=root,
            endpoint="/tmp/k/k.sock",
            scratch="/tmp/j/tmp",
            home="/home/me",
            config=BrigConfig(write=write),
            layers=(),
            host=(),
            trusted=trusted,
        )

    spec = home_rooted("/home/me")
    for name in ("kernel.py", "models.toml", "context.toml"):
        assert _denied(spec, f"/home/me/.config/bh-02/{name}"), name
        assert _denied(spec, f"/home/me/xdg/bh-02/{name}"), name  # $XDG_CONFIG_HOME/bh-02
    assert _denied(spec, "/home/me/.config/bh-02")  # the directory itself: no link swapped in
    assert not _denied(spec, "/home/me/.config/gh/hosts.yml") and not _denied(spec, "/home/me/notes.md")
    assert "/elsewhere/bh-02" not in spec.fs.write_denies  # outside every writable root
    project = home_rooted("/home/me/src/app")  # the usual case: the home is not writable at all
    assert not set(trusted) & set(project.fs.write_denies)
    extra = home_rooted("/home/me/src/app", write=(".", "/home/me"))  # a root `write` adds
    assert _denied(extra, "/home/me/.config/bh-02/kernel.py")
    inside = home_rooted("/home/me/.config/bh-02")  # bh-02 run in its own config directory
    assert not _denied(inside, "/home/me/.config/bh-02/notes.md")


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
    thing that stops an input creating it."""
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
    assert "/w" not in readable  # not the workspace root, whose local.env an input must not read
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
    holds = held(spec, ())  # both there, so both masked
    assert holds == ("/w/app/local.env", "/w/app/pkg/local.env")  # not ~/.ssh, not /src/bh
    notice = notice_for("linux", holds)
    assert "/w/app/local.env, /w/app/pkg/local.env" in notice and "renaming a new file over it" in notice
    assert "bh-02 ends the jail at once" in notice and "`/release`" in notice
    assert notice_for("darwin", holds) == "" and notice_for("linux", ()) == ""
    report = {"fs_read": "enforced", "fs_write": "enforced"}
    assert graded(report, holds) == {"fs_read": "best_effort", "fs_write": "enforced"}
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
    stopped = released_for(["/w/local.env"], [], others=True)  # the extensions' worker ran too
    assert stopped.startswith("Nothing holds") and "extensions' worker" in stopped
    assert "next input" in released_for([], [], others=True)


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


async def _gone(group: int, within: float = 2.0) -> bool:
    """Whether process group `group` has no process left within `within` seconds."""
    for _ in range(int(within / 0.02)):
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return True
        await asyncio.sleep(0.02)
    return False


def _recorded_group(tmp_path: Path) -> int:
    """The process group of the one running jail recorded under `tmp_path`'s state directory."""
    (record,) = (tmp_path / "state" / "bh-02" / "jails").iterdir()
    group = recorded_group(record.read_text())
    assert group is not None
    return group


async def test_a_linux_jail_ends_when_the_host_replaces_or_removes_a_secret_it_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The jail holds a secret under the project with a mount on its path (a `/dev/null` over the
    file, an empty directory where there is none). Replacing the file on the host the way an
    editor saves (a new file renamed over it), or removing the empty directory, detaches that
    mount inside the jail (measured before the tripwire: the workload then read the new file and
    created the absent one), so the jail ends itself at once and says why. A new jail holds both
    again. `fs_read` stays best-effort: a file created on the host at an absent secret that is
    not held is still readable."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    secret, absent, seen = project / "local.env", project / "pkg" / "local.env", project / "seen"
    secret.write_text("OLD=1\n")  # a stand-in: never the real file
    one = BrigJail(BrigConfig(), Layers(credentials=(str(absent),), secrets=(str(absent),)))

    async def jailed() -> Any:
        sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
        endpoint = str(sock_dir / "k.sock")
        argv = [
            sys.executable,
            "-I",
            "-c",
            _LISTEN_THEN_READ_AND_PLANT,
            endpoint,
            *map(str, (secret, absent, seen)),
        ]
        return await one.start(argv, cwd=str(project), endpoint=endpoint)

    started = await jailed()
    try:
        assert started.report()["fs_read"] == "best_effort"
        assert f"{secret}, {absent}" in started.notice()
        await asyncio.sleep(0.5)
        assert not seen.exists() and absent.is_dir() and started.ended() == ""  # held
        group = _recorded_group(tmp_path)
        (project / "saved.tmp").write_text("NEW=1\n")
        (project / "saved.tmp").replace(secret)  # an editor's save
        assert await _gone(group)  # the jail ended itself
        assert str(secret) in started.ended() and "the next one holds it again" in started.ended()
    finally:
        await started.stop()
    started = await jailed()
    try:
        group = _recorded_group(tmp_path)
        absent.rmdir()  # a placeholder removed by hand
        assert await _gone(group)
        assert str(absent) in started.ended()
    finally:
        await started.stop()
    started = await jailed()
    try:
        await asyncio.sleep(0.5)
        assert not seen.exists() and absent.is_dir()  # a new jail holds both again
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


async def test_a_linux_jail_ends_when_the_host_renames_over_a_write_deny_and_a_new_one_holds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The jail holds `.git/config` read-only with a bind mount on its path. A host `git config`
    saves the file by renaming a new one over it, which detaches that mount inside the jail
    (measured before the tripwire: the workload then wrote the file), so the jail ends itself at
    once and says why. A new jail (the next input's) holds it again."""
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
        assert "planted" not in config.read_text() and started.ended() == ""  # held
        group = _recorded_group(tmp_path)
        git = await asyncio.create_subprocess_exec("git", "-C", str(project), "config", "user.name", "Pat")
        assert await git.wait() == 0
        assert await _gone(group)  # the jail ended itself
        assert str(config) in started.ended()
    finally:
        await started.stop()
    started = await jailed()
    try:
        await asyncio.sleep(0.5)
        assert "planted" not in config.read_text() and "Pat" in config.read_text()  # held again
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


class _Plain:
    """What brig's launch returns, for a jail whose program runs as a plain process: there is no
    bubblewrap, so nothing is mounted, and what is tested is the jail's own work around it (its
    placeholders, record, lock, tripwire, facts and release). The program is in a session of its
    own, as brig's is, so its process group is what the jail and its tripwire end."""

    def __init__(self, jail: Any, argv: Sequence[str], cwd: str) -> None:
        self._endpoint = jail.spec.channels[0].endpoint
        self._process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, start_new_session=True)
        self.pgid = self._process.pid
        # reaped as it ends, however it ends (the tripwire kills its group), so a group that
        # ended is gone and not a zombie that `os.killpg(group, 0)` still finds
        threading.Thread(target=self._process.wait, daemon=True).start()

    def wait_ready(self, channel: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and self._process.poll() is None:
            with contextlib.suppress(OSError), socket.socket(socket.AF_UNIX) as probe:
                probe.connect(self._endpoint)  # connect, then leave without a word (a probe)
                return
            time.sleep(0.02)
        raise TimeoutError(f"{channel} never listened")

    def interrupt(self) -> bool:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(self.pgid, signal.SIGINT)
            return True
        return False

    def kill(self) -> Any:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(self.pgid, signal.SIGKILL)
        self._process.wait()
        return SimpleNamespace(items=())  # every item ended


@pytest.fixture
def _plain_launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A Linux `brig:jail` whose program is launched plainly (`_Plain`): no bubblewrap needed,
    nor allowed to fail as it does where it can't make namespaces. Linux only: the tripwire is
    inotify's."""
    if sys.platform != "linux":
        pytest.skip("the jail's tripwire is inotify's: Linux only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def launch(self: object, jail: Any, *, argv: Sequence[str], cwd: str, **rest: object) -> _Plain:
        return _Plain(jail, argv, cwd)

    monkeypatch.setattr("brig.run.SubprocessLauncher.launch", launch)
    # the jail refuses to start without bubblewrap installed; the package's `jail` is the row
    monkeypatch.setattr(sys.modules["brig_cordis_plugin.jail"], "DEFAULT_BWRAP_PATH", sys.executable)


def _endpoint() -> str:
    """A socket path short enough for a Unix socket, in a directory of its own."""
    return str(Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"), "k.sock"))


# Listens; once the jail has seen it listen, creates the file argv[2] (as an input may), says so
# in argv[3], and waits.
_LISTEN_THEN_CREATE = """
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
open(sys.argv[2], "w").write("MINE=1\\n")
open(sys.argv[3], "w").write("done")
time.sleep(60)
"""


# Listens, and waits.
_LISTEN = """
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
time.sleep(60)
"""


@pytest.mark.usefixtures("_plain_launch")
async def test_each_start_keeps_what_it_is_whatever_the_jail_starts_after_it(tmp_path: Path) -> None:
    """The `jail` row starts two programs, the kernel's worker and the extensions' worker, each
    from a command of its own. What a start is (the trees its program reads, which name the
    program's own directory; the roots it writes; its notice and grades) is that start's: the
    second start replaces none of the first's, so the kernel never tells the model the
    extensions' worker's trees. The jail's own grades are what was known before either."""
    project = tmp_path / "project"
    project.mkdir()
    credential = project / "local.env"  # where bh-02 looks for its credential, absent: held
    for name in ("kernel", "extensions"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "worker.py").write_text(_LISTEN)
    one = BrigJail(BrigConfig(), Layers(credentials=(str(credential),), secrets=(str(credential),)))
    before = dict(one.report())
    started = []
    try:
        for name in ("kernel", "extensions"):
            endpoint = _endpoint()
            argv = [sys.executable, "-I", str(tmp_path / name / "worker.py"), endpoint]
            started.append(await one.start(argv, cwd=str(project), endpoint=endpoint))
        kernel, extensions = started
        assert str(tmp_path / "kernel") in kernel.reads(), kernel.reads()
        assert str(tmp_path / "extensions") not in kernel.reads()  # the second start's, not the first's
        assert str(tmp_path / "extensions") in extensions.reads()
        assert kernel.writes() == extensions.writes() == (str(project.resolve()),)
        assert str(credential) in kernel.notice() and kernel.report()["fs_read"] == "best_effort"
        assert one.report() == before
    finally:
        for each in started:
            await each.stop()


@pytest.mark.usefixtures("_plain_launch")
async def test_release_stops_every_program_the_jail_started_and_frees_what_they_held(tmp_path: Path) -> None:
    """The `jail` row starts the kernel's worker and the extensions' worker, and both jails hold
    the absent `local.env` where bh-02 looks for its credential (and take the shared jail lock).
    The kernel stops its own worker for `/release`; the jail's `release` stops every program it
    started that still runs, so the placeholder is removed and the path is free, and says so.
    It stays released, so the extensions' worker waits, until the next start (the next input's
    kernel worker)."""
    project = tmp_path / "project"
    project.mkdir()
    credential = project / "local.env"
    one = BrigJail(BrigConfig(), Layers(credentials=(str(credential),), secrets=(str(credential),)))
    started = []
    for _ in ("kernel", "extensions"):
        endpoint = _endpoint()
        argv = [sys.executable, "-I", "-c", _LISTEN, endpoint]
        started.append(await one.start(argv, cwd=str(project), endpoint=endpoint))
    kernel, extensions = started
    try:
        records = tmp_path / "state" / "bh-02" / "jails"
        groups = [recorded_group(record.read_text()) for record in sorted(records.iterdir())]
        assert credential.is_dir() and len(groups) == 2 and None not in groups
        await kernel.stop()  # what the kernel's `release` does first
        assert credential.is_dir()  # the extensions' jail still holds it
        said = await one.release()
        assert said.startswith(f"Nothing holds {credential}"), said
        assert "stays held" not in said and "extensions' worker" in said
        assert not credential.exists() and list(records.iterdir()) == []
        for group in groups:
            assert group is not None and await _gone(group)
        assert one.released()
        endpoint = _endpoint()
        again = await one.start(
            [sys.executable, "-I", "-c", _LISTEN, endpoint], cwd=str(project), endpoint=endpoint
        )
        try:
            assert not one.released() and credential.is_dir()  # the next input's jail holds it again
        finally:
            await again.stop()
    finally:
        for each in started:
            await each.stop()  # again: nothing more happens


@pytest.mark.usefixtures("_plain_launch")
async def test_release_stops_a_program_whose_start_was_under_way_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start under way when `release` begins (the extensions' worker loading as the person
    types `/release`) is waited for, then stopped with the rest: nothing the release freed is
    held again by a jail that came up during it."""
    project = tmp_path / "project"
    project.mkdir()
    launched: list[_Plain] = []

    def slow(self: object, jail: Any, *, argv: Sequence[str], cwd: str, **rest: object) -> _Plain:
        time.sleep(0.3)
        launched.append(_Plain(jail, argv, cwd))
        return launched[-1]

    monkeypatch.setattr("brig.run.SubprocessLauncher.launch", slow)
    one = BrigJail(BrigConfig(), Layers())
    endpoint = _endpoint()
    argv = [sys.executable, "-I", "-c", _LISTEN, endpoint]
    starting = asyncio.ensure_future(one.start(argv, cwd=str(project), endpoint=endpoint))
    await asyncio.sleep(0.1)  # launching
    assert not launched and (project / ".envrc").is_dir()
    said = await one.release()
    started = await starting
    try:
        assert "extensions' worker" in said, said
        (plain,) = launched
        assert await _gone(plain.pgid) and one.released()
        assert list(project.iterdir()) == []  # its placeholders went with it
    finally:
        await started.stop()


@pytest.mark.usefixtures("_plain_launch")
async def test_an_input_creating_the_project_s_own_absent_local_env_leaves_the_jail_running(
    tmp_path: Path,
) -> None:
    """The project's `local.env` is absent and not where bh-02 looks for its credential: nothing
    holds it, and an input may create it. That must not trip the jail's own tripwire, which would
    end the jail mid-input and blame the host. The host removing a placeholder the jail does hold
    still ends it."""
    project = tmp_path / "project"
    project.mkdir()
    created, done = project / "local.env", project / "done"
    endpoint = _endpoint()
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_CREATE, endpoint, str(created), str(done)]
    started = await BrigJail(BrigConfig(), Layers()).start(argv, cwd=str(project), endpoint=endpoint)
    try:
        group = _recorded_group(tmp_path)
        for _ in range(250):
            if done.exists():
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.3)  # the tripwire's thread has read the creation, if it watches it
        assert created.read_text() == "MINE=1\n"
        assert started.ended() == "", started.ended()
        os.killpg(group, 0)  # still running
        (project / ".envrc").rmdir()  # a placeholder the jail holds, removed on the host
        assert await _gone(group)
        assert str(project / ".envrc") in started.ended()
    finally:
        await started.stop()


# A bh-02 that crashes once its jailed kernel is up: no `stop`, so nothing it made is removed.
# Its worker listens for a moment and exits, as an orphaned kernel with no host would be ended.
_CRASH = """
import asyncio, os, sys, tempfile
from pathlib import Path
from brig_cordis_plugin import BrigConfig, BrigJail

class Layers:
    paths, credentials, secrets, trusted, memory = (), (), (), (), ""

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


# A bh-02 killed while its kernel runs an input's background program, which keeps trying to write
# under `.claude/` (Claude Code would run hooks from its settings) and says it is alive: the real
# kernel, in the real jail. argv: the project, then "setsid" to start the program in a session
# of its own (out of the jail's process group), else "group". It says "started" and waits to be
# killed.
_KILLED_WITH_A_BACKGROUND_INPUT = """
import asyncio, sys, time
from brig_cordis_plugin import BrigConfig, BrigJail
from kernel_cordis_plugin import Kernel, KernelConfig

class Layers:
    paths, credentials, secrets, trusted, memory = (), (), (), (), ""

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
    code = (
        "import subprocess, sys\\n"
        f"subprocess.Popen([sys.executable, '-c', {LOOP!r}, 'alive'], start_new_session={setsid})\\n"
        "print('started')"
    )
    print(await kernel.run(code), flush=True)
    time.sleep(600)

asyncio.run(main())
"""


async def _killed_with_a_background_input(project: Path, how: str) -> None:
    """Run `_KILLED_WITH_A_BACKGROUND_INPUT` in `project`, see the program write, then `SIGKILL`
    the stand-in bh-02, as a crash or `kill -9` would end it."""
    killed = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _KILLED_WITH_A_BACKGROUND_INPUT,
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
    """bh-02 killed with SIGKILL while a program an input started runs in the background, in a
    session of its own: the jail ends with bh-02 (brig's tether: the kernel closes bh-02's end,
    and brig's watcher kills the jail's process group, bubblewrap's namespace with it, so a
    program that left the group goes too). Its record now names a group that is gone, so the
    next jail's sweep removes its placeholders and the record."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    await _killed_with_a_background_input(project, "setsid")
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
    """darwin: bh-02 killed with SIGKILL takes a program an input left running with it (brig's
    tether kills the jail's process group). seatbelt has no namespace, so a program an input
    started in a session of its own is out of that group and lives on, as it does past a normal
    stop (brig's teardown is group-shaped too): measured, so the README's gap stays honest."""
    if sys.platform != "darwin":
        pytest.skip("seatbelt is darwin's")
    grouped, setsid = tmp_path / "grouped", tmp_path / "setsid"
    grouped.mkdir()
    setsid.mkdir()
    await _killed_with_a_background_input(grouped, "group")
    await _killed_with_a_background_input(setsid, "setsid")
    programs = [int((where / "alive.pid").read_text()) for where in (grouped, setsid)]
    await asyncio.sleep(1.0)
    try:
        assert not await _still_writing(grouped / "alive")
        with pytest.raises(ProcessLookupError):
            os.kill(programs[0], 0)
        assert await _still_writing(setsid / "alive")  # the gap
    finally:
        for program in programs:  # neither outlives the test, whatever it found
            with contextlib.suppress(ProcessLookupError):
                os.kill(program, signal.SIGKILL)


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
    paths, credentials, secrets, trusted, memory = (), (), (), (), ""

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


# Listens; once the jail has seen it listen, writes "note" to argv[2] and to argv[3] (as an input
# keeping auto memory would, and one reaching for another project's), says so in argv[4], waits.
_LISTEN_THEN_NOTE = """
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
for path in sys.argv[2:4]:
    try:
        open(path, "w").write("note")
    except OSError:
        pass
open(sys.argv[4], "w").write("done")
time.sleep(60)
"""


async def test_a_linux_jail_lets_an_input_write_its_project_s_auto_memory_and_nothing_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The project's auto memory directory (`layers.memory`) is a root an input may write, in the
    real jail: the model keeps its notes there with plain Python. Another project's, beside it,
    is not even there to read; and the model is told it may write the directory (`writes()`)."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "records"))
    project, projects = tmp_path / "project", tmp_path / "state" / "bh-02" / "projects"
    memory, beside = projects / "-project" / "memory", projects / "-other" / "memory"
    for directory in (project, memory, beside):
        directory.mkdir(parents=True)
    one = BrigJail(BrigConfig(), Layers(memory=str(memory)))
    endpoint = _endpoint()
    notes = (str(memory / "MEMORY.md"), str(beside / "MEMORY.md"))
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_NOTE, endpoint, *notes, str(project / "done")]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
    try:
        for _ in range(200):
            if (project / "done").exists():
                break
            await asyncio.sleep(0.05)
        assert (project / "done").exists()
        assert (memory / "MEMORY.md").read_text() == "note"
        assert not (beside / "MEMORY.md").exists()
        assert str(memory.resolve()) in started.writes() and str(memory.resolve()) in started.reads()
    finally:
        await started.stop()


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
    `scripts/linux-jail-check`'s): the grades an input is confined by, and the project's own
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


def test_the_tripwire_watches_each_held_path_s_directory_by_name() -> None:
    held = ("/w/.git/config", "/w/.git/hooks", "/w/mine.toml", "/w/local.env", "/w/mine.toml")
    assert wires(held) == {"/w/.git": ("config", "hooks"), "/w": ("mine.toml", "local.env")}


def test_what_lifts_a_hold_is_the_host_replacing_moving_or_removing_a_held_name() -> None:
    """Renamed over (`MOVED_TO`), renamed away (`MOVED_FROM`), removed, created; the directory
    itself gone; the queue overflowed. Not a write to a held file, not git's lock beside one,
    nor anything to a name not held."""
    watched = {"/w/.git": ("config", "hooks"), "/w": ("mine.toml",)}
    moved_to, moved_from, create, delete, delete_self, overflow = 0x80, 0x40, 0x100, 0x200, 0x400, 0x4000
    assert lifted([("/w/.git", moved_to, "config")], watched) == ("/w/.git/config",)
    assert lifted([("/w", moved_from, "mine.toml")], watched) == ("/w/mine.toml",)
    assert lifted([("/w/.git", delete | 0x40000000, "hooks")], watched) == ("/w/.git/hooks",)
    assert lifted([("/w/.git", create, "config.lock")], watched) == ()  # git's lock: see `lifted`
    assert lifted([("/w/.git", delete_self, "")], watched) == ("/w/.git/config", "/w/.git/hooks")
    assert len(lifted([("", overflow, "")], watched)) == 3
    assert lifted([("/w", create, "notes.txt"), ("/w/.git", create, "index.lock")], watched) == ()
    assert lifted([("/w", moved_to, "mine.toml~"), ("/w/.git", 0x2, "config")], watched) == ()


def test_inotify_records_are_read_as_descriptor_mask_and_name() -> None:
    record = struct.pack("iIII", 3, 0x80, 7, 16) + b"config".ljust(16, b"\0")
    bare = struct.pack("iIII", 1, 0x400, 0, 0)
    assert decoded(record + bare) == [(3, 0x80, "config"), (1, 0x400, "")]


def test_a_linux_jail_watches_an_absent_secret_only_where_no_input_may_create_it() -> None:
    """The project's own `local.env`, absent and not where bh-02 looks for its credential: the
    allowlist drops its write deny and nothing is mounted there, so an input may create it, and
    that must not trip the jail's own tripwire. An absent one an input can't create (held by an
    empty directory where bh-02 looks for its credential, or inside a directory bound read-only)
    is still watched: only the host could create it, and the jail could then read it. One that
    is there is masked, and watched."""
    policy = spec_for(
        root="/w/app",
        endpoint="/tmp/k/k.sock",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(),
        layers=(),
        host=("/w/app/src",),  # a directory the host imports code from: bound read-only
        secrets=("/w/app/creds/local.env", "/w/app/src/local.env"),
    )
    linux = allowlisted(policy, ("/usr",), hold={"/w/app/creds/local.env"})
    absent = {"/w/app/local.env", "/w/app/creds/local.env", "/w/app/src/local.env"}
    assert "/w/app/local.env" not in linux.fs.write_denies  # an input may create it
    watched = tripwired(linux, absent)
    assert "/w/app/local.env" not in watched and "/w/app/local.env" not in held(linux, absent)
    assert {"/w/app/creds/local.env", "/w/app/src/local.env"} <= set(watched)
    assert "/w/app/local.env" in tripwired(linux, ()) and "/w/app/local.env" in held(linux, ())  # masked
    assert "/w/app/local.env" not in notice_for("linux", held(linux, absent))


def test_a_linux_jail_trips_on_every_write_deny_under_a_writable_root_and_every_held_secret() -> None:
    policy = spec_for(
        root="/w/app",
        endpoint="/tmp/k/k.sock",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(),
        layers=("/w/app/mine.toml", "/elsewhere/chat.toml"),
        host=(),
    )
    paths = tripwired(policy, ())
    assert {"/w/app/mine.toml", "/w/app/.git/config", "/w/app/local.env"} <= set(paths)
    assert "/elsewhere/chat.toml" not in paths  # outside every writable root: nothing is mounted


async def test_on_linux_the_tripwire_ends_a_process_group_when_a_held_file_is_renamed_over(
    tmp_path: Path,
) -> None:
    """The shell, without bubblewrap: a held file renamed over ends the group and says why;
    a file beside it changing does nothing."""
    if sys.platform != "linux":
        pytest.skip("inotify is Linux's")
    held = tmp_path / "config"
    held.write_text("a")
    victim = subprocess.Popen(["sleep", "30"], start_new_session=True)
    wire = Tripwire([str(held)])
    wire.arm(victim.pid)
    try:
        (tmp_path / "beside").write_text("b")  # not held: nothing happens
        await asyncio.sleep(0.1)
        assert victim.poll() is None and wire.tripped == ""
        (tmp_path / "config.new").write_text("c")
        (tmp_path / "config.new").replace(held)
        assert await asyncio.to_thread(victim.wait, 2) == -signal.SIGKILL
        assert str(held) in wire.tripped
    finally:
        wire.stop()
        victim.kill()
