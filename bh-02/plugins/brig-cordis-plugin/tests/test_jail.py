"""The policy as a function, and the row. Real cells in a real jail are
bh-02/app/tests/test_python_cells.py's: they need a kernel, which is another plugin."""

import asyncio
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from brig_cordis_plugin import (
    SYSTEM_READABLE,
    BrigConfig,
    BrigJail,
    allowlisted,
    graded,
    held,
    jail,
    made_by_the_jail,
    mountable,
    notice_for,
    readable_roots,
    self_modify_denied,
    spec_for,
    stack_for,
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
    assert "`/restart kernel`" in notice
    assert notice_for("darwin", held(spec)) == "" and notice_for("linux", ()) == ""
    report = {"fs_read": "enforced", "fs_write": "enforced"}
    assert graded(report, held(spec)) == {"fs_read": "best_effort", "fs_write": "enforced"}
    assert graded(report, ()) == report


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
