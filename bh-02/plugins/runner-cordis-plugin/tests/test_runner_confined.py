"""The policy as a function, and the row. Real inputs in a real jail are
bh-02/app/tests/test_python_repl.py's: they need a Python process, which is another plugin's."""

import asyncio
import errno
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import uuid
from collections import namedtuple
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cordis.testing import drive
from runner_cordis_plugin import (
    PLANNED,
    SYSTEM_READABLE,
    BrigConfig,
    BrigJail,
    Policy,
    ReadModel,
    Runner,
    Tripwire,
    allowlisted,
    confined,
    decoded,
    git_author,
    held,
    is_confined,
    lifted,
    link_directories,
    links_on_the_way,
    mountable,
    notice_for,
    planned,
    readable_roots,
    released_for,
    report_of,
    self_modify_denied,
    spec_for,
    to_brig,
    told_reads,
    tripwired,
    unended_for,
    wires,
)
from runner_cordis_plugin import jail as jail_module


@dataclass(frozen=True)
class Host:
    paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    auto_memory: str = ""
    key_envs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    models_file: str = ""


def test_the_project_s_auto_memory_directory_is_a_root_an_input_may_write() -> None:
    """Outside the project, so the model can keep memories across sessions that are never
    committed; no self-modification deny is made there, since only the memory row reads it."""
    spec = spec_for(
        root="/w/app",
        scratch="/tmp/j/tmp",
        home="/Users/me",
        config=BrigConfig(),
        layers=(),
        host=(),
        memory="/Users/me/.local/state/bh-02/projects/-w-app/memory",
    )
    assert spec.writable == (
        "/Users/me/.local/state/bh-02/projects/-w-app/memory",
        "/tmp/j/tmp",
        "/w/app",
    )
    assert not any(d.startswith("/Users/me/.local/state") for d in spec.write_denies)
    assert spec_for(
        root="/w/app",
        scratch="/tmp/j/tmp",
        home="/h",
        config=BrigConfig(),
        layers=(),
        host=(),
    ).writable == ("/tmp/j/tmp", "/w/app")


def test_the_spec_denies_what_would_reach_outside_the_jail_later() -> None:
    spec = spec_for(
        root="/w/app",
        scratch="/tmp/j/tmp",
        home="/Users/me",
        config=BrigConfig(hide=("private.txt",)),
        layers=("/w/app/mine.toml", "/elsewhere/chat.toml"),
        host=("/w/app/src", "/usr/lib/python3.15", "/w/app/.venv", "/w/app"),
        secrets=("/src/bh/private.txt",),
    )
    assert spec.writable == ("/tmp/j/tmp", "/w/app")
    denies = set(spec.write_denies)
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
    assert "/Users/me/.ssh" in spec.masks
    assert "/w/app/private.txt" in spec.masks  # a file `hide` names, beside the project
    assert "/src/bh/private.txt" in spec.masks  # a secret, wherever the project is
    assert "/w/app/private.txt" in denies  # one it may not read it may not overwrite either
    assert "/src/bh/private.txt" not in denies  # outside every writable root: nothing to deny
    assert dict(spec.env_set) == {"TMPDIR": "/tmp/j/tmp"} and "PATH" in spec.env_allow


#: The made-up home, resolved the way `spec_for` resolves a root (`Path.resolve`): on macOS
#: `/home/me` is `/System/Volumes/Data/home/me`, and `spec_for` compares the `trusted` and `code`
#: paths it is handed, which the program supplies already resolved, with its resolved roots.
_HOME = str(Path("/home/me").resolve())


def _denied(spec: Policy, path: str) -> bool:
    """Whether `spec` denies writing `path`: it is a write deny, or under one."""
    return any(path == d or path.startswith(d + "/") for d in spec.write_denies)


def test_bh_02_run_from_the_home_directory_may_not_write_its_configuration() -> None:
    """Run from the home directory, the home is a root an input may write, and bh-02's config
    directory is under it: the person's startup file, models file and context file, which a later
    session reads on the host and trusts (a startup file replaced with a link to a file the jail
    hides would be read there and handed to the model). So the directory is denied, this run's
    (`$XDG_CONFIG_HOME/bh-02`) and the default one alike; one outside every writable root needs
    no deny, and one the project is in (bh-02 run in its own config) is not denied, or the
    project would be read-only."""
    trusted = (f"{_HOME}/xdg/bh-02", f"{_HOME}/.config/bh-02", "/elsewhere/bh-02")

    def home_rooted(root: str, write: Sequence[str] = (".",)) -> Any:
        return spec_for(
            root=root,
            scratch="/tmp/j/tmp",
            home=_HOME,
            config=BrigConfig(write=write),
            layers=(),
            host=(),
            trusted=trusted,
        )

    spec = home_rooted(_HOME)
    for name in ("startup.py", "models.toml", "context.toml"):
        assert _denied(spec, f"{_HOME}/.config/bh-02/{name}"), name
        assert _denied(spec, f"{_HOME}/xdg/bh-02/{name}"), name  # $XDG_CONFIG_HOME/bh-02
    assert _denied(spec, f"{_HOME}/.config/bh-02")  # the directory itself: no link swapped in
    assert not _denied(spec, f"{_HOME}/.config/gh/hosts.yml") and not _denied(spec, f"{_HOME}/notes.md")
    assert "/elsewhere/bh-02" not in spec.write_denies  # outside every writable root
    project = home_rooted(f"{_HOME}/src/app")  # the usual case: the home is not writable at all
    assert not set(trusted) & set(project.write_denies)
    extra = home_rooted(f"{_HOME}/src/app", write=(".", _HOME))  # a root `write` adds
    assert _denied(extra, f"{_HOME}/.config/bh-02/startup.py")
    inside = home_rooted(f"{_HOME}/.config/bh-02")  # bh-02 run in its own config directory
    assert not _denied(inside, f"{_HOME}/.config/bh-02/notes.md")


_CHECKOUT = f"{_HOME}/src/bh-02"  # bh-02's own workspace, installed editable
_CODE = (  # the directory of every package bh-02 runs code from (`host.code`)
    f"{_CHECKOUT}/bh-02/plugins/memory-cordis-plugin/src/memory_cordis_plugin",
    f"{_CHECKOUT}/bh-02/plugins/python-cordis-plugin/src/python_cordis_plugin",
    f"{_CHECKOUT}/libs/cordis/src/cordis",
    "/opt/py/lib/python3.15/site-packages/brig",  # one installed into the interpreter
)


def test_bh_02_s_own_code_under_a_writable_root_is_denied_as_its_layer_files_are() -> None:
    """bh-02 working on its own checkout (an editable install), or run from the home directory
    with the checkout under it: the directory of every package bh-02 runs code from
    (`host.code`) is under a root an input may write. bh-02 imports its modules from there in
    its own process (a plugin a layer names later, say), so an input that wrote one would choose
    code bh-02 runs. Each is denied as a layer
    file is, whatever the host's `sys.path` holds (`host` names nothing here). Not one the project
    is (bh-02 run in a package's own directory), or the project would be read-only; one outside
    every writable root needs no deny."""
    shipped = f"{_CODE[0]}/context.toml"

    def rooted(root: str) -> Any:
        return spec_for(
            root=root,
            scratch="/tmp/j/tmp",
            home=_HOME,
            config=BrigConfig(),
            layers=(),
            host=(),
            code=_CODE,
        )

    for root in (_CHECKOUT, _HOME):  # checkout-rooted, home-rooted
        spec = rooted(root)
        assert _denied(spec, shipped), root
        assert _denied(spec, f"{_CODE[0]}/planted.py"), root  # a module bh-02 could import
        assert all(_denied(spec, code) for code in _CODE[:3]), root  # every plugin's, and cordis's
        assert _CODE[3] not in spec.write_denies  # outside every writable root
        assert not _denied(spec, f"{_CHECKOUT}/README.md")  # the rest of the checkout is the project's
    elsewhere = rooted(f"{_HOME}/work/app")  # the usual case: none is under the project
    assert not set(_CODE) & set(elsewhere.write_denies)
    inside = rooted(_CODE[0])  # bh-02 run in a package's own directory
    assert not _denied(inside, f"{_CODE[0]}/notes.md")


def test_the_interpreter_bh_02_runs_on_is_denied_where_an_input_could_write_it() -> None:
    """A project that holds the uv-managed Python (the home directory) is a root an input may
    write, and the interpreter bh-02 runs on lies under it. In a venv layout `host` names the base's
    standard library (on `sys.path`) and the venv's prefix, not the base's own binary: an input
    that wrote that file would be run by the next bh-02 start on the host, outside any jail. So the
    interpreter's files are denied, with or without a venv, where they are under a writable root."""
    base = f"{_HOME}/.local/share/uv/python/cpython-3.15.0-linux"
    interpreter, venv = f"{base}/bin/python3.15", f"{_HOME}/src/app/.venv"
    stdlib = (f"{base}/lib/python3.15", f"{base}/lib/python3.15/lib-dynload")
    in_a_venv = (*stdlib, f"{venv}/lib/python3.15/site-packages", venv)  # `sys.path`, `sys.prefix`
    without_one = (base, *stdlib)  # `sys.prefix` is the base: the whole tree is the host's

    def rooted(root: str, host: Sequence[str], interpreters: Sequence[str] = (interpreter,)) -> Any:
        return spec_for(
            root=root,
            scratch="/tmp/j/tmp",
            home=_HOME,
            config=BrigConfig(),
            layers=(),
            host=host,
            interpreters=interpreters,
        )

    for host in (in_a_venv, without_one):
        spec = rooted(_HOME, host)
        assert _denied(spec, interpreter), host
        assert _denied(spec, f"{base}/lib/python3.15/os.py")  # the standard library was, either way
        assert not _denied(spec, f"{_HOME}/notes.md")
    sibling = f"{base}/bin/python3.15x"
    assert not _denied(rooted(_HOME, in_a_venv), sibling)  # a name beside it is not the file
    assert _denied(rooted(_HOME, without_one), sibling)  # (no venv: the whole base is the host's)
    elsewhere = rooted(f"{_HOME}/work/app", in_a_venv)  # the usual case: the Python is not under the project
    assert interpreter not in elsewhere.write_denies
    system = rooted(_HOME, in_a_venv, ("/usr/bin/python3.13",))  # a system Python, outside every root
    assert "/usr/bin/python3.13" not in system.write_denies
    in_its_directory = rooted(f"{base}/bin", in_a_venv)  # the project is its directory: only the file
    assert _denied(in_its_directory, interpreter) and not _denied(in_its_directory, f"{base}/bin/notes.md")
    itself = rooted(interpreter, in_a_venv)  # a root is never denied, or the project would be read-only
    assert interpreter not in itself.write_denies


def _a_python_in(project: Path) -> tuple[Path, Path, Path]:
    """A uv-managed Python under `project` and a venv beside it, as a project opened at the home
    directory holds them: the base's interpreter file (an executable, `true`'s) with its `python3`
    link and standard library, and the venv's `python` links, which lead to the file. Returns the
    file, the link, the venv."""
    base, venv = project / ".local" / "py", project / "venv"
    (base / "lib" / "python3.15").mkdir(parents=True)
    (base / "bin").mkdir()
    file = base / "bin" / "python3.15"
    shutil.copy2(shutil.which("true") or "/bin/true", file)
    link = base / "bin" / "python3"
    link.symlink_to("python3.15")
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").symlink_to(file)
    (venv / "bin" / "python3").symlink_to("python")
    return file, link, venv


def test_the_directory_of_each_link_on_the_way_to_the_interpreter_is_denied_where_it_is_writable() -> None:
    """A mount on the interpreter's file holds the file, not the links that lead to it: an input
    that renamed one could plant a Python of its own at its name. So the directory that holds each
    link on the way is denied, when it is under a root an input may write. A project opened at the
    home directory holds uv's Python: the venv's `python` goes through uv's `cpython-3.15-<platform>`
    link (to the versioned directory), and that link lies in `~/.local/share/uv/python`."""
    uv = f"{_HOME}/.local/share/uv/python"
    venv = f"{_HOME}/src/app/.venv"
    chain = (  # as `_links_on_the_way` finds them: the entry of each link, in the order met
        f"{venv}/bin/python3",
        f"{venv}/bin/python",
        f"{uv}/cpython-3.15-linux",
        f"{uv}/cpython-3.15.0-linux/bin/python3",
    )
    in_the_home = (f"{venv}/bin", uv, f"{uv}/cpython-3.15.0-linux/bin")  # each directory once, as met
    assert link_directories(chain, (_HOME,)) == in_the_home
    assert link_directories(chain, ("/tmp/j/tmp", f"{_HOME}/work/app")) == ()  # outside every root: nothing
    assert link_directories((), (_HOME,)) == ()
    assert link_directories(chain, (f"{_HOME}/src/app",)) == (f"{venv}/bin",)  # only what is under a root
    assert link_directories(chain, (uv,)) == (f"{uv}/cpython-3.15.0-linux/bin",)  # the directory itself: not
    assert link_directories(chain, (f"{uv}/cpython-3.15.0-linux/bin",)) == ()  # a root is the project: left
    assert link_directories(chain, (f"{_HOME}/src/ap",)) == ()  # a sibling name is not under it
    assert link_directories(chain, (f"{uv}/cpython-3.15.0-linux/bin/x", _HOME)) == in_the_home

    def denies(root: str) -> Any:
        return spec_for(
            root=root,
            scratch="/tmp/j/tmp",
            home=_HOME,
            config=BrigConfig(),
            layers=(),
            host=(),
            links=chain,
        )

    for directory in in_the_home:
        assert _denied(denies(_HOME), f"{directory}/anything"), directory  # nothing in it is written
    assert not _denied(denies(_HOME), f"{_HOME}/notes.md")
    assert not set(in_the_home) & set(denies(f"{_HOME}/work/app").write_denies)  # the usual case
    assert not _denied(denies(uv), uv) and _denied(denies(uv), f"{uv}/cpython-3.15.0-linux/bin/python3")


def _a_uv_python_in(project: Path) -> tuple[Path, Path, tuple[Path, ...]]:
    """uv's layout under `project`, as one opened at the home directory holds it: the versioned
    directory (`cpython-3.15.0-linux`, an interpreter file, `true`'s, with its `python3` link and
    standard library), uv's link to it (`cpython-3.15-linux`, an absolute target as uv writes it)
    and a venv whose `python` goes through that link. Returns the venv, the interpreter file and the
    links on the way from the venv's `python3` to the file, in the order met."""
    python, venv = project.resolve() / "uv" / "python", project.resolve() / "venv"
    base = python / "cpython-3.15.0-linux"
    (base / "lib" / "python3.15").mkdir(parents=True)
    (base / "bin").mkdir()
    file = base / "bin" / "python3.15"
    shutil.copy2(shutil.which("true") or "/bin/true", file)
    (base / "bin" / "python3").symlink_to("python3.15")
    through = python / "cpython-3.15-linux"
    through.symlink_to(base)
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").symlink_to(through / "bin" / "python3")
    (venv / "bin" / "python3").symlink_to("python")
    return venv, file, (venv / "bin" / "python3", venv / "bin" / "python", through, base / "bin" / "python3")


def test_allow_takes_names_off_the_self_modification_list_and_only_those() -> None:
    assert "CLAUDE.md" not in self_modify_denied(("CLAUDE.md",))
    assert {".git/hooks", ".git/config", "AGENTS.md"} <= set(self_modify_denied(("CLAUDE.md",)))
    assert ".git/config" in self_modify_denied(())  # nothing allowed: the whole list
    with pytest.raises(ValueError) as raised:
        self_modify_denied(("README.md",))
    assert "'README.md'" in str(raised.value) and "use `write`" in str(raised.value)


async def test_the_row_binds_a_runner_over_a_brig_jail_over_the_layers_it_was_given() -> None:
    effects = await drive(confined(config=BrigConfig(), host=Host()))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "runner")]
    assert isinstance(effects[0].args[1], Runner)


def test_on_linux_the_policy_reads_by_allowlist_and_keeps_every_deny() -> None:
    """The same policy, one read model over: what is readable is named, and every read deny
    (the credential paths, `hide`, `secrets`) is a carve-out inside it; writes and env are
    untouched, but for a secret under the project, whose read mask refuses writes by itself."""
    policy = spec_for(
        root="/w/app",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(hide=("private.txt",)),
        layers=("/w/app/mine.toml",),
        host=(),
        secrets=("/src/bh/private.txt",),
    )
    linux = allowlisted(policy, ("/usr", "/etc", "/opt/py"))
    assert linux.readable == ("/etc", "/opt/py", "/usr")
    assert linux.masks == policy.masks
    assert {"/w/app/private.txt", "/src/bh/private.txt", "/home/me/.ssh"} <= set(linux.masks)
    assert "/w/app/private.txt" in policy.write_denies and "/w/app/private.txt" not in linux.write_denies
    kept = tuple(d for d in policy.write_denies if d != "/w/app/private.txt")
    assert (linux.writable, linux.write_denies) == (policy.writable, kept)
    assert (linux.env_allow, linux.env_set) == (policy.env_allow, policy.env_set)
    assert linux.read_model is ReadModel.ALLOWLIST and policy.read_model is ReadModel.DENYLIST


def test_a_linux_jail_reads_the_system_the_interpreter_and_what_the_command_names() -> None:
    readable = readable_roots(
        argv=["/w/.venv/bin/python", "-I", "/w/src/python_cordis_plugin/worker.py", "/tmp/k/k.sock"],
        interpreter=("/opt/py", "/w/.venv"),
        system=SYSTEM_READABLE,
    )
    assert readable[: len(SYSTEM_READABLE)] == SYSTEM_READABLE
    assert {"/opt/py", "/w/.venv", "/w/.venv/bin", "/w/src/python_cordis_plugin"} <= set(readable)
    assert "/w" not in readable  # not the workspace root, whose files an input must not read
    assert len(readable) == len(set(readable))


def test_a_linux_jail_holds_the_secrets_under_a_writable_root_and_says_so() -> None:
    """What the jail holds with a mount (a secret under the project) can be undone by the host:
    brig's grade says best-effort, and the person is told which paths at the start of a session.
    darwin's seatbelt matches paths, so there is nothing to say there."""
    spec = spec_for(
        root="/w/app",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(hide=("private.txt",)),
        layers=(),
        host=(),
        secrets=("/w/app/pkg/private.txt", "/src/bh/private.txt"),
    )
    holds = held(spec)  # present or not, each is mounted over (brig makes a directory at an absent one)
    assert holds == ("/w/app/pkg/private.txt", "/w/app/private.txt")  # not ~/.ssh, not /src/bh
    notice = notice_for("linux", holds)
    assert "/w/app/pkg/private.txt, /w/app/private.txt" in notice and "renaming a new file over it" in notice
    assert "bh-02 ends the jail at once" in notice and "credential" not in notice
    assert notice_for("darwin", holds) == "" and notice_for("linux", ()) == ""


def test_release_says_only_that_a_program_still_runs() -> None:
    assert released_for() == "" and released_for(running=False) == ""
    running = released_for(running=True)  # an owner did not stop its own program
    assert running.startswith("A program this runner started still runs") and "/restart" in running


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
        if not _alive(group):
            return True
        await asyncio.sleep(0.02)
    return False


_LISTEN_WITH_A_SESSION_OF_ITS_OWN = """
import socket, subprocess, sys, time
subprocess.Popen(["/bin/sleep", sys.argv[2]], start_new_session=True)
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
time.sleep(600)
"""


# A hostile program: it ignores SIGTERM, starts a second program in a session of its own that
# ignores it too and stamps argv[3] every 10 ms, and itself tries to create argv[2] every 10 ms.
_HOSTILE_IGNORING_SIGTERM = """
import signal, socket, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
STAMP = (
    "import signal, sys, time\\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\\n"
    "while True:\\n"
    "    open(sys.argv[1], 'w').write(str(time.time()))\\n"
    "    time.sleep(0.01)\\n"
)
subprocess.Popen([sys.executable, "-I", "-c", STAMP, sys.argv[3]], start_new_session=True)
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
while True:
    time.sleep(0.01)
    try:
        open(sys.argv[2], "w").write("PLANTED=1")
    except OSError:
        pass
"""


# Starts a server in a session of its own, listens, and after a moment writes argv[2] and exits:
# the jail's program ends while a program of its own keeps running in the jail.
_LISTEN_LEAVE_A_SERVER_AND_END = """
import socket, subprocess, sys, time
subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(120)"], start_new_session=True)
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
time.sleep(0.8)
open(sys.argv[2], "w").write("ending")
"""


def _nothing_listens(endpoint: str) -> bool:
    with socket.socket(socket.AF_UNIX) as client:
        try:
            client.connect(endpoint)
        except OSError:
            return True
    return False


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


def test_one_walk_of_the_links_serves_the_policy_and_the_readable_trees(tmp_path: Path) -> None:
    """Every link on the way is found, in the directory that holds it; the ones the lookup goes on
    through (a link to a directory in the middle of a path) are told from the ones it ends at."""
    (tmp_path / "store" / "3.15.0" / "bin").mkdir(parents=True)
    (tmp_path / "store" / "3.15.0" / "bin" / "python3").write_text("")
    (tmp_path / "alias").symlink_to("store/3.15.0")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "python").symlink_to("../alias/bin/python3")
    found = links_on_the_way([f"{tmp_path}/bin/python"])
    assert [(link.entry, link.through) for link in found] == [
        (f"{tmp_path}/bin/python", False),
        (f"{tmp_path}/alias", True),
    ]
    assert links_on_the_way([f"{tmp_path}/alias/bin/python3", ""]) == (found[1],)


def test_the_model_is_told_the_trees_a_jail_reads_the_same_at_every_start() -> None:
    """Each tree once, and none that another holds: bh-02's own code, or the interpreter's
    environment, inside the project (bh-02 working on its own checkout) is the project's."""
    trees = (
        "/usr",
        "/tmp/bh-k-a1",
        "/w/app/src/cordis",
        "/w/app/.venv",
        "/w/app",
        "/tmp/bh-j-b2/tmp",
        "/usr",
    )
    assert told_reads(trees, ("/tmp/bh-j-b2", "/tmp/bh-k-a1")) == ("/usr", "/w/app", "$TMPDIR")


def _needs_bwrap() -> None:
    if sys.platform != "linux" or not Path("/usr/bin/bwrap").exists():
        pytest.skip("the placeholders are bubblewrap's: Linux with /usr/bin/bwrap only")


def _listening(endpoint: str) -> list[str]:
    """The command of a program that listens on `endpoint` and does nothing else."""
    return [sys.executable, "-I", "-c", _LISTEN, endpoint]


async def _report(said: Path, started: Any) -> str:
    """What the program wrote to `said`, once the name exists. The programs that report this way write a
    temporary name and rename it into place (`os.replace`), so the name exists only when the report is
    whole. The wait is 10 seconds; when it runs out, the assertion says what is there instead: the
    directory's entries, and why the jail ended the program itself, if it did."""
    deadline = time.monotonic() + 10
    while not said.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert said.exists(), (
        f"no report at {said} after 10 s: the directory holds "
        f"{sorted(p.name for p in said.parent.iterdir())}; the jail's own reason for ending the program: "
        f"{started.ended() or 'none'}"
    )
    return said.read_text()


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


# Listens; once the jail has seen it listen, writes "a memory" to argv[2] and to argv[3] (as an input
# keeping auto memory would, and one reaching for another project's), says so in argv[4], waits.
_LISTEN_THEN_REMEMBER = """
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
for path in sys.argv[2:4]:
    try:
        open(path, "w").write("a memory")
    except OSError:
        pass
open(sys.argv[4], "w").write("done")
time.sleep(60)
"""


async def test_a_linux_jail_lets_an_input_write_its_project_s_auto_memory_and_nothing_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The project's auto memory directory (`host.auto_memory`) is a root an input may write, in the
    real jail: the model keeps its memories there with plain Python. Another project's, beside it,
    is not even there to read; and the model is told it may write the directory (`writes()`)."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "records"))
    project, projects = tmp_path / "project", tmp_path / "state" / "bh-02" / "projects"
    memory, beside = projects / "-project" / "memory", projects / "-other" / "memory"
    for directory in (project, memory, beside):
        directory.mkdir(parents=True)
    one = BrigJail(BrigConfig(), Host(auto_memory=str(memory)))
    memories = (str(memory / "MEMORY.md"), str(beside / "MEMORY.md"))

    def argv(endpoint: str) -> list[str]:
        return [sys.executable, "-I", "-c", _LISTEN_THEN_REMEMBER, endpoint, *memories, str(project / "done")]

    started = await one.start(argv, cwd=str(project))
    try:
        for _ in range(200):
            if (project / "done").exists():
                break
            await asyncio.sleep(0.05)
        assert (project / "done").exists()
        assert (memory / "MEMORY.md").read_text() == "a memory"
        assert not (beside / "MEMORY.md").exists()
        assert str(memory.resolve()) in started.writes() and str(memory.resolve()) in started.reads()
    finally:
        await started.stop()


# Listens; once the jail has seen it listen, tries what an input could do to the interpreter file
# argv[2] (write it, write through its link argv[3], rename it, remove it) and writes a file beside
# them, argv[4]; says what each came to in argv[5] (renamed into place, so whole), waits.
_LISTEN_THEN_REACH_FOR_THE_PYTHON = """
import os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
file, link, beside, said = sys.argv[2:6]
tries = {
    "write": lambda: open(file, "w").write("planted"),
    "write through the link": lambda: open(link, "w").write("planted"),
    "rename": lambda: os.rename(file, file + ".moved"),
    "remove": lambda: os.unlink(file),
    "write beside": lambda: open(beside, "w").write("fine"),
}
came_to = []
for name, attempt in tries.items():
    try:
        attempt()
        came_to.append(name + ": done")
    except OSError as error:
        came_to.append(name + ": " + os.strerror(error.errno))
with open(said + ".tmp", "w") as report:
    report.write("\\n".join(came_to))
os.replace(said + ".tmp", said)
time.sleep(60)
"""


async def test_a_linux_jail_refuses_an_input_that_writes_the_interpreter_bh_02_runs_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In a real jail, with the interpreter bh-02 runs on planted under the project (an input may
    write the project): a write to the file, or through its link, a rename and a removal are all
    refused, and a file beside it is written as any in the project is."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "records"))
    project = tmp_path / "project"
    file, link, _ = _a_python_in(project)
    before = file.read_bytes()
    monkeypatch.setattr("runner_cordis_plugin.jail.host_executable", str(link))
    one = BrigJail(BrigConfig(), Host())
    said, beside = project / "said", project / "beside"

    def argv(endpoint: str) -> list[str]:
        return [
            sys.executable,
            "-I",
            "-c",
            _LISTEN_THEN_REACH_FOR_THE_PYTHON,
            endpoint,
            *[str(file), str(link), str(beside), str(said)],
        ]

    started = await one.start(argv, cwd=str(project))
    try:
        report = await _report(said, started)
        came_to = dict(line.split(": ") for line in report.splitlines())
        assert came_to.get("write beside") == "done" and beside.read_text() == "fine", report
        refused = {name: how for name, how in came_to.items() if name != "write beside"}
        assert refused and "done" not in refused.values(), refused
        assert file.read_bytes() == before and not Path(f"{file}.moved").exists()
    finally:
        await started.stop()


# Listens; once the jail has seen it listen, tries what an input could do to each link in argv[2:-2]
# (replace it by one planted beside it, rename it, remove it) and writes a file, argv[-2], beside the
# project's own; says what each came to in argv[-1] (renamed into place, so whole), waits. The links
# are those on the way from the interpreter bh-02 runs on to its file.
_LISTEN_THEN_CHANGE_THE_LINKS = """
import os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
links, beside, said = sys.argv[2:-2], sys.argv[-2], sys.argv[-1]
came_to = []

def attempt(name, action):
    try:
        action()
        came_to.append(name + ": done")
    except OSError as error:
        came_to.append(name + ": " + os.strerror(error.errno))

def replace(link):
    os.symlink("/usr/bin/python3", link + ".planted")
    os.replace(link + ".planted", link)

for number, link in enumerate(links):
    attempt("%d replace" % number, lambda: replace(link))
    attempt("%d rename" % number, lambda: os.rename(link, link + ".moved"))
    attempt("%d remove" % number, lambda: os.unlink(link))
attempt("beside", lambda: open(beside, "w").write("fine"))
with open(said + ".tmp", "w") as report:
    report.write("\\n".join(came_to))
os.replace(said + ".tmp", said)
time.sleep(60)
"""


async def test_a_linux_jail_refuses_an_input_that_changes_a_link_on_the_way_to_the_interpreter_bh_02_runs_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In a real jail, with the layout a project opened at the home directory holds (a venv whose
    `python` goes through uv's link to the versioned directory, all under the project, which an input
    may write): an input can neither rename, remove nor replace any link on the way from
    `sys.executable` to the interpreter file, the link to the directory included, which a mount on
    the file does not hold (it would plant a Python of its own at the name). It writes beside them
    as anywhere in the project."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "records"))
    project = tmp_path / "project"
    venv, file, chain = _a_uv_python_in(project)
    before = {link: os.readlink(link) for link in chain}
    monkeypatch.setattr("runner_cordis_plugin.jail.host_executable", str(venv / "bin" / "python3"))
    one = BrigJail(BrigConfig(), Host())
    said, beside = project / "said", project / "beside"

    def argv(endpoint: str) -> list[str]:
        return [
            sys.executable,
            "-I",
            "-c",
            _LISTEN_THEN_CHANGE_THE_LINKS,
            endpoint,
            *[*map(str, chain), str(beside), str(said)],
        ]

    started = await one.start(argv, cwd=str(project))
    try:
        report = await _report(said, started)
        came_to = dict(line.split(": ") for line in report.splitlines())
        assert came_to.pop("beside", None) == "done" and beside.read_text() == "fine", report
        assert len(came_to) == 3 * len(chain) and "done" not in came_to.values(), came_to
        assert {link: os.readlink(link) for link in chain} == before  # on the host: every link as it was
        assert not [*project.rglob("*.moved"), *project.rglob("*.planted")] and file.is_file()
    finally:
        await started.stop()


# Listens; once the jail has seen it listen, tries to rename each directory in argv[2:-1] to its name
# with `.moved` added, and says what each came to in argv[-1], waits. The directories are those
# between the project and the interpreter file or a link on the way to it, deepest first.
_LISTEN_THEN_RENAME_THE_DIRECTORIES = """
import os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
directories, said = sys.argv[2:-1], sys.argv[-1]
came_to = []
for directory in directories:
    try:
        os.rename(directory, directory + ".moved")
        came_to.append(directory + ": done")
    except OSError as error:
        came_to.append(directory + ": " + os.strerror(error.errno))
open(said, "w").write("\\n".join(came_to))
time.sleep(60)
"""


async def test_a_linux_jail_refuses_a_rename_of_a_directory_on_the_way_to_the_interpreter_bh_02_runs_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In a real jail, with the layout a project opened at the home directory holds (uv's Python and a
    venv whose `python` goes through uv's link, all under the project, which an input may write): an
    input can rename no directory between the project and the interpreter file or a link on the way to
    it, `uv` and `venv` included. rename(2) refuses only a mount point, and `uv` is not one: renamed, it
    would carry its mounts with it, the read-only deny on `uv/python` among them, so a Python planted at
    its old name is the one the next `uv run` on the host would run. brig's pins (decision-168) hold it:
    each existing directory between a write root and a deny is bound over itself, so `uv` and `venv` are
    mount points, which rename refuses as busy; the directories inside a read-only deny refuse as
    read-only. The directories are tried deepest first, so each is tried at its own name; on the host
    every one is still at its name, nothing is left as `*.moved`, and the file is as it was."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "records"))
    project = tmp_path / "project"
    venv, file, chain = _a_uv_python_in(project)
    root = project.resolve()
    between = {p for f in (file, *chain) for p in f.parents if p.is_relative_to(root) and p != root}
    dirs = sorted(between, key=lambda p: (-len(p.parts), str(p)))
    monkeypatch.setattr("runner_cordis_plugin.jail.host_executable", str(venv / "bin" / "python3"))
    one = BrigJail(BrigConfig(), Host())
    said = project / "said"

    def argv(endpoint: str) -> list[str]:
        return [
            sys.executable,
            "-I",
            "-c",
            _LISTEN_THEN_RENAME_THE_DIRECTORIES,
            endpoint,
            *[*map(str, dirs), str(said)],
        ]

    started = await one.start(argv, cwd=str(project))
    try:
        for _ in range(200):  # the file exists before the child writes it: wait for every line
            if said.exists() and len(said.read_text().splitlines()) == len(dirs):
                break
            await asyncio.sleep(0.05)
        came_to = dict(line.split(": ") for line in said.read_text().splitlines())
        assert list(came_to) == [str(d) for d in dirs], came_to  # every directory was tried
        assert set(came_to.values()) <= {os.strerror(errno.EBUSY), os.strerror(errno.EROFS)}, came_to
        assert [d for d in dirs if not d.is_dir()] == [] and not list(project.rglob("*.moved"))  # the host
        assert file.is_file()
    finally:
        await started.stop()


def _marked_groups(marker: str) -> list[int]:
    """The process groups of the live processes whose command line holds `marker`."""
    table = subprocess.run(
        ["/bin/ps", "-Ao", "pgid=,stat=,args="], capture_output=True, text=True, check=True
    ).stdout
    rows = [line.split(None, 2) for line in table.splitlines() if line.strip()]
    return sorted(
        {int(row[0]) for row in rows if len(row) == 3 and marker in row[2] and not row[1].startswith("Z")}
    )


async def _until(check: Any, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        await asyncio.sleep(0.05)
    return bool(check())


def test_the_tripwire_watches_each_held_path_s_directory_by_name() -> None:
    held = ("/w/.git/config", "/w/.git/hooks", "/w/mine.toml", "/w/private.txt", "/w/mine.toml")
    assert wires(held) == {"/w/.git": ("config", "hooks"), "/w": ("mine.toml", "private.txt")}


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


def test_a_linux_jail_trips_on_every_write_deny_under_a_writable_root_and_every_held_secret() -> None:
    policy = spec_for(
        root="/w/app",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(hide=("private.txt",)),
        layers=("/w/app/mine.toml", "/elsewhere/chat.toml"),
        host=(),
    )
    paths = tripwired(policy)
    assert {"/w/app/mine.toml", "/w/app/.git/config", "/w/app/private.txt"} <= set(paths)
    assert "/elsewhere/chat.toml" not in paths  # outside every writable root: nothing is mounted


# A bh-02 killed while its Python process runs an input's background program, which keeps trying to write
# under `.claude/` (Claude Code would run hooks from its settings) and says it is alive: the real
# Python process, in the real jail. argv: the project, then "setsid" to start the program in a session
# of its own (out of the jail's process group), else "group". It says "started" and waits to be
# killed.
_KILLED_WITH_A_BACKGROUND_INPUT = """
import asyncio, sys, time
from runner_cordis_plugin import Approval, BrigConfig, BrigJail, Runner
from python_cordis_plugin import PythonProcess, PythonProcessConfig

class Host:
    paths, secrets, trusted, code, auto_memory = (), (), (), (), ""

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
    runner = Runner(BrigJail(BrigConfig(), Host()))
    process = PythonProcess(runner, PythonProcessConfig(root=sys.argv[1]), rule=Approval(runner))
    await process.__aenter__()
    setsid = sys.argv[2] == "setsid"
    code = (
        "import subprocess, sys\\n"
        f"subprocess.Popen([sys.executable, '-c', {LOOP!r}, 'alive'], start_new_session={setsid})\\n"
        "print('started')"
    )
    print(await process.run(code), flush=True)
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


def test_a_jail_denies_the_interpreter_bh_02_runs_on_when_it_lies_in_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The policy reads the interpreter off the process (`sys.executable`, `sys.base_prefix`) and
    denies the files they lead to: in a venv layout planted under the project, the base's file is
    denied beside its standard library. The base's `python3` is a link, and a mount on a link lands
    on the file it leads to, so the link's own entry is held by the directory that holds it (the
    policy also holds the links on the way)."""
    project = tmp_path / "project"
    file, link, venv = _a_python_in(project)
    module = "runner_cordis_plugin.jail"
    monkeypatch.setattr(f"{module}.host_executable", str(venv / "bin" / "python3"))
    monkeypatch.setattr(f"{module}.base_prefix", str(file.parent.parent))
    monkeypatch.setattr(f"{module}.prefix", str(venv))
    monkeypatch.setattr(f"{module}.import_path", [str(file.parent.parent / "lib" / "python3.15")])
    policy = planned(BrigConfig(), Host(), scratch_root=str(tmp_path / "j"), cwd=str(project), argv=())
    assert _denied(
        policy, str(file.resolve())
    )  # the interpreter, which the venv's links and `python3` lead to
    assert _denied(policy, str(venv / "bin" / "python")) and _denied(
        policy, str(file.parent.parent / "lib" / "python3.15" / "os.py")
    )  # the venv's links and the standard library: held already
    assert (
        str(link) not in policy.write_denies and str(link.parent) in policy.write_denies
    )  # held by its directory


def test_a_jail_denies_the_directory_of_each_link_from_the_interpreter_bh_02_runs_on_to_its_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The policy walks the links from `sys.executable` (and the base's `bin/python3`) to the file,
    one path component at a time, and hands the policy where each sits. The venv here is bh-02's
    interpreter but not `sys.prefix`, so the walk alone holds its `bin`; a project's own venv, whose
    Python is not the one bh-02 runs on, is not on the way to it and is left to the input."""
    project = tmp_path / "project"
    venv, file, chain = _a_uv_python_in(project)
    own = project.resolve() / "own" / ".venv" / "bin"  # the project's own venv, on a Python of its own
    own.mkdir(parents=True)
    (own / "python").symlink_to("/usr/bin/python3")
    module = "runner_cordis_plugin.jail"
    monkeypatch.setattr(f"{module}.host_executable", str(venv / "bin" / "python3"))
    monkeypatch.setattr(f"{module}.base_prefix", str(file.parent.parent))
    policy = planned(BrigConfig(), Host(), scratch_root=str(tmp_path / "j"), cwd=str(project), argv=())
    assert {str(link.parent) for link in chain} == {
        str(venv / "bin"),
        str(file.parent),
        str(file.parent.parent.parent),
    }
    for link in chain:
        assert _denied(policy, str(link.parent / "planted")), link  # nothing can be put beside a link
        assert _denied(policy, str(link)), link
    assert _denied(policy, str(file))
    assert not _denied(policy, str(own / "python")) and not _denied(policy, str(own / "pip"))
    assert not _denied(policy, str(project.resolve() / "notes.md"))


def test_the_walk_to_the_interpreter_follows_relative_links_and_dots_and_ends_at_a_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pyenv and Homebrew write relative links, with `..` in them, and a link to a directory in the
    middle of a path: each is found in the directory that holds it, and only those on the way. A
    loop of links is no interpreter, and the policy does not wait on it."""
    project = tmp_path.resolve() / "project"
    base = project / "store" / "3.15.0"
    (base / "bin").mkdir(parents=True)
    (base / "lib").mkdir()
    shutil.copy2(shutil.which("true") or "/bin/true", base / "bin" / "python3.15")
    (base / "bin" / "python3").symlink_to("python3.15")
    (project / "alias").mkdir()
    (project / "alias" / "current").symlink_to("../store/3.15.0")
    (project / "alias" / "other").symlink_to("../store/other")
    (project / "venv" / "bin").mkdir(parents=True)
    (project / "venv" / "bin" / "python").symlink_to("../../alias/current/bin/python3")
    (project / "loop").mkdir()
    (project / "loop" / "a").symlink_to("b")
    (project / "loop" / "b").symlink_to("a")
    module = "runner_cordis_plugin.jail"
    monkeypatch.setattr(f"{module}.base_prefix", str(base))

    def compiled(executable: Path) -> Policy:
        monkeypatch.setattr(f"{module}.host_executable", str(executable))
        return planned(BrigConfig(), Host(), scratch_root=str(tmp_path / "j"), cwd=str(project), argv=())

    spec = compiled(project / "venv" / "bin" / "python")
    ways = ("venv/bin", "alias", "store/3.15.0/bin")  # the links' own directories: not the ones they lead to
    assert all(_denied(spec, f"{project}/{way}/planted") for way in ways)
    assert not _denied(spec, f"{project}/store/other") and not _denied(spec, f"{base}/lib/planted")
    assert not _denied(spec, f"{project}/loop/planted")
    assert _denied(compiled(project / "loop" / "a"), f"{project}/loop/planted")


def test_a_linux_jail_reads_bh_02_s_own_code_and_writes_none_of_it(tmp_path: Path) -> None:
    """A Linux jail reads by allowlist. The extensions process imports cordis, and with an
    editable install that is the workspace's `src/cordis`, outside the project and the
    interpreter: so the allowlist names bh-02's own code (`host.code`), read-only (outside
    every writable root nothing writes it; under one, it is denied above), and never the
    workspace itself, whose files an input must not read."""
    readable = readable_roots(
        argv=["/w/.venv/bin/python", "-I", f"{_CODE[1]}/worker.py", "/tmp/k/k.sock"],
        interpreter=("/opt/py", "/w/.venv"),
        system=SYSTEM_READABLE,
        code=_CODE,
    )
    assert set(_CODE) <= set(readable) and len(readable) == len(set(readable))
    assert _CHECKOUT not in readable and f"{_CHECKOUT}/libs/cordis/src" not in readable
    policy = spec_for(
        root="/w/app",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(),
        layers=(),
        host=(),
        code=_CODE,
    )
    linux = allowlisted(policy, readable)
    read = linux.readable  # brig keeps a tree once: one under another (`/opt/py`) is that one
    assert all(any(c == r or c.startswith(r + "/") for r in read) for c in _CODE), read
    assert not any(c == w or c.startswith(w + "/") for c in _CODE for w in linux.writable)
    # and the row's jail reads them: a root of its policy, bound read-only as they are on the host
    package = tmp_path / "src" / "cordis"
    package.mkdir(parents=True)
    project = tmp_path / "project"
    project.mkdir()
    planned_policy = planned(
        BrigConfig(), Host(code=(str(package),)), scratch_root=str(tmp_path / "j"), cwd=str(project), argv=()
    )
    assert str(package) in planned_policy.readable and str(package) not in planned_policy.writable


async def test_a_linux_jail_ends_when_the_host_replaces_or_removes_a_secret_it_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The jail holds a secret under the project with a mount on its path (a `/dev/null` over the
    file), and a write-denied path that is not there (`.envrc`) with an empty directory. Replacing
    the file on the host the way an editor saves (a new file renamed over it), or removing the
    empty directory, detaches that mount inside the jail (measured before the tripwire: the
    workload then read the new file and created the absent one), so the jail ends itself at once
    and says why. A new jail holds both again. `fs_read` stays best-effort: a file created on the
    host at an absent secret that is not held is still readable."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    secret, absent, seen = project / "private.txt", project / ".envrc", project / "seen"
    secret.write_text("OLD=1\n")  # a stand-in: never the real file
    one = BrigJail(BrigConfig(hide=("private.txt",)), Host())

    async def jailed() -> Any:
        def argv(endpoint: str) -> list[str]:
            return [
                sys.executable,
                "-I",
                "-c",
                _LISTEN_THEN_READ_AND_PLANT,
                endpoint,
                *map(str, (secret, absent, seen)),
            ]

        return await one.start(argv, cwd=str(project))

    started = await jailed()
    try:
        assert started.report()["fs_read"] == "best_effort"
        assert str(secret) in started.notice()
        await asyncio.sleep(0.5)
        assert not seen.exists() and absent.is_dir() and started.ended() == ""  # held
        group = started.group
        (project / "saved.tmp").write_text("NEW=1\n")
        (project / "saved.tmp").replace(secret)  # an editor's save
        assert await _gone(group)  # the jail ended itself
        assert str(secret) in started.ended() and "the next one holds it again" in started.ended()
    finally:
        await started.stop()
    started = await jailed()
    try:
        group = started.group
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


async def test_the_tripwire_ends_the_whole_jail_a_program_in_a_session_of_its_own_included(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The program an input runs starts another in a session of its own (out of its process group),
    then the host removes a placeholder the jail holds: the tripwire ends the jail, and the
    program that left the group goes with it. The control: until the host does, both run.

    A jail's processes are brig's supervisor's children (brig's decision-190), so the program's
    group is no longer the jail's: killing it would leave the other program running, with the
    mount lifted, until the owner stopped the jail. The tripwire ends the jail, not the group."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    absent = project / ".envrc"
    marker = f"{uuid.uuid4().int % 10**9 + 10**9}.{uuid.uuid4().int % 10**6:06d}"
    one = BrigJail(BrigConfig(), Host())

    def argv(endpoint: str) -> list[str]:
        return [sys.executable, "-I", "-c", _LISTEN_WITH_A_SESSION_OF_ITS_OWN, endpoint, marker]

    started = await one.start(argv, cwd=str(project))
    try:
        assert await _until(lambda: bool(_marked_groups(marker)), 5.0), "CONTROL failed: it never ran"
        assert started.ended() == "" and absent.is_dir()  # held
        absent.rmdir()  # the host undoes a mount the jail holds
        assert await _until(lambda: not _marked_groups(marker), 10.0), (
            "the program in a session of its own outlived the tripwire"
        )
        assert str(absent) in started.ended()
    finally:
        await started.stop()


async def test_a_jail_whose_hold_the_host_lifted_ends_at_once_whatever_its_programs_do_with_sigterm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The host removes a placeholder the jail holds, so the mount inside is gone and an input
    may create the secret's file on the host. Programs that ignore SIGTERM (one of them in a
    session of its own) keep trying every 10 ms. The tripwire ends the jail with SIGKILL and no
    SIGTERM first (brig's `destroy(grace=0)`, decision-193), so how long the jail survives it is
    the kernel's, milliseconds, and not the 2 s grace a teardown that sent SIGTERM first gives
    a program that ignores it: measured 2.01 to 2.06 s, the secret planted on the host 3 times
    in 3. The control: the same programs run, and both are writing, until the host lifts it.

    Not asserted: that nothing is planted. A program trying every 10 ms can land one in the few
    milliseconds the kill takes, and a test that depends on missing it would flake; the bound is
    on how long the jail survives, which is what decides how many it can land."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    absent, stamp = project / ".envrc", project / "stamp"
    one = BrigJail(BrigConfig(), Host())

    def argv(endpoint: str) -> list[str]:
        return [sys.executable, "-I", "-c", _HOSTILE_IGNORING_SIGTERM, endpoint, str(absent), str(stamp)]

    started = await one.start(argv, cwd=str(project))
    try:
        assert await _until(stamp.exists, 5.0), "CONTROL failed: the second program never ran"
        first = stamp.read_text()
        await asyncio.sleep(0.2)
        assert stamp.read_text() != first and absent.is_dir() and started.ended() == "", "CONTROL failed"
        group = started.group
        lifted_at = time.time()
        began = time.monotonic()
        absent.rmdir()  # the host undoes a mount the jail holds
        assert await _gone(group, within=5.0), "the jail outlived the tripwire by 5 s"
        survived = time.monotonic() - began
        assert survived < 1.0, (
            f"the jail survived the tripwire for {survived:.2f} s (a SIGTERM's grace is 2 s)"
        )
        # the namespace's last processes go a moment after bubblewrap does, longer on a busy machine:
        # the stamp must stop changing, not stop at once
        last = float(stamp.read_text() or "0")
        for _ in range(20):
            await asyncio.sleep(0.3)
            now = float(stamp.read_text() or "0")
            if now == last:
                break
            last = now
        else:
            pytest.fail("the program in a session of its own kept running")
        assert last - lifted_at < 2.0
        assert str(absent) in started.ended() and "did not complete" not in started.ended()
    finally:
        await started.stop()
        if absent.is_file():  # what the one that got in left on the host, for the next test's sake
            absent.unlink()


async def test_a_linux_jail_ends_when_the_host_renames_over_a_write_deny_and_a_new_one_holds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The jail holds `.git/config` read-only with a bind mount on its path. A host `git config`
    saves the file by renaming a new one over it, which detaches that mount inside the jail
    (measured before the tripwire: the workload then wrote the file), so the jail ends itself at
    once and says why. A new jail (the next input's) holds it again."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    made = await asyncio.create_subprocess_exec("git", "init", "-q", str(project))
    assert await made.wait() == 0
    config = project / ".git" / "config"

    async def jailed() -> Any:
        def argv(endpoint: str) -> list[str]:
            return [sys.executable, "-I", "-c", _LISTEN_THEN_APPEND, endpoint, str(config)]

        return await BrigJail(BrigConfig(), Host()).start(argv, cwd=str(project))

    started = await jailed()
    try:
        await asyncio.sleep(0.5)
        assert "planted" not in config.read_text() and started.ended() == ""  # held
        group = started.group
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


async def test_git_init_on_the_host_works_while_a_jail_runs_in_a_project_that_is_no_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project that isn't a repository has no `.git`, so the jail holds `.git` itself (an empty
    directory) rather than a `.git/config` directory inside it, which would break the person's
    own `git init`. That works on the host while the Python process runs; inside the jail `.git` stays
    what it was held as, and the new repository outlives the jail."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    one = BrigJail(BrigConfig(), Host())
    git_config = project / ".git" / "config"

    def argv(endpoint: str) -> list[str]:
        return [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(git_config)]

    started = await one.start(argv, cwd=str(project))
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
    """Two Python processes in one project (two sessions). The first makes the empty `.claude/` it mounts
    over; the second, starting while it lives, binds that directory read-only over itself. When
    the first stops it must not remove it: removed on the host, the second's bind is detached
    and the second writes `.claude/settings.json`, which Claude Code would run hooks from.
    Linux only, with bubblewrap: the placeholders are bubblewrap's."""
    if sys.platform != "linux" or not Path("/usr/bin/bwrap").exists():
        pytest.skip("the placeholders are bubblewrap's: Linux with /usr/bin/bwrap only")
    project = tmp_path / "project"
    project.mkdir()
    claude = project / ".claude"
    jails = [BrigJail(BrigConfig(), Host()) for _ in range(2)]
    started = []
    for n, one in enumerate(jails):

        def argv(endpoint: str) -> list[str]:
            return [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(claude)]

        started.append(await one.start(argv, cwd=str(project)))
        assert claude.is_dir(), n  # the first made it; the second found it
    await started[0].stop()
    await asyncio.sleep(1.0)  # the second's workload keeps trying to write under .claude
    try:
        assert claude.is_dir() and not (claude / "settings.json").exists()
    finally:
        await started[1].stop()
    assert not (claude / "settings.json").exists()


def test_a_policy_becomes_brig_s_policies_and_nothing_else_reaches_the_program() -> None:
    """`to_brig` is the one converter: the policy's roots, denies and masks as brig's `FsPolicy`
    (readable roots by allowlist, the whole host by denylist), an allow-list that names the policy's
    own variables beside the baseline, a candidate environment holding both the host's and the
    policy's values, and the program's streams (stdin from /dev/null, the others to the files
    named)."""
    policy = spec_for(
        root="/w/app",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(hide=("private.txt",)),
        layers=("/w/app/mine.toml",),
        host=(),
    )
    linux = allowlisted(policy, ("/usr", "/etc"))
    environ = {"PATH": "/usr/bin", "CLAUDE_CODE_OAUTH_TOKEN": "not-a-credential", "TMPDIR": "/host/tmp"}
    brigged = to_brig(
        replace(linux, env_set=(*linux.env_set, ("GIT_AUTHOR_NAME", "Pat"))),
        environ=environ,
        stdout="/tmp/l/stdout.log",
        stderr="/tmp/l/stderr.log",
    )
    assert brigged.fs.readable == ("/etc", "/usr") and brigged.fs.writable == linux.writable
    assert brigged.fs.write_denies == linux.write_denies and brigged.fs.masks == linux.masks
    assert {"PATH", "HOME", "TMPDIR", "GIT_AUTHOR_NAME"} <= set(brigged.env_policy.allowed)
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in brigged.env_policy.allowed  # in the candidate, never let through
    env = dict(brigged.env)
    assert env["TMPDIR"] == "/tmp/j/tmp" and env["GIT_AUTHOR_NAME"] == "Pat" and env["PATH"] == "/usr/bin"
    assert (brigged.stdio.stdin, brigged.stdio.stdout, brigged.stdio.stderr) == (
        "/dev/null",
        "/tmp/l/stdout.log",
        "/tmp/l/stderr.log",
    )
    by_denylist = to_brig(policy, environ={}, stdout="/o", stderr="/e")
    assert by_denylist.fs.readable == ("/",)  # everything but the masks


def test_brig_s_report_is_the_runner_s_in_lower_case_and_the_planned_one_is_no_stronger() -> None:
    _Named = namedtuple("_Named", "name")

    def claim(name: str) -> Any:  # brig's `Claim`, which report_of reads the name of
        return _Named(name)

    def grade(value: str) -> Any:  # brig's `Grade`, a string enum in upper case
        return SimpleNamespace(value=value)

    graded = {
        claim("fs_write"): grade("BEST_EFFORT"),
        claim("fs_read"): grade("ENFORCED"),
        claim("network"): grade("ENFORCED"),
        claim("channel_exclusivity"): grade("VIOLATED"),
    }
    assert report_of(graded) == {
        "fs_write": "best_effort",
        "fs_read": "enforced",
        "network": "enforced",
        "channel_exclusivity": "violated",
    }
    assert PLANNED["fs_write"] == "best_effort" and PLANNED["network"] == "enforced"


async def test_a_platform_brig_has_no_jail_for_is_refused_by_name(tmp_path: Path) -> None:
    """darwin has no jail type in brig yet (TASK-0176.05), so `runner:confined` refuses there and
    says what to use instead; so does any other platform."""
    for platform in ("darwin", "freebsd"):
        one = BrigJail(BrigConfig(), Host(), platform=platform)
        with pytest.raises(RuntimeError, match=rf"this is {platform}.*`runner:unconfined`"):
            await one.start(_listening, cwd=str(tmp_path))


async def test_a_host_with_no_bubblewrap_is_refused_with_what_a_person_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("runner_cordis_plugin.jail.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match=r"no `bwrap` on PATH.*`runner:unconfined`"):
        await BrigJail(BrigConfig(), Host(), platform="linux").start(_listening, cwd=str(tmp_path))


async def test_a_policy_that_mounts_no_interpreter_is_refused_by_brig_before_anything_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """brig runs its supervisor, the jail's PID 1, under bh-02's own interpreter and refuses a
    policy that does not mount it: here a host whose interpreter lies under no tree the jail reads
    (the policy names none of `sys.prefix`'s trees). Nothing is made on the host."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    module = "runner_cordis_plugin.jail"
    monkeypatch.setattr(f"{module}.base_prefix", str(tmp_path / "nowhere"))
    monkeypatch.setattr(f"{module}.prefix", str(tmp_path / "nowhere"))
    monkeypatch.setattr(f"{module}.host_executable", "/usr/bin/python3")
    with pytest.raises(Exception, match="add a readable root") as raised:
        await BrigJail(BrigConfig(), Host()).start(_listening, cwd=str(project))
    assert type(raised.value).__name__ == "PolicyInterpreterUnreachable"
    assert list(project.iterdir()) == []


async def test_a_jail_that_fails_to_launch_leaves_nothing_on_the_host(tmp_path: Path) -> None:
    """A program that ends before it listens: the start says so with what it wrote, and the
    directories the jail made (the placeholders brig makes in the project, the scratch and the logs)
    are gone, as a stop would leave them."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    program = "import sys; sys.stderr.write('no listening today')"
    with pytest.raises(RuntimeError, match=r"(?s)never listened.*no listening today"):
        await BrigJail(BrigConfig(), Host()).start(
            lambda endpoint: [sys.executable, "-I", "-c", program], cwd=str(project)
        )
    assert list(project.iterdir()) == []
    assert list((tmp_path / "state" / "bh-02" / "jails").iterdir()) == []


async def test_a_jail_start_cancelled_while_it_launches_ends_what_the_launch_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launch runs in a thread, which a cancellation doesn't stop: the start waits for it,
    ends the jail it made and removes what it made on the host, then lets the cancellation through."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    marker = f"{uuid.uuid4().int % 10**9 + 10**9}.{uuid.uuid4().int % 10**6:06d}"
    real = jail_module.create_bwrap_jail

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.4)
        return real(*args, **kwargs)

    monkeypatch.setattr("runner_cordis_plugin.jail.create_bwrap_jail", slow)
    starting = asyncio.ensure_future(
        BrigJail(BrigConfig(), Host()).start(
            lambda endpoint: [sys.executable, "-I", "-c", _LISTEN, endpoint, marker], cwd=str(project)
        )
    )
    await asyncio.sleep(0.1)  # launching
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    assert await _until(lambda: not _marked_groups(marker), 5.0), "the program the launch started still runs"
    assert list(project.iterdir()) == []


def _alive(group: int) -> bool:
    """Whether a process of `group` lives (a zombie counts as gone)."""
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except OSError:
                continue
            if fields[0] != "Z" and fields[2] == str(group):
                return True
    return False


async def test_each_start_keeps_what_it_is_whatever_the_jail_starts_after_it(tmp_path: Path) -> None:
    """The runner starts two programs, the Python process and the extensions process, each
    from a command of its own. What a start is (the trees its program reads, which name the
    program's own directory; the roots it writes; its notice and grades) is that start's: the
    second start replaces none of the first's, so the Python process's notice never names the
    extensions' worker's trees. The jail's own grades are what was known before either."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    secret = project / "private.txt"  # a secret under the project: masked, so held
    secret.write_text("OLD=1\n")  # a stand-in: never a real file
    for name in ("python", "extensions"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "worker.py").write_text(_LISTEN)
    one = BrigJail(BrigConfig(hide=("private.txt",)), Host())
    before = dict(one.report())
    started = []
    try:
        for name in ("python", "extensions"):

            def argv(endpoint: str, name: str = name) -> list[str]:
                return [sys.executable, "-I", str(tmp_path / name / "worker.py"), endpoint]

            started.append(await one.start(argv, cwd=str(project)))
        python_process, extensions = started
        assert str(tmp_path / "python") in python_process.reads(), python_process.reads()
        assert (
            str(tmp_path / "extensions") not in python_process.reads()
        )  # the second start's, not the first's
        assert str(tmp_path / "extensions") in extensions.reads()
        assert python_process.writes() == extensions.writes() == (str(project.resolve()),)
        assert str(secret) in python_process.notice() and python_process.report()["fs_read"] == "best_effort"
        assert one.report() == before
    finally:
        for each in started:
            await each.stop()


async def test_a_start_s_grades_are_brig_s_and_the_planned_ones_are_no_stronger(tmp_path: Path) -> None:
    """Each axis a start reports is brig's grade of its jail, by name in lower case; the grades
    known before anything starts (what `approval` reads) are no stronger than a start's on any
    axis they name, and the start is `confined` for `approval` (writes best-effort, the network
    enforced)."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    one = BrigJail(BrigConfig(), Host())
    started = await one.start(_listening, cwd=str(project))
    try:
        report = dict(started.report())
        order = ["violated", "unenforced", "best_effort", "enforced"]
        assert set(report.values()) <= set(order), report
        assert report["network"] == report["env"] == "enforced" and report["fs_write"] == "best_effort"
        assert all(
            order.index(planned_grade) <= order.index(report[axis])
            for axis, planned_grade in one.report().items()
        )
        assert is_confined(report)
    finally:
        await started.stop()


async def test_release_frees_what_the_programs_held_once_each_owner_stopped_its_own(tmp_path: Path) -> None:
    """The runner starts the Python process and the extensions' worker, and both jails hold the
    absent `.envrc` (an empty directory in its place). On `/release` each owner stops its own
    program (`on_release`), and brig removes the placeholder once no jail holds it: the path is
    free. The runner stays released, so the extensions' worker waits, until the next start (the
    next input's Python process)."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    placeholder = project / ".envrc"
    runner = Runner(BrigJail(BrigConfig(), Host()))
    started = []
    for _ in ("python", "extensions"):
        started.append(await runner.start(_listening, cwd=str(project)))
        runner.on_release(_stops(started[-1]))
    try:
        groups = [each.group for each in started]
        assert placeholder.is_dir()
        said = await runner.release()
        assert said == "", said  # nothing still runs
        assert not placeholder.exists()
        for group in groups:
            assert await _gone(group)
        assert runner.released()
        again = await runner.start(_listening, cwd=str(project))
        try:
            assert not runner.released() and placeholder.is_dir()  # the next input's jail holds it again
        finally:
            await again.stop()
    finally:
        for each in started:
            await each.stop()  # again: nothing more happens


def _stops(started: Any) -> Any:
    """An owner's stop for `/release` (`Runner.on_release`): stop its own program, say nothing."""

    async def stop() -> str:
        await started.stop()
        return ""

    return stop


async def test_release_never_stops_a_program_its_owner_did_not_and_says_it_still_holds(
    tmp_path: Path,
) -> None:
    """The runner stops no row's program: one whose owner registered no stop keeps running, its
    jail keeps the path held, and `/release` says so, naming the way out."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    runner = Runner(BrigJail(BrigConfig(), Host()))
    kept = await runner.start(_listening, cwd=str(project))
    try:
        said = await runner.release()
        assert "still runs" in said and "/restart" in said, said
        assert (project / ".envrc").is_dir() and kept.ended() == ""
    finally:
        await kept.stop()


async def test_release_waits_for_a_start_under_way_and_says_it_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start under way when `release` begins (the extensions' worker loading as the person
    types `/release`) is waited for, so `/release` does not answer before it; its owner had
    nothing to stop when asked, so `/release` says a program still runs."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    real = jail_module.create_bwrap_jail

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.4)
        return real(*args, **kwargs)

    monkeypatch.setattr("runner_cordis_plugin.jail.create_bwrap_jail", slow)
    runner = Runner(BrigJail(BrigConfig(), Host()))
    starting = asyncio.ensure_future(runner.start(_listening, cwd=str(project)))
    await asyncio.sleep(0.1)  # launching
    said = await runner.release()
    assert starting.done(), "release answered before the start under way had"
    started = await starting
    try:
        assert "still runs" in said, said
        assert (project / ".envrc").is_dir()  # still its jail's
    finally:
        await started.stop()
    assert list(project.iterdir()) == []  # its placeholders went with it


async def test_an_input_creating_a_hidden_file_the_project_lacks_is_refused_and_leaves_the_jail_running(
    tmp_path: Path,
) -> None:
    """The project's `private.txt`, a file `hide` names, is absent: brig holds the path with an empty
    directory for the jail's life, so an input can neither read nor create it. The jail's own
    making of that directory must not trip its tripwire, which would end the jail before the
    input began and blame the host. The host removing a placeholder the jail holds still ends it."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    created, done = project / "private.txt", project / "done"
    program = _LISTEN_THEN_TRY_TO_CREATE

    def argv(endpoint: str) -> list[str]:
        return [sys.executable, "-I", "-c", program, endpoint, str(created), str(done)]

    started = await BrigJail(BrigConfig(hide=("private.txt",)), Host()).start(argv, cwd=str(project))
    try:
        await _report(done, started)
        await asyncio.sleep(0.3)  # the tripwire's thread has read the creation, if it watches it
        assert done.read_text() == "refused" and created.is_dir() and list(created.iterdir()) == []
        assert started.ended() == "", started.ended()
        assert _alive(started.group)  # still running
        (project / ".envrc").rmdir()  # a placeholder the jail holds, removed on the host
        assert await _gone(started.group)
        assert str(project / ".envrc") in started.ended()
    finally:
        await started.stop()


_LISTEN_THEN_TRY_TO_CREATE = """
import os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
try:
    open(sys.argv[2], "w").write("MINE=1\\n")
    said = "created"
except OSError:
    said = "refused"
open(sys.argv[3] + ".tmp", "w").write(said)
os.replace(sys.argv[3] + ".tmp", sys.argv[3])
time.sleep(60)
"""


async def test_a_deny_inside_another_is_left_to_the_outer_one(tmp_path: Path) -> None:
    """An absent secret in a directory the project denies writing: that directory is read-only
    already, and brig makes no mount point for the secret in it, so the jail starts, nothing is
    made on the host there, and the input can create neither the secret nor anything beside it."""
    _needs_bwrap()
    project = tmp_path / "project"
    (project / "pkg" / "src").mkdir(parents=True)
    done = project / "done"
    program = _LISTEN_THEN_TRY_TO_CREATE

    def argv(endpoint: str) -> list[str]:
        return [
            sys.executable,
            "-I",
            "-c",
            program,
            endpoint,
            str(project / "pkg" / "src" / "private.txt"),
            str(done),
        ]

    config = BrigConfig(deny=("pkg/src",), hide=("pkg/src/private.txt",))
    started = await BrigJail(config, Host()).start(argv, cwd=str(project))
    try:
        await _report(done, started)
        assert done.read_text() == "refused" and list((project / "pkg" / "src").iterdir()) == []
    finally:
        await started.stop()


_LISTEN_THEN_REPORT_THE_ENVIRONMENT = """
import json, os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
open(sys.argv[2] + ".tmp", "w").write(json.dumps(dict(os.environ)))
os.replace(sys.argv[2] + ".tmp", sys.argv[2])
time.sleep(60)
"""


async def test_the_program_sees_the_allowlist_and_what_the_policy_sets_and_nothing_else_of_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bh-02's environment is the candidate and brig's allow-list the whole of what reaches the
    program: the baseline and the policy's own (`TMPDIR`, the scratch directory), not a credential
    the person exports, nor a variable the policy does not name."""
    _needs_bwrap()
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "not-a-credential")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-key")
    monkeypatch.setenv("SOME_OTHER_VARIABLE", "x")
    project = tmp_path / "project"
    project.mkdir()
    said = project / "environment.json"

    def argv(endpoint: str) -> list[str]:
        return [sys.executable, "-I", "-c", _LISTEN_THEN_REPORT_THE_ENVIRONMENT, endpoint, str(said)]

    started = await BrigJail(BrigConfig(), Host()).start(argv, cwd=str(project))
    try:
        seen = json.loads(await _report(said, started))
        assert "PATH" in seen and seen["TMPDIR"].endswith("/tmp")
        assert not {"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "SOME_OTHER_VARIABLE"} & set(seen), set(
            seen
        )
    finally:
        await started.stop()


_LISTEN_THEN_DIAL = """
import os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
client = socket.socket(socket.AF_UNIX)
try:
    client.connect(sys.argv[2])
    said = "connected"
except OSError as error:
    said = "refused"
open(sys.argv[3] + ".tmp", "w").write(said)
os.replace(sys.argv[3] + ".tmp", sys.argv[3])
time.sleep(60)
"""


async def test_one_jail_cannot_dial_another_jail_s_channel(tmp_path: Path) -> None:
    """Planted: a jail whose program dials the socket another jail listens on (path known to it,
    as one in the same project would know it). The other jail's channel directory is not in its
    view, so nothing answers. Control: the owner (bh-02) dials either one."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    one = BrigJail(BrigConfig(), Host())
    victim = await one.start(_listening, cwd=str(project))
    said = project / "said"
    try:

        def argv(endpoint: str) -> list[str]:
            return [sys.executable, "-I", "-c", _LISTEN_THEN_DIAL, endpoint, victim.endpoint, str(said)]

        attacker = await one.start(argv, cwd=str(project))
        try:
            _, writer = await asyncio.open_unix_connection(victim.endpoint)  # CONTROL: the owner can
            writer.close()
            _, writer = await asyncio.open_unix_connection(
                attacker.endpoint
            )  # (accepts: the program goes on)
            writer.close()
            assert await _report(said, attacker) == "refused"
        finally:
            await attacker.stop()
    finally:
        await victim.stop()


_LISTEN_AND_SAY_ON_INTERRUPT = """
import os, signal, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
def interrupted(*_):
    open(sys.argv[2] + ".tmp", "w").write("interrupted")
    os.replace(sys.argv[2] + ".tmp", sys.argv[2])
signal.signal(signal.SIGINT, interrupted)
while True:
    time.sleep(0.05)
"""


async def test_interrupting_a_running_input_reaches_the_program_and_the_program_survives_it(
    tmp_path: Path,
) -> None:
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    said = project / "said"

    def argv(endpoint: str) -> list[str]:
        return [sys.executable, "-I", "-c", _LISTEN_AND_SAY_ON_INTERRUPT, endpoint, str(said)]

    started = await BrigJail(BrigConfig(), Host()).start(argv, cwd=str(project))
    try:
        assert started.interrupt() is True
        assert await _report(said, started) == "interrupted"
        await asyncio.sleep(0.3)
        assert _alive(started.group) and started.ended() == ""
    finally:
        await started.stop()
    assert started.interrupt() is False  # nothing left to interrupt


async def test_a_killed_bh_02_s_jail_ends_with_it_and_the_next_jail_removes_what_it_left(
    tmp_path: Path,
) -> None:
    """bh-02 killed with SIGKILL while a program an input started runs in the background, in a
    session of its own: the jail ends with bh-02 (bubblewrap's `--die-with-parent`, and its
    namespace with it, so a program that left the group goes too). What it made on the host stays
    (`.claude/`, an empty directory), and the next jail brig starts removes it with its own at its end."""
    _needs_bwrap()
    project = tmp_path / "project"
    project.mkdir()
    await _killed_with_a_background_input(project, "setsid")
    await asyncio.sleep(1.0)
    assert not await _still_writing(project / "alive")  # the program is gone
    (record,) = (
        found
        for found in Path(os.environ["BRIG_HOME"], "placeholders").glob("*.json")
        if str(project) in found.read_text()  # this test's: every test of the process shares brig's directory
    )
    group = json.loads(record.read_text())["jail"][0]  # bubblewrap's pid, which leads the jail's group
    assert await _gone(group, within=10.0), "the jail outlived the bh-02 that started it"
    assert (project / ".claude").is_dir() and not list((project / ".claude").iterdir())
    one = BrigJail(BrigConfig(), Host())
    await (await one.start(_listening, cwd=str(project))).stop()  # brig swept
    assert sorted(p.name for p in project.iterdir()) == ["alive", "alive.pid"]


async def test_on_linux_the_tripwire_ends_what_it_was_armed_with_when_a_held_file_is_renamed_over(
    tmp_path: Path,
) -> None:
    """The shell, without bubblewrap: a held file renamed over calls what the wire was armed with
    (here, a kill of a process group) and says why; a file beside it changing does nothing."""
    if sys.platform != "linux":
        pytest.skip("inotify is Linux's")
    held_file = tmp_path / "config"
    held_file.write_text("a")
    victim = subprocess.Popen(["sleep", "30"], start_new_session=True)
    wire = Tripwire([str(held_file)])

    def end() -> None:
        os.killpg(victim.pid, signal.SIGKILL)

    wire.arm(end, fallback=lambda: pytest.fail("the fallback is for a teardown that raised"))
    try:
        (tmp_path / "beside").write_text("b")  # not held: nothing happens
        await asyncio.sleep(0.1)
        assert victim.poll() is None and wire.tripped == ""
        (tmp_path / "config.new").write_text("c")
        (tmp_path / "config.new").replace(held_file)
        assert await asyncio.to_thread(victim.wait, 2) == -signal.SIGKILL
        assert str(held_file) in wire.tripped and "did not complete" not in wire.tripped
    finally:
        wire.stop()
        victim.kill()


async def test_a_teardown_that_raised_is_followed_by_a_kill_and_tripped_says_so(tmp_path: Path) -> None:
    """A teardown that raised must not leave the jail running with no trace: the wire kills the
    jail's group directly (`fallback`) and `tripped` says brig's teardown raised and what the kill
    does not reach."""
    if sys.platform != "linux":
        pytest.skip("inotify is Linux's")
    held_file = tmp_path / "config"
    held_file.write_text("a")
    victim = subprocess.Popen(["sleep", "30"], start_new_session=True)
    wire = Tripwire([str(held_file)])
    killed: list[str] = []

    def end() -> None:
        raise OSError("no teardown today")

    wire.arm(end, fallback=lambda: (killed.append("group"), os.killpg(victim.pid, signal.SIGKILL)))
    try:
        (tmp_path / "config.new").write_text("c")
        (tmp_path / "config.new").replace(held_file)
        assert await asyncio.to_thread(victim.wait, 2) == -signal.SIGKILL
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and "did not complete" not in wire.tripped:
            await asyncio.sleep(0.02)
        assert "did not complete" in wire.tripped and str(held_file) in wire.tripped, wire.tripped
        assert killed == ["group"] and "no teardown today" in wire.tripped
    finally:
        wire.stop()
        victim.kill()


def test_what_a_teardown_could_not_end_is_named_and_nothing_added_when_it_ended_everything() -> None:
    assert unended_for("") == ""
    note = unended_for("JailTeardownFailed: x")
    assert "JailTeardownFailed: x" in note and "end them yourself" in note
