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
    jail,
    made_by_the_jail,
    mountable,
    readable_roots,
    self_modify_denied,
    spec_for,
    stack_for,
)
from cordis.testing import drive


@dataclass(frozen=True)
class Layers:
    paths: tuple[str, ...] = ()
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
    (credentials, `hide`, `secrets`) is a carve-out inside it; writes and env are untouched."""
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
    linux = allowlisted(policy, ("/usr", "/etc", "/opt/py"))
    assert linux.fs.read_allows == ("/etc", "/opt/py", "/usr")
    assert linux.fs.read_denies == policy.fs.read_denies
    assert {"/w/app/local.env", "/src/bh/local.env", "/home/me/.ssh"} <= set(linux.fs.read_denies)
    assert (linux.fs.write_allows, linux.fs.write_denies) == (policy.fs.write_allows, policy.fs.write_denies)
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
    `local.env` masked on the command line, because it exists; absent, it is named instead."""
    project = tmp_path / "project"
    project.mkdir()
    secret = project / "local.env"
    jail = BrigJail(BrigConfig(), Layers(), platform="linux")
    report = jail.report()
    assert report["fs_write"] == report["network"] == report["env"] == "enforced"

    compiled, graded = jail.compile(str(tmp_path / "j"), str(tmp_path / "k" / "k.sock"), str(project), ())
    detail = next(g.detail for axis, g in compiled.report.axes.items() if axis.value == "fs_read")
    assert graded["fs_read"] == "best_effort" and str(secret.resolve()) in detail

    secret.write_text("NOT_A_REAL_CREDENTIAL=placeholder\n")  # a stand-in: never the real file
    compiled, graded = jail.compile(str(tmp_path / "j"), str(tmp_path / "k" / "k.sock"), str(project), ())
    argv = compiled.wrap(("w",))
    at = argv.index(str(secret.resolve()))
    assert argv[at - 2 : at + 1] == ("--ro-bind", "/dev/null", str(secret.resolve()))
    assert graded["fs_read"] == "enforced"
