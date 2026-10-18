"""The policy as a function, and the row. Real inputs in a real jail are
bh-02/app/tests/test_python_repl.py's: they need a Python process, which is another plugin's."""

import asyncio
import contextlib
import ctypes
import errno
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cordis.testing import drive
from runner_cordis_plugin import (
    MARK,
    SYSTEM_READABLE,
    BrigConfig,
    BrigJail,
    Runner,
    Tripwire,
    allowlisted,
    confined,
    decoded,
    git_author,
    graded,
    group_alive,
    held,
    holding,
    host_interpreters,
    identity,
    lifted,
    link_directories,
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
    still_running,
    supervisor_interpreter,
    told_reads,
    tripwired,
    uncovered,
    unended_for,
    wires,
)


@dataclass(frozen=True)
class Host:
    paths: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    auto_memory: str = ""


def test_the_project_s_auto_memory_directory_is_a_root_an_input_may_write() -> None:
    """Outside the project, so the model can keep memories across sessions that are never
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
        "/tmp/k",  # the socket's directory (brig's decision-186; TASK-0079.31 replaces it)
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
    ).fs.write_allows == ("/tmp/j/tmp", "/tmp/k", "/w/app")


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
    assert spec.fs.write_allows == ("/tmp/j/tmp", "/tmp/k", "/w/app")
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
    # The channel by name; its socket's directory is a write root (above), as brig granted it
    # per channel until its decision-186.
    assert [c.name for c in spec.channels] == ["program"]


#: The made-up home, resolved the way `spec_for` resolves a root (`Path.resolve`): on macOS
#: `/home/me` is `/System/Volumes/Data/home/me`, and `spec_for` compares the `trusted` and `code`
#: paths it is handed, which the program supplies already resolved, with its resolved roots.
_HOME = str(Path("/home/me").resolve())


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
    trusted = (f"{_HOME}/xdg/bh-02", f"{_HOME}/.config/bh-02", "/elsewhere/bh-02")

    def home_rooted(root: str, write: Sequence[str] = (".",)) -> Any:
        return spec_for(
            root=root,
            endpoint="/tmp/k/k.sock",
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
    assert "/elsewhere/bh-02" not in spec.fs.write_denies  # outside every writable root
    project = home_rooted(f"{_HOME}/src/app")  # the usual case: the home is not writable at all
    assert not set(trusted) & set(project.fs.write_denies)
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
            endpoint="/tmp/k/k.sock",
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
        assert _CODE[3] not in spec.fs.write_denies  # outside every writable root
        assert not _denied(spec, f"{_CHECKOUT}/README.md")  # the rest of the checkout is the project's
    elsewhere = rooted(f"{_HOME}/work/app")  # the usual case: none is under the project
    assert not set(_CODE) & set(elsewhere.fs.write_denies)
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
            endpoint="/tmp/k/k.sock",
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
    assert interpreter not in elsewhere.fs.write_denies
    system = rooted(_HOME, in_a_venv, ("/usr/bin/python3.13",))  # a system Python, outside every root
    assert "/usr/bin/python3.13" not in system.fs.write_denies
    in_its_directory = rooted(f"{base}/bin", in_a_venv)  # the project is its directory: only the file
    assert _denied(in_its_directory, interpreter) and not _denied(in_its_directory, f"{base}/bin/notes.md")
    itself = rooted(interpreter, in_a_venv)  # a root is never denied, or the project would be read-only
    assert interpreter not in itself.fs.write_denies


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


def test_a_jail_denies_the_interpreter_bh_02_runs_on_when_it_lies_in_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compile reads the interpreter off the process (`sys.executable`, `sys.base_prefix`) and
    gives the policy the files they lead to: in a venv layout planted under the project, the base's
    file is denied beside its standard library. The base's `python3` is a link, and a mount on a
    link lands on the file it leads to, so the link's own entry is held by the directory that holds
    it (the compile also hands the policy the links on the way): which is also why it may be the
    supervisor's Python, as the file may."""
    project = tmp_path / "project"
    file, link, venv = _a_python_in(project)
    module = "runner_cordis_plugin.jail"
    monkeypatch.setattr(f"{module}.host_executable", str(venv / "bin" / "python3"))
    monkeypatch.setattr(f"{module}.base_prefix", str(file.parent.parent))
    monkeypatch.setattr(f"{module}.prefix", str(venv))
    monkeypatch.setattr(f"{module}.import_path", [str(file.parent.parent / "lib" / "python3.15")])
    sock = str(tmp_path / "k" / "k.sock")
    one = BrigJail(BrigConfig(), Host(), platform="linux", interpreters=(str(link),))
    compiled, _ = one.compile(str(tmp_path / "j"), sock, str(project), ())
    denies = compiled.spec.fs.write_denies
    assert _denied(
        compiled.spec, str(file.resolve())
    )  # the interpreter, which the venv's links and `python3` lead to
    assert _denied(compiled.spec, str(venv / "bin" / "python")) and _denied(
        compiled.spec, str(file.parent.parent / "lib" / "python3.15" / "os.py")
    )  # the venv's links and the standard library: held already
    assert str(link) not in denies and str(link.parent) in denies  # the link's entry: held by its directory
    assert compiled.supervisor.interpreter == str(link)  # which makes it a Python the jail holds
    held = BrigJail(BrigConfig(), Host(), platform="linux", interpreters=(str(file),))
    assert held.compile(str(tmp_path / "j"), sock, str(project), ())[0].supervisor.interpreter == str(file)


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
            endpoint="/tmp/k/k.sock",
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
    assert not set(in_the_home) & set(denies(f"{_HOME}/work/app").fs.write_denies)  # the usual case
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


def test_a_jail_denies_the_directory_of_each_link_from_the_interpreter_bh_02_runs_on_to_its_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compile walks the links from `sys.executable` (and the base's `bin/python3`) to the file,
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
    sock = str(tmp_path / "k" / "k.sock")
    one = BrigJail(BrigConfig(), Host(), platform="linux", interpreters=(str(chain[-1]),))
    compiled, _ = one.compile(str(tmp_path / "j"), sock, str(project), ())
    assert {str(link.parent) for link in chain} == {
        str(venv / "bin"),
        str(file.parent),
        str(file.parent.parent.parent),
    }
    for link in chain:
        assert _denied(compiled.spec, str(link.parent / "planted")), link  # nothing can be put beside a link
        assert _denied(compiled.spec, str(link)), link
    assert _denied(compiled.spec, str(file))
    assert not _denied(compiled.spec, str(own / "python")) and not _denied(compiled.spec, str(own / "pip"))
    assert not _denied(compiled.spec, str(project.resolve() / "notes.md"))
    # the base's `python3` link is held by its directory now, so the supervisor may run under it
    assert compiled.supervisor.interpreter == str(chain[-1])


def test_the_walk_to_the_interpreter_follows_relative_links_and_dots_and_ends_at_a_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pyenv and Homebrew write relative links, with `..` in them, and a link to a directory in the
    middle of a path: each is found in the directory that holds it, and only those on the way. A
    loop of links is no interpreter, and the compile does not wait on it."""
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
    module, sock = "runner_cordis_plugin.jail", str(tmp_path / "k" / "k.sock")
    monkeypatch.setattr(f"{module}.base_prefix", str(base))
    one = BrigJail(BrigConfig(), Host(), platform="linux", interpreters=())

    def compiled(executable: Path) -> Any:
        monkeypatch.setattr(f"{module}.host_executable", str(executable))
        return one.compile(str(tmp_path / "j"), sock, str(project), ())[0].spec

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
    workspace itself, whose `local.env` an input must not read."""
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
        endpoint="/tmp/k/k.sock",
        scratch="/tmp/j/tmp",
        home="/home/me",
        config=BrigConfig(),
        layers=(),
        host=(),
        code=_CODE,
    )
    linux = allowlisted(policy, readable)
    read = linux.fs.read_allows  # brig keeps a tree once: one under another (`/opt/py`) is that one
    assert all(any(c == r or c.startswith(r + "/") for r in read) for c in _CODE), read
    assert not any(c == w or c.startswith(w + "/") for c in _CODE for w in linux.fs.write_allows)
    # and the row's jail compiles them in: bound read-only, as they are on the host
    package = tmp_path / "src" / "cordis"
    package.mkdir(parents=True)
    project = tmp_path / "project"
    project.mkdir()
    jail = BrigJail(BrigConfig(), Host(code=(str(package),)), platform="linux")
    compiled, _ = jail.compile(str(tmp_path / "j"), str(tmp_path / "k" / "k.sock"), str(project), ())
    assert str(package) in compiled.spec.fs.read_allows
    argv = compiled.wrap(("w",))
    at = argv.index(str(package))
    assert argv[at - 1] == "--ro-bind" and argv[at + 1] == str(package)


def test_allow_takes_names_off_brig_s_self_modification_list_and_only_those() -> None:
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
        argv=["/w/.venv/bin/python", "-I", "/w/src/python_cordis_plugin/worker.py", "/tmp/k/k.sock"],
        interpreter=("/opt/py", "/w/.venv"),
        system=SYSTEM_READABLE,
    )
    assert readable[: len(SYSTEM_READABLE)] == SYSTEM_READABLE
    assert {"/opt/py", "/w/.venv", "/w/.venv/bin", "/w/src/python_cordis_plugin"} <= set(readable)
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
    assert free.startswith("Nothing holds /w/local.env until something starts in the runner again")
    assert "`/restart model`" in free and "stays held" not in free
    still = released_for([], ["/w/local.env"])
    assert still.startswith("/w/local.env stays held") and "/release again" in still
    assert released_for([], []) == ""
    running = released_for([], [], running=True)  # an owner did not stop its own program
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
        if not group_alive(group):
            return True
        await asyncio.sleep(0.02)
    return False


def _recorded_group(tmp_path: Path) -> int:
    """The process group of the one running jail recorded under `tmp_path`'s state directory."""
    (record,) = (tmp_path / "state" / "bh-02" / "jails").iterdir()
    group = recorded_group(record.read_text())
    assert group is not None
    return group


def _holds_pid_1(group: int) -> bool:
    """Whether a process of `group` is PID 1 of a pid namespace of its own (`NSpid` ends in 1):
    a jail's instance, the supervisor's group, and not the group of a program in it."""
    table = subprocess.run(["/bin/ps", "-Ao", "pid=,pgid="], capture_output=True, text=True, check=True)
    for line in table.stdout.splitlines():
        pid, _, pgid = line.strip().partition(" ")  # ps pads a short pid with spaces
        if pgid.strip() != str(group):
            continue
        with contextlib.suppress(OSError):
            for status in Path(f"/proc/{pid}/status").read_text().splitlines():
                if status.startswith("NSpid:"):
                    ids = status.split()[1:]
                    if len(ids) > 1 and ids[-1] == "1":
                        return True
    return False


def _jail_group(tmp_path: Path) -> int:
    """The group the one running bubblewrap jail's record names, which is the jail itself: the
    process group that holds PID 1 of its namespaces (`Jail.instance_group`), so that it is gone
    means the jail is, whatever its programs started in a session of their own, and not that a
    program's own group ended."""
    group = _recorded_group(tmp_path)
    assert _holds_pid_1(group), f"the record names group {group}, which holds no PID 1: not a jail's"
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
    one = BrigJail(
        BrigConfig(),
        Host(credentials=(str(absent),), secrets=(str(absent),)),
        lock=str(tmp_path / "jails.lock"),
    )

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
        group = _jail_group(tmp_path)
        (project / "saved.tmp").write_text("NEW=1\n")
        (project / "saved.tmp").replace(secret)  # an editor's save
        assert await _gone(group)  # the jail ended itself
        assert str(secret) in started.ended() and "the next one holds it again" in started.ended()
    finally:
        await started.stop()
    started = await jailed()
    try:
        group = _jail_group(tmp_path)
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


_LISTEN_WITH_A_SESSION_OF_ITS_OWN = """
import socket, subprocess, sys, time
subprocess.Popen(["/bin/sleep", sys.argv[2]], start_new_session=True)
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
time.sleep(600)
"""


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
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    absent = project / "pkg" / "local.env"
    marker = f"{uuid.uuid4().int % 10**9 + 10**9}.{uuid.uuid4().int % 10**6:06d}"
    one = BrigJail(
        BrigConfig(),
        Host(credentials=(str(absent),), secrets=(str(absent),)),
        lock=str(tmp_path / "jails.lock"),
    )
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_WITH_A_SESSION_OF_ITS_OWN, endpoint, marker]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
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
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    absent, stamp = project / "pkg" / "local.env", project / "stamp"
    one = BrigJail(
        BrigConfig(),
        Host(credentials=(str(absent),), secrets=(str(absent),)),
        lock=str(tmp_path / "jails.lock"),
    )
    endpoint = _endpoint()
    argv = [sys.executable, "-I", "-c", _HOSTILE_IGNORING_SIGTERM, endpoint, str(absent), str(stamp)]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
    try:
        assert await _until(stamp.exists, 5.0), "CONTROL failed: the second program never ran"
        first = stamp.read_text()
        await asyncio.sleep(0.2)
        assert stamp.read_text() != first and absent.is_dir() and started.ended() == "", "CONTROL failed"
        group = _jail_group(tmp_path)
        lifted_at = time.time()
        began = time.monotonic()
        absent.rmdir()  # the host undoes a mount the jail holds
        assert await _gone(group, within=5.0), "the jail outlived the tripwire by 5 s"
        survived = time.monotonic() - began
        assert survived < 1.0, (
            f"the jail survived the tripwire for {survived:.2f} s (a SIGTERM's grace is 2 s)"
        )
        last = float(stamp.read_text() or "0")
        await asyncio.sleep(0.5)
        assert float(stamp.read_text() or "0") == last, "the program in a session of its own kept running"
        assert last - lifted_at < 1.0
        assert str(absent) in started.ended() and "did not complete" not in started.ended()
    finally:
        await started.stop()
        if absent.is_file():  # what the one that got in left on the host, for the next test's sake
            absent.unlink()


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


async def test_the_sweep_leaves_a_jail_a_server_holds_after_the_program_that_started_it_ended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model's code starts a server in a session of its own and the program ends: the jail
    does not, because the server is in it. Its record names the jail (the instance's group), not
    the program's, so a later bh-02's sweep finds the jail running and leaves the placeholders it
    holds. The record named the program's own group before, which is gone by then, and the sweep
    removed the placeholders from under a running jail, detaching the mounts that hold them.
    (The first jail's lock is another file here: the sweep runs when no running jail's bh-02 is
    left to hold the lock, so its bh-02 is the one that is gone.)"""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    records = tmp_path / "state" / "bh-02" / "jails"
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "one.lock"))
    endpoint, ending = _endpoint(), project / "ending"
    argv = [sys.executable, "-I", "-c", _LISTEN_LEAVE_A_SERVER_AND_END, endpoint, str(ending)]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
    try:
        group = _jail_group(tmp_path)
        (record,) = records.iterdir()
        held = project / ".claude"
        assert held.is_dir() and await _until(ending.exists, 10.0), "CONTROL failed: the program never ran"
        assert await _until(lambda: _nothing_listens(endpoint), 10.0), "the program did not end"
        assert group_alive(group), "the jail ended with its program: CONTROL failed, nothing is left to hold"
        other = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "other.lock"))
        endpoint_2 = _endpoint()
        argv_2 = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint_2, str(tmp_path / "elsewhere")]
        await (await other.start(argv_2, cwd=str(project), endpoint=endpoint_2)).stop()  # it swept
        assert held.is_dir() and record.exists(), "the sweep removed what a running jail holds"
    finally:
        await started.stop()
    assert not (project / ".claude").exists() and not list(records.iterdir())  # now it is gone


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
        return await BrigJail(BrigConfig(), Host()).start(argv, cwd=str(project), endpoint=endpoint)

    started = await jailed()
    try:
        await asyncio.sleep(0.5)
        assert "planted" not in config.read_text() and started.ended() == ""  # held
        group = _jail_group(tmp_path)
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
    made = [("/w/.git/hooks", "12:1700000000000000000"), ("/w/.git", "mark:bh-j-1")]
    assert recorded(record_text(made)) == made
    assert recorded("not json") == [] and recorded('{"made": 3}') == []  # a broken record names none
    damaged = '{"made": [["/w/a", null], ["/w/b", 7], ["/w/c", "mark:bh-j-1"]]}'
    assert recorded(damaged) == [("/w/c", "mark:bh-j-1")]  # an entry with no way to know it names none


def test_only_a_placeholder_still_as_the_jail_made_it_is_removed(tmp_path: Path) -> None:
    """Empty and unchanged: removed, deepest first. One the person put a file in, one they
    replaced with a directory of their own (even on the same inode), one the person made at a
    path recorded by its mark (it carries none) and one already gone are kept or passed over."""
    ours, filled, theirs, made_since = (tmp_path / n for n in ("ours", "filled", "theirs", "made_since"))
    for path in (ours, filled, theirs, made_since):
        path.mkdir(parents=True)
    made = [(str(p), identity(p.stat())) for p in (ours, filled, theirs)]
    made += [(str(made_since), "mark:bh-j-1"), (str(tmp_path / "gone"), "mark:bh-j-1")]
    (filled / "mine.txt").write_text("x")
    theirs.rmdir()
    time.sleep(0.05)  # the person's own comes later: a later change time, on the kernel's clock tick
    theirs.mkdir()
    remove_placeholders(made)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["filled", "made_since", "theirs"]


def test_a_placeholder_is_known_by_the_jail_s_mark_else_by_its_identity() -> None:
    assert still_made("mark:bh-j-1", "1:2", "bh-j-1") and not still_made("mark:bh-j-1", "1:2", None)
    assert not still_made("mark:bh-j-1", "1:2", "bh-j-2")  # another jail's
    assert still_made("1:2", "1:2", None) and not still_made("1:2", "1:3", None)


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


class _Plain:
    """What brig's `Jail.create` returns, for a jail whose program runs as a plain process: there
    is no bubblewrap, so nothing is mounted, and what is tested is the jail's own work around it
    (its placeholders, record, lock, tripwire, facts and release). Its one `start` puts the
    program in a session of its own, as brig's is, so its process group is what the jail and its
    tripwire end."""

    def __init__(self, jail: Any) -> None:
        del jail
        self._process: subprocess.Popen[bytes] | None = None

    def start(self, argv: Sequence[str], *, cwd: str, **rest: object) -> SimpleNamespace:
        self._process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, start_new_session=True)
        # reaped as it ends, however it ends (the tripwire kills its group), so a group that
        # ended is gone and not a zombie that `os.killpg(group, 0)` still finds
        threading.Thread(target=self._process.wait, daemon=True).start()
        return SimpleNamespace(pid=self._process.pid, stderr_path="", interrupt=self._interrupt)

    def _interrupt(self) -> bool:
        assert self._process is not None
        with contextlib.suppress(ProcessLookupError):
            os.killpg(self._process.pid, signal.SIGINT)
            return True
        return False

    instance_group = None  # no supervisor: the program's own group is all there is

    def destroy(self, *, grace: float = 2.0) -> Any:
        del grace  # SIGKILL whatever it is
        if self._process is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._process.pid, signal.SIGKILL)
            self._process.wait()
        return SimpleNamespace(items=())  # every item ended


@pytest.fixture
def _plain_launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A Linux confined runner's jail whose program is launched plainly (`_Plain`): no bubblewrap needed,
    nor allowed to fail as it does where it can't make namespaces. Linux only: the tripwire is
    inotify's."""
    if sys.platform != "linux":
        pytest.skip("the jail's tripwire is inotify's: Linux only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def create(jail: Any, **rest: object) -> _Plain:
        return _Plain(jail)

    monkeypatch.setattr("brig.run.Jail.create", create)
    # the jail refuses to start without bubblewrap installed; the package's `jail` is the row
    monkeypatch.setattr(sys.modules["runner_cordis_plugin.jail"], "DEFAULT_BWRAP_PATH", sys.executable)


def _endpoint() -> str:
    """A socket path short enough for a Unix socket, in a directory of its own."""
    return str(Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"), "k.sock"))


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


@pytest.mark.usefixtures("_plain_launch")
async def test_each_start_keeps_what_it_is_whatever_the_jail_starts_after_it(tmp_path: Path) -> None:
    """The runner starts two programs, the Python process and the extensions process, each
    from a command of its own. What a start is (the trees its program reads, which name the
    program's own directory; the roots it writes; its notice and grades) is that start's: the
    second start replaces none of the first's, so the Python process's notice never names the
    extensions' worker's trees. The jail's own grades are what was known before either."""
    project = tmp_path / "project"
    project.mkdir()
    credential = project / "local.env"  # where bh-02 looks for its credential, absent: held
    for name in ("python", "extensions"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "worker.py").write_text(_LISTEN)
    one = BrigJail(BrigConfig(), Host(credentials=(str(credential),), secrets=(str(credential),)))
    before = dict(one.report())
    started = []
    try:
        for name in ("python", "extensions"):
            endpoint = _endpoint()
            argv = [sys.executable, "-I", str(tmp_path / name / "worker.py"), endpoint]
            started.append(await one.start(argv, cwd=str(project), endpoint=endpoint))
        python_process, extensions = started
        assert str(tmp_path / "python") in python_process.reads(), python_process.reads()
        assert (
            str(tmp_path / "extensions") not in python_process.reads()
        )  # the second start's, not the first's
        assert str(tmp_path / "extensions") in extensions.reads()
        assert python_process.writes() == extensions.writes() == (str(project.resolve()),)
        assert (
            str(credential) in python_process.notice() and python_process.report()["fs_read"] == "best_effort"
        )
        assert one.report() == before
    finally:
        for each in started:
            await each.stop()


def _stops(started: Any) -> Any:
    """An owner's stop for `/release` (`Runner.on_release`): stop its own program, say nothing."""

    async def stop() -> str:
        await started.stop()
        return ""

    return stop


@pytest.mark.usefixtures("_plain_launch")
async def test_release_frees_what_the_programs_held_once_each_owner_stopped_its_own(tmp_path: Path) -> None:
    """The runner starts the Python process and the extensions' worker, and both jails hold the
    absent `local.env` where bh-02 looks for its credential (and take the shared jail lock). On
    `/release` each owner stops its own program (`on_release`), then the jail sweeps: the
    placeholder is removed, the path is free, and it says so. The runner stays released, so the
    extensions' worker waits, until the next start (the next input's Python process)."""
    project = tmp_path / "project"
    project.mkdir()
    credential = project / "local.env"
    runner = Runner(
        BrigJail(
            BrigConfig(),
            Host(credentials=(str(credential),), secrets=(str(credential),)),
            lock=str(tmp_path / "jails.lock"),
        )
    )
    started = []
    for _ in ("python", "extensions"):
        endpoint = _endpoint()
        argv = [sys.executable, "-I", "-c", _LISTEN, endpoint]
        started.append(await runner.start(argv, cwd=str(project), endpoint=endpoint))
        runner.on_release(_stops(started[-1]))
    try:
        records = tmp_path / "state" / "bh-02" / "jails"
        groups = [recorded_group(record.read_text()) for record in sorted(records.iterdir())]
        assert credential.is_dir() and len(groups) == 2 and None not in groups
        said = await runner.release()
        assert said.startswith(f"Nothing holds {credential}"), said
        assert "stays held" not in said and "still runs" not in said
        assert not credential.exists() and list(records.iterdir()) == []
        for group in groups:
            assert group is not None and await _gone(group)
        assert runner.released()
        endpoint = _endpoint()
        again = await runner.start(
            [sys.executable, "-I", "-c", _LISTEN, endpoint], cwd=str(project), endpoint=endpoint
        )
        try:
            assert not runner.released() and credential.is_dir()  # the next input's jail holds it again
        finally:
            await again.stop()
    finally:
        for each in started:
            await each.stop()  # again: nothing more happens


@pytest.mark.usefixtures("_plain_launch")
async def test_release_never_stops_a_program_its_owner_did_not_and_says_it_still_holds(
    tmp_path: Path,
) -> None:
    """The runner stops no row's program: one whose owner registered no stop keeps running, its
    jail keeps the path held, and `/release` says so, naming the way out."""
    project = tmp_path / "project"
    project.mkdir()
    credential = project / "local.env"
    runner = Runner(
        BrigJail(
            BrigConfig(),
            Host(credentials=(str(credential),), secrets=(str(credential),)),
            lock=str(tmp_path / "jails.lock"),
        )
    )
    endpoint = _endpoint()
    kept = await runner.start(
        [sys.executable, "-I", "-c", _LISTEN, endpoint], cwd=str(project), endpoint=endpoint
    )
    try:
        said = await runner.release()
        assert "still runs" in said and "/restart" in said, said
        assert credential.is_dir() and kept.ended() == ""
    finally:
        await kept.stop()


_HOLDS_THE_LOCK_SHARED = """
import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_SH)
print("held", flush=True)
time.sleep(120)
"""


@pytest.mark.usefixtures("_plain_launch")
async def test_release_keeps_what_another_session_holds_on_the_shared_lock_until_it_is_gone(
    tmp_path: Path,
) -> None:
    """Another bh-02 session of the person's runs a jail: it holds the jail lock shared, from a
    process of its own. A program stopped here can't remove the placeholder while that hold
    stands, and `/release` says the path stays held by another session. Once that session is
    gone, the next `/release` frees it."""
    project = tmp_path / "project"
    project.mkdir()
    credential = project / "local.env"
    lock = str(tmp_path / "jails.lock")
    runner = Runner(
        BrigJail(BrigConfig(), Host(credentials=(str(credential),), secrets=(str(credential),)), lock=lock)
    )
    endpoint = _endpoint()
    started = await runner.start(
        [sys.executable, "-I", "-c", _LISTEN, endpoint], cwd=str(project), endpoint=endpoint
    )
    other = subprocess.Popen(
        [sys.executable, "-I", "-c", _HOLDS_THE_LOCK_SHARED, lock], stdout=subprocess.PIPE, text=True
    )
    try:
        assert other.stdout is not None and other.stdout.readline() == "held\n"
        await started.stop()
        said = await runner.release()
        assert credential.is_dir(), said
        assert f"{credential} stays held" in said and "another bh-02 session" in said, said
        other.kill()
        other.wait()
        said = await runner.release()
        assert not credential.exists() and said.startswith(f"Nothing holds {credential}"), said
    finally:
        other.kill()
        other.wait()
        await started.stop()


@pytest.mark.usefixtures("_plain_launch")
async def test_release_waits_for_a_start_under_way_and_says_it_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start under way when `release` begins (the extensions' worker loading as the person
    types `/release`) is waited for, so no placeholder of its is swept from under it; its owner
    had nothing to stop when asked, so `/release` says a program still runs."""
    project = tmp_path / "project"
    project.mkdir()
    launched: list[_Plain] = []

    def slow(jail: Any, **rest: object) -> _Plain:
        time.sleep(0.3)
        launched.append(_Plain(jail))
        return launched[-1]

    monkeypatch.setattr("brig.run.Jail.create", slow)
    runner = Runner(BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock")))
    endpoint = _endpoint()
    argv = [sys.executable, "-I", "-c", _LISTEN, endpoint]
    starting = asyncio.ensure_future(runner.start(argv, cwd=str(project), endpoint=endpoint))
    await asyncio.sleep(0.1)  # launching
    assert not launched and (project / ".envrc").is_dir()
    said = await runner.release()
    started = await starting
    try:
        assert "still runs" in said, said
        assert (project / ".envrc").is_dir()  # still its jail's
    finally:
        await started.stop()
    assert list(project.iterdir()) == []  # its placeholders went with it


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
    started = await BrigJail(BrigConfig(), Host()).start(argv, cwd=str(project), endpoint=endpoint)
    try:
        group = _recorded_group(tmp_path)
        for _ in range(250):
            if done.exists():
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.3)  # the tripwire's thread has read the creation, if it watches it
        assert created.read_text() == "MINE=1\n"
        assert started.ended() == "", started.ended()
        assert group_alive(group)  # still running
        (project / ".envrc").rmdir()  # a placeholder the jail holds, removed on the host
        assert await _gone(group)
        assert str(project / ".envrc") in started.ended()
    finally:
        await started.stop()


# A bh-02 that crashes once its jailed Python process is up: no `stop`, so nothing it made is removed.
# Its worker listens for a moment and exits, as an orphaned Python process with no host would be ended.
_CRASH = """
import asyncio, os, sys, tempfile
from pathlib import Path
from runner_cordis_plugin import BrigConfig, BrigJail

class Host:
    paths, credentials, secrets, trusted, code, auto_memory = (), (), (), (), (), ""

async def main():
    sock = str(Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"), "k.sock"))
    worker = (
        "import socket, sys, time; s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); "
        "s.listen(1); time.sleep(2)"
    )
    argv = [sys.executable, "-I", "-c", worker, sock]
    await BrigJail(BrigConfig(), Host()).start(argv, cwd=sys.argv[1], endpoint=sock)
    os._exit(9)

asyncio.run(main())
"""


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
    paths, credentials, secrets, trusted, code, auto_memory = (), (), (), (), (), ""

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
        assert not group_alive(group)  # and the whole jail
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(group, signal.SIGKILL)
    assert (project / ".claude").is_dir() and not list((project / ".claude").iterdir())
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
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
        one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
        sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
        endpoint = str(sock_dir / "k.sock")
        argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
        await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()
        assert held.is_dir() and record.exists()
    finally:
        living.kill()
        await living.wait()
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()
    assert not held.exists() and not record.exists()  # its group gone, so are they


_PR_SET_CHILD_SUBREAPER = 36


@pytest.fixture
def non_reaping_init() -> Iterator[list[int]]:
    """Make this process the init of every orphan beneath it and never reap them: the shape of a
    container whose PID 1 does not reap, under any real PID 1 (`PR_SET_CHILD_SUBREAPER`). The test
    adds the pids it planted to the yielded list; only those are reaped at the end."""
    if sys.platform != "linux":
        pytest.skip("PR_SET_CHILD_SUBREAPER is Linux's prctl; no other kernel has it")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        pytest.skip("PR_SET_CHILD_SUBREAPER is unavailable here")
    planted: list[int] = []
    try:
        yield planted
    finally:
        libc.prctl(_PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0)
        for pid in planted:
            with contextlib.suppress(ChildProcessError):
                os.waitpid(pid, os.WNOHANG)


def _group_states(group: int) -> dict[int, str]:
    """Each member of process group `group` by pid, with its process state."""
    table = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid=,stat="], capture_output=True, text=True, check=True
    ).stdout
    rows = [line.split() for line in table.splitlines() if line.strip()]
    return {int(pid): stat for pid, pgid, stat in rows if int(pgid) == group}


async def test_the_sweep_removes_what_a_jail_left_whose_group_is_only_zombies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, non_reaping_init: list[int]
) -> None:
    """Where PID 1 does not reap, a dead jail's process group stays in the table as zombies for
    good, and `os.killpg(group, 0)` still finds it. Nothing of it runs, so the sweep counts it
    gone: it removes the record's placeholders and the record, and release does not say
    another session holds them. The group here is a program that started a child and neither
    waits for it, killed: both are zombies, the child's orphaned to this process as init."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    held = project / ".claude"
    held.mkdir(parents=True)
    records = tmp_path / "state" / "bh-02" / "jails"
    records.mkdir(parents=True)
    # keeps the `Popen`: a dropped one reaps its child in `__del__` once it has exited, which on a loaded
    # machine it has by then, and no zombie is left
    body = "import subprocess, time; zombie = subprocess.Popen(['true']); time.sleep(100)"
    leader = subprocess.Popen([sys.executable, "-c", body], start_new_session=True)
    non_reaping_init.append(leader.pid)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and len(_group_states(leader.pid)) < 2:
        time.sleep(0.05)
    assert len(_group_states(leader.pid)) >= 2, "CONTROL failed: the child never started"
    os.killpg(leader.pid, signal.SIGKILL)
    while time.monotonic() < deadline and any(
        not state.startswith("Z") for state in _group_states(leader.pid).values()
    ):
        time.sleep(0.05)
    states = _group_states(leader.pid)
    non_reaping_init.extend(states)
    assert states and all(state.startswith("Z") for state in states.values()), states
    os.killpg(leader.pid, 0)  # CONTROL: the group is still found, by its zombies
    record = records / "bh-j-zombies.json"
    record.write_text(record_text([(str(held), identity(held.stat()))], leader.pid))
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()
    assert not held.exists() and not record.exists()  # its group is zombies only, so gone


# A bh-02 that crashes the moment it would start bubblewrap: what its jail holds on the host is
# there, and nothing of it was mounted yet.
_CRASH_AT_LAUNCH = """
import os, sys, tempfile
from pathlib import Path
import asyncio
from brig.run import Jail
from runner_cordis_plugin import BrigConfig, BrigJail

class Host:
    paths, credentials, secrets, trusted, code, auto_memory = (), (), (), (), (), ""

def crash(*args, **kwargs):
    os._exit(9)

Jail.create = crash
sock = str(Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"), "k.sock"))
argv = [sys.executable, "-c", "pass"]
asyncio.run(BrigJail(BrigConfig(), Host()).start(argv, cwd=sys.argv[1], endpoint=sock))
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
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()
    assert list(project.iterdir()) == [] and not record.exists()


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
    endpoint = _endpoint()
    memories = (str(memory / "MEMORY.md"), str(beside / "MEMORY.md"))
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_REMEMBER, endpoint, *memories, str(project / "done")]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
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
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
    endpoint, said, beside = _endpoint(), project / "said", project / "beside"
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_REACH_FOR_THE_PYTHON, endpoint]
    argv += [str(file), str(link), str(beside), str(said)]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
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
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
    endpoint, said, beside = _endpoint(), project / "said", project / "beside"
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_CHANGE_THE_LINKS, endpoint]
    argv += [*map(str, chain), str(beside), str(said)]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
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
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
    endpoint, said = _endpoint(), project / "said"
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_RENAME_THE_DIRECTORIES, endpoint]
    argv += [*map(str, dirs), str(said)]
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
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


async def test_a_jail_that_fails_to_launch_leaves_nothing_on_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its placeholders are made before bubblewrap starts, so a launch that fails (or is
    cancelled) removes them again, with its record, as a stop would."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()

    def refused(*args: object, **kwargs: object) -> None:
        raise RuntimeError("no launch today")

    monkeypatch.setattr("brig.run.Jail.create", refused)
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    with pytest.raises(RuntimeError, match="no launch today"):
        await BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock")).start(
            [sys.executable, "-c", "pass"], cwd=str(project), endpoint=str(sock_dir / "k.sock")
        )
    assert list(project.iterdir()) == []
    assert list((tmp_path / "state" / "bh-02" / "jails").iterdir()) == []


# A bh-02 whose jail has a helper brig's `Jail.create` starts and keeps for the jail's life (as an
# egress proxy would be), and, for argv[3] "refused", a wrap that is not a pure argv prefix, so
# brig refuses the jail's first start; "control": a prefix wrap, so it starts. It says
# "refused: <why>" or "started", waits for a line, stops what started (saying "stopped"), and
# waits for another. argv: the project, a token (the helper's command line holds "keeper-" and
# it, which this program's own does not), "refused" or "control", then the jail lock (a tmp path:
# another bh-02 session of the machine must not hold it out from under the test).
_REFUSED_FIRST_START = """
import asyncio, dataclasses, sys, tempfile
from pathlib import Path
from brig.mech import Helper, HelperLifetime
from brig.run import ExecWrapNotAPrefix, Jail
from runner_cordis_plugin import BrigConfig, BrigJail

class Host:
    paths, credentials, secrets, trusted, code, auto_memory = (), (), (), (), (), ""

project, token, how, lock = sys.argv[1:5]
helper = Helper(
    name="keeper",
    argv=("/bin/sh", "-c", f": keeper-{token}; sleep 100"),
    lifetime=HelperLifetime.JAIL_LIFETIME,
)
real = Jail.create

def create(compiled, **rest):
    wrap = (lambda argv: (*argv, "--appended")) if how == "refused" else (lambda argv: tuple(argv))
    # No bubblewrap in either, so no supervisor either: its program is bound by bubblewrap
    # (brig's decision-190), and a start is brig's own to refuse here (decision-181).
    return real(
        dataclasses.replace(compiled, wrap=wrap, supervisor=None, helpers=(*compiled.helpers, helper)),
        **rest,
    )

Jail.create = create

async def main():
    sock = str(Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"), "k.sock"))
    worker = (
        "import socket, sys, time; s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); "
        "s.listen(1); time.sleep(100)"
    )
    started = None
    try:
        started = await BrigJail(BrigConfig(), Host(), lock=lock).start(
            [sys.executable, "-I", "-c", worker, sock], cwd=project, endpoint=sock
        )
    except ExecWrapNotAPrefix as error:
        print("refused:", str(error).replace("\\n", " "), flush=True)
    else:
        print("started", flush=True)
    sys.stdin.readline()
    if started is not None:
        await started.stop()
        print("stopped", flush=True)
    sys.stdin.readline()

asyncio.run(main())
"""


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


@pytest.mark.parametrize("how", ["refused", "control"])
async def test_a_refused_first_start_destroys_the_jail_so_nothing_it_made_outlives_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    """brig's refused `Jail.start` changes nothing: the jail it was refused in is its creator's.
    The runner creates the jail (whose helper `Jail.create` starts and keeps for the jail's
    life), its first start is refused (a wrap that is not a pure prefix), and the runner
    destroys the jail before it says why: the helper is gone, and so are the placeholders and
    the record. The control (a prefix wrap): the same helper runs once the start returns, and
    goes with the stop, so the helper does start.

    Planted on 2026-10-12 (scratch copy of `jail.py`, restored by sha256): with `_launch`'s
    `jail.destroy()` removed, the refused case failed with the helper still running."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    token = uuid.uuid4().hex[:12]
    marker = f"keeper-{token}"  # the helper's, never the stand-in bh-02's own command line
    bh02 = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _REFUSED_FIRST_START,
        str(project),
        token,
        how,
        str(tmp_path / "jails.lock"),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    assert bh02.stdin is not None and bh02.stdout is not None
    seen: list[int] = []
    try:
        said = (await asyncio.wait_for(bh02.stdout.readline(), 30)).decode()
        if how == "refused":
            assert said.startswith("refused:") and "not a pure argv prefix" in said, said
            seen = _marked_groups(marker)
            assert seen == [], f"the helper outlived a refused first start: groups {seen}"
            assert list(project.iterdir()) == []
            assert list((tmp_path / "state" / "bh-02" / "jails").iterdir()) == []
        else:
            assert said == "started\n", said
            assert await _until(lambda: bool(_marked_groups(marker)), 5.0), "CONTROL failed: no helper ran"
            seen = _marked_groups(marker)
            bh02.stdin.write(b"\n")
            assert (await asyncio.wait_for(bh02.stdout.readline(), 30)) == b"stopped\n"
            assert await _until(lambda: not _marked_groups(marker), 5.0), _marked_groups(marker)
            assert list(project.iterdir()) == []
    finally:
        for group in {*seen, *_marked_groups(marker)}:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(group, signal.SIGKILL)
        bh02.stdin.write(b"\n\n")
        with contextlib.suppress(ConnectionError):
            await bh02.stdin.drain()
        await asyncio.wait_for(bh02.wait(), 30)


class _Refused:
    """What brig's `Jail.create` returns, for a jail whose first start is refused and whose
    `destroy` reports `ended` (a report's items) or, when it is an exception, raises it."""

    def __init__(self, ended: Any) -> None:
        self._ended = ended

    def start(self, argv: Sequence[str], **rest: object) -> None:
        raise RuntimeError("start refused today")

    def destroy(self) -> Any:
        if isinstance(self._ended, BaseException):
            raise self._ended
        return SimpleNamespace(items=self._ended)


@pytest.mark.parametrize("ended", ["failed", "raised"])
async def test_a_refused_start_s_error_crosses_with_what_ending_its_jail_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ended: str
) -> None:
    """The runner ends a jail whose first start brig refused; the start's error is what the
    caller sees, whatever the ending found: a helper it could not end ("failed") is named on
    it with brig's detail, and an ending that itself raised ("raised") is named too, never put
    in the start's place. Its placeholders and record go either way.

    Planted on 2026-10-12 (scratch copy of `jail.py`, restored by sha256): with `_launch`'s
    ending back to a bare `jail.destroy()`, "failed" had no note and "raised" let the ending's
    OSError cross in place of the start's error."""
    if sys.platform != "linux":
        pytest.skip("the placeholders are bubblewrap's: Linux only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(sys.modules["runner_cordis_plugin.jail"], "DEFAULT_BWRAP_PATH", sys.executable)
    failed = SimpleNamespace(
        kind="helper", identity="4242", outcome=SimpleNamespace(value="FAILED"), detail="EPERM"
    )
    outcome: Any = (failed,) if ended == "failed" else OSError("no ending today")
    monkeypatch.setattr("brig.run.Jail.create", lambda *args, **kwargs: _Refused(outcome))
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(RuntimeError, match="start refused today") as refused:
        await BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock")).start(
            [sys.executable, "-c", "pass"], cwd=str(project), endpoint=_endpoint()
        )
    notes = " ".join(getattr(refused.value, "__notes__", ()))
    if ended == "failed":
        assert "helper 4242 FAILED: EPERM" in notes and "kill -KILL -- -4242" in notes, notes
    else:
        assert "failed too" in notes and "no ending today" in notes, notes
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
        BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock")).start(
            argv, cwd=str(project), endpoint=endpoint
        )
    )
    await asyncio.sleep(0.1)
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    assert groups  # the start returned only once the launch had
    await asyncio.sleep(1.0)
    (group,) = groups
    assert not group_alive(group)
    assert list(project.iterdir()) == []
    assert list((tmp_path / "state" / "bh-02" / "jails").iterdir()) == []


async def test_a_record_with_unmarked_paths_removes_nothing_it_can_t_prove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record written before its placeholders were made (a crash between writing it and marking
    them, so each is known by the mark it would have carried): the person has since made an empty
    directory at one of its paths. It carries no mark, so the sweep can't tell it from a
    placeholder and leaves it, and the record goes."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    mine = project / "build"
    mine.mkdir(parents=True)  # the person's, empty
    records = tmp_path / "state" / "bh-02" / "jails"
    records.mkdir(parents=True)
    record = records / "bh-j-crashed.json"
    record.write_text(
        record_text([(str(mine), "mark:bh-j-crashed"), (str(project / "gone"), "mark:bh-j-crashed")])
    )
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
    sock_dir = Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"))
    endpoint = str(sock_dir / "k.sock")
    argv = [sys.executable, "-I", "-c", _LISTEN_THEN_WRITE, endpoint, str(tmp_path / "elsewhere")]
    await (await one.start(argv, cwd=str(project), endpoint=endpoint)).stop()
    assert mine.is_dir() and not record.exists()


def test_a_record_names_the_jail_s_process_group() -> None:
    text = record_text([("/w/.claude", "mark:bh-j-1")], 4242)
    assert recorded_group(text) == 4242 and recorded(text) == [("/w/.claude", "mark:bh-j-1")]
    assert recorded_group(record_text([("/w/.claude", "mark:bh-j-1")])) is None  # before bwrap started
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
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"))
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
    own `git init`. That works on the host while the Python process runs; inside the jail `.git` stays
    what it was held as, and the new repository outlives the jail."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    one = BrigJail(BrigConfig(), Host())
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
    with pytest.raises(RuntimeError, match=r"this is freebsd.*`runner:unconfined`"):
        stack_for("freebsd")
    assert BrigJail(BrigConfig(), Host(), platform="freebsd").report() == {}


def test_the_supervisor_runs_under_the_first_interpreter_the_jail_holds_whole() -> None:
    """brig checks only that the interpreter's spelling is under a root the Spec mounts, so the
    rest is this choice's: a link that leads out of the roots would dangle in the jail, and a
    jail whose PID 1 can't start is no jail. The roots are the Spec's read roots: read-only."""
    mounted = ("/usr", "/etc", "/opt/py")
    system = {"/usr/bin/python3": "/usr/bin/python3.13"}  # Debian's goes through /etc/alternatives
    own = {"/opt/py/bin/python3": "/opt/py/bin/python3.15"}
    assert supervisor_interpreter({**system, **own}, mounted) == "/usr/bin/python3"  # best first
    assert supervisor_interpreter(own, mounted) == "/opt/py/bin/python3"  # the system's is elsewhere
    nix = {"/nix/store/aa-python3/bin/python3": "/nix/store/aa-python3/bin/python3.15"}
    assert supervisor_interpreter({**nix, **own}, mounted) == "/opt/py/bin/python3"  # not mounted: skipped
    leads_out = {"/usr/bin/python3": "/nix/store/bb-python3/bin/python3.15"}  # mounted, its target is not
    assert supervisor_interpreter({**leads_out, **own}, mounted) == "/opt/py/bin/python3"
    beside = {"/opt/pyx/bin/python3": "/opt/pyx/bin/python3"}  # a sibling name is not under /opt/py
    assert supervisor_interpreter({**beside, **own}, mounted) == "/opt/py/bin/python3"
    assert supervisor_interpreter(own, ("/",)) == "/opt/py/bin/python3"  # everything is under /
    # none holds whole: brig's own default, which brig then refuses by name or fails to start
    assert supervisor_interpreter({}, mounted) == "/usr/bin/python3"
    assert supervisor_interpreter({**nix, **leads_out}, mounted) == "/usr/bin/python3"
    assert supervisor_interpreter({**nix}, ("/opt/py",)) == "/usr/bin/python3"


def test_the_supervisor_never_runs_under_a_python_an_input_can_write_unless_a_deny_holds_it() -> None:
    """bh-02's base interpreter lies under the project when the project is the home directory (a
    uv-managed Python under `~/.local`). An input could replace what runs as the jail's PID 1 there,
    so a candidate counts under a writable root only where a write deny holds it, its spelling and
    its target both: a sibling name does not hold it."""
    mounted = ("/usr", "/home/me")
    writable = ("/home/me",)
    base = {"/home/me/.local/py/bin/python3": "/home/me/.local/py/bin/python3.15"}
    assert supervisor_interpreter(base, mounted, writable=writable) == "/usr/bin/python3"
    assert (
        supervisor_interpreter(base, mounted, writable=writable, denied=("/home/me/.local/py",))
        == "/home/me/.local/py/bin/python3"
    )
    assert (
        supervisor_interpreter(base, mounted, writable=writable, denied=("/home/me/.local/p",))
        == "/usr/bin/python3"  # a sibling name is not under the deny
    )
    system = {"/usr/bin/python3": "/home/me/.local/py/bin/python3.15"}  # a link into the writable tree
    own = {"/opt/py/bin/python3": "/opt/py/bin/python3.15"}
    assert supervisor_interpreter({**system, **own}, (*mounted, "/opt/py"), writable=writable) == (
        "/opt/py/bin/python3"  # the target counts too
    )


def test_a_linux_host_looks_for_its_system_python_then_the_one_bh_02_runs_on() -> None:
    assert host_interpreters() == ("/usr/bin/python3", str(Path(sys.base_prefix, "bin", "python3")))


def _a_python_elsewhere(directory: Path) -> Path:
    """An interpreter at a path no host has one at: a link to the one running this, whose target
    the jail mounts (`sys.base_prefix`) and whose own directory only a command naming it does."""
    directory.mkdir()
    link = directory / "python3"
    link.symlink_to(Path(sys.executable).resolve())
    return link


def test_a_jail_compiles_its_supervisor_under_the_interpreter_the_host_has_and_it_mounts(
    tmp_path: Path,
) -> None:
    """The choice reaches brig (`strict_linux(python=...)`): the supervisor plan of the compiled
    jail names it. Where the host's own interpreter is not at a path the Spec mounts, the next is
    chosen, and with none at all brig's default, for brig to refuse or run."""
    link = _a_python_elsewhere(tmp_path / "pybin")
    project = tmp_path / "project"
    project.mkdir()
    sock = str(tmp_path / "k" / "k.sock")
    here = BrigJail(BrigConfig(), Host(), platform="linux", interpreters=(str(link),))
    naming = ["/usr/bin/env", str(link), "-I"]  # the command names the interpreter's directory
    assert here.compile(str(tmp_path / "j"), sock, str(project), naming)[0].supervisor.interpreter == str(
        link
    )
    assert here.compile(str(tmp_path / "j"), sock, str(project), ())[0].supervisor.interpreter == (
        "/usr/bin/python3"  # its directory is not mounted: the jail has no such interpreter
    )
    chosen = BrigJail(BrigConfig(), Host(), platform="linux", interpreters=("/nowhere/python3", str(link)))
    assert chosen.compile(str(tmp_path / "j"), sock, str(project), naming)[0].supervisor.interpreter == str(
        link
    )  # one that is not there is skipped


def test_a_jail_does_not_run_its_supervisor_under_a_python_in_its_project_unless_a_deny_holds_it(
    tmp_path: Path,
) -> None:
    """A Python in the project (where an input may write) is the PID 1 only where the policy denies
    writing it: the same interpreter, named by the command so its directory is mounted, is refused
    without the deny and chosen with one (`BrigConfig(deny=)`)."""
    project = tmp_path / "project"
    project.mkdir()
    link = _a_python_elsewhere(project / "py")
    sock = str(tmp_path / "k" / "k.sock")
    naming = ["/usr/bin/env", str(link), "-I"]  # mounted, so only the writable root decides
    bare = BrigJail(BrigConfig(), Host(), platform="linux", interpreters=(str(link),))
    assert bare.compile(str(tmp_path / "j"), sock, str(project), naming)[0].supervisor.interpreter == (
        "/usr/bin/python3"
    )
    denied = BrigJail(BrigConfig(deny=("py",)), Host(), platform="linux", interpreters=(str(link),))
    assert denied.compile(str(tmp_path / "j"), sock, str(project), naming)[0].supervisor.interpreter == (
        str(link)
    )


# Listens; once the jail has seen it listen, says so in argv[2] (renamed into place, so whole), and waits.
_LISTEN_THEN_SAY_SO = """
import os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
server.accept()
with open(sys.argv[2] + ".tmp", "w") as report:
    report.write("listening")
os.replace(sys.argv[2] + ".tmp", sys.argv[2])
time.sleep(60)
"""


def _commands_running(word: str) -> list[list[str]]:
    """The command line of each process on the host that has `word` in it, read from `/proc` as
    the host sees it: a process in a jail's pid namespace, or in one inside that, is in this table."""
    found: list[list[str]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            words = [w.decode(errors="replace") for w in (entry / "cmdline").read_bytes().split(b"\0") if w]
        except OSError:
            continue
        if word in words:
            found.append(words)
    return found


async def test_a_host_whose_python_is_not_at_the_usual_path_starts_a_confined_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real jail on a host whose only interpreter is elsewhere (a link, in a directory the
    command names): its PID 1, brig's supervisor, runs under that path, not under the default
    `/usr/bin/python3` brig would otherwise start it with. Read from the host's process table:
    the program, in namespaces of its own since TASK-0079.07, is no longer in the supervisor's
    pid namespace to read it from inside."""
    _needs_bwrap()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    link = _a_python_elsewhere(tmp_path / "pybin")
    project = tmp_path / "project"
    project.mkdir()
    said = project / "listening"
    endpoint = _endpoint()
    argv = [str(link), "-I", "-c", _LISTEN_THEN_SAY_SO, endpoint, str(said)]
    one = BrigJail(BrigConfig(), Host(), lock=str(tmp_path / "jails.lock"), interpreters=(str(link),))
    started = await one.start(argv, cwd=str(project), endpoint=endpoint)
    try:
        report = await _report(said, started)
        assert report == "listening", report
        supervisors = _commands_running("/.brig-supervisor.py")
        assert [str(link), "-I", "/.brig-supervisor.py"] in [words[:3] for words in supervisors]
    finally:
        await started.stop()


def test_a_host_whose_jail_mounts_no_interpreter_is_refused_with_what_a_person_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No `/usr` on the host (nothing of the system mounted but `/etc`), and the interpreter bh-02
    runs on elsewhere: nothing holds an interpreter, so the runner refuses before any program
    starts. The refusal is the runner's own, in a bh-02 user's terms (install python3, or
    `--no-jail`), and brig's `InterpreterNotMounted` is its cause, with brig's advice to an
    embedder left in the cause."""
    monkeypatch.setattr("runner_cordis_plugin.jail.SYSTEM_READABLE", ("/etc",))
    monkeypatch.setattr("runner_cordis_plugin.jail.base_prefix", "/opt/py")
    monkeypatch.setattr("runner_cordis_plugin.jail.prefix", "/opt/py")
    with pytest.raises(RuntimeError, match=r"runner:confined cannot start") as raised:
        BrigJail(BrigConfig(), Host(), platform="linux", interpreters=("/nowhere/python3",))
    said = str(raised.value)
    assert type(raised.value.__cause__).__name__ == "InterpreterNotMounted"
    assert "(/nowhere/python3) is one" in said  # the candidates looked for
    assert "(InterpreterNotMounted): /usr/bin/python3 is under no path the jail mounts" in said
    assert "Install python3" in said and "`runner:unconfined`" in said and "`bh-02 --no-jail`" in said
    assert "strict_linux" not in said and "read_allows" not in said, said  # brig's advice stays a cause


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
    jail = BrigJail(BrigConfig(), Host(), platform="linux")
    report = jail.report()
    assert report["fs_write"] == report["network"] == report["env"] == "enforced"

    compiled, graded = jail.compile(str(tmp_path / "j"), str(tmp_path / "k" / "k.sock"), str(project), ())
    detail = next(g.detail for axis, g in compiled.report.axes.items() if axis.value == "fs_read")
    assert graded["fs_read"] == "best_effort" and str(secret.resolve()) in detail
    assert str(secret.resolve()) not in compiled.wrap(("w",))  # the project's own: nothing made
    looked = BrigJail(BrigConfig(), Host(credentials=(str(secret.resolve()),)), platform="linux")
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


async def test_on_linux_the_tripwire_ends_what_it_was_armed_with_when_a_held_file_is_renamed_over(
    tmp_path: Path,
) -> None:
    """The shell, without bubblewrap: a held file renamed over calls what the wire was armed with
    (here, a kill of a process group) and says why; a file beside it changing does nothing."""
    if sys.platform != "linux":
        pytest.skip("inotify is Linux's")
    held = tmp_path / "config"
    held.write_text("a")
    victim = subprocess.Popen(["sleep", "30"], start_new_session=True)
    wire = Tripwire([str(held)])

    def end() -> str:
        os.killpg(victim.pid, signal.SIGKILL)
        return ""

    wire.arm(end, fallback=lambda: pytest.fail("the fallback is for a teardown that raised"))
    try:
        (tmp_path / "beside").write_text("b")  # not held: nothing happens
        await asyncio.sleep(0.1)
        assert victim.poll() is None and wire.tripped == ""
        (tmp_path / "config.new").write_text("c")
        (tmp_path / "config.new").replace(held)
        assert await asyncio.to_thread(victim.wait, 2) == -signal.SIGKILL
        assert str(held) in wire.tripped and "did not complete" not in wire.tripped
    finally:
        wire.stop()
        victim.kill()


@pytest.mark.parametrize("how", ["raised", "failed"])
async def test_a_teardown_that_did_not_end_the_jail_says_so_and_one_that_raised_is_followed_by_a_kill(
    tmp_path: Path, how: str
) -> None:
    """A teardown that raised must not leave the jail running with no trace: the wire kills the
    jail's group directly (`fallback`) and `tripped` says brig's teardown raised and what the kill
    does not reach. One that returned what it could not end (a `FAILED` item) is not killed again
    (brig has just sent `SIGKILL` and verified), and `tripped` names it. Control: a teardown that
    ended everything adds nothing."""
    if sys.platform != "linux":
        pytest.skip("inotify is Linux's")
    held = tmp_path / "config"
    held.write_text("a")
    victim = subprocess.Popen(["sleep", "30"], start_new_session=True)
    wire = Tripwire([str(held)])
    killed: list[str] = []

    def end() -> str:
        if how == "raised":
            raise OSError("no teardown today")
        return "workload_group 4242: still had members"

    wire.arm(end, fallback=lambda: (killed.append("group"), os.killpg(victim.pid, signal.SIGKILL)))
    try:
        (tmp_path / "config.new").write_text("c")
        (tmp_path / "config.new").replace(held)
        if how == "raised":
            assert await asyncio.to_thread(victim.wait, 2) == -signal.SIGKILL
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not wire.tripped.count("did not complete"):
            await asyncio.sleep(0.02)
        assert "did not complete" in wire.tripped and str(held) in wire.tripped, wire.tripped
        if how == "raised":
            assert killed == ["group"] and "no teardown today" in wire.tripped
        else:
            assert killed == [] and "workload_group 4242: still had members" in wire.tripped
            assert victim.poll() is None
    finally:
        wire.stop()
        victim.kill()


def test_what_a_teardown_could_not_end_is_named_and_nothing_added_when_it_ended_everything() -> None:
    outcomes = sys.modules["runner_cordis_plugin.jail"].KillOutcome  # brig's, as the row holds it

    def item(kind: str, outcome: Any, detail: str) -> SimpleNamespace:
        return SimpleNamespace(kind=kind, identity="77", outcome=outcome, detail=detail)

    failed_outcome = SimpleNamespace(value="FAILED")  # anything but ended or gone
    ended = SimpleNamespace(
        items=(item("workload_group", outcomes.ENDED, ""), item("supervisor", outcomes.ALREADY_GONE, ""))
    )
    failed = SimpleNamespace(
        items=(
            item("workload_group", outcomes.ENDED, ""),
            item("helper", failed_outcome, "EPERM"),
            item("supervisor", failed_outcome, "x"),
        )
    )
    assert still_running(ended) == "" and unended_for("") == ""
    assert still_running(failed) == "helper 77: EPERM; supervisor 77: x"
    note = unended_for(still_running(failed))
    assert (
        note.startswith("; ending it did not complete: helper 77: EPERM") and "ps -eo pid,pgid,args" in note
    )
