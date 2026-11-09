"""The confined runner's mechanism over brig (`runner:confined`): a Spec built from where the
work is, compiled, launched, graded.

`spec_for` is the whole policy as a pure function. What an input may write: the project root
(`write`) and a scratch directory of the jail's own. What it may not, even inside those: the
composition's layer files (an input rewriting one would reshape the program running it, outside
the jail), every path the host imports code from (`sys.path` entries and the interpreter's
prefix), the interpreter bh-02 runs on (its files: in a venv layout the base's binary is on
neither of those, and the next start on the host would run what an input wrote there; and the
directory of every link on the way to it, which a mount on the file cannot hold: an input
could rename the link and plant a Python of its own at its name), the
directory of every package bh-02 runs code from (`code`: bh-02's own, cordis's,
brig's and each plugin's, as installed; under a writable root when bh-02 works on its own
checkout, an editable install), whose modules bh-02 imports in its own process, brig's own
self-modification list (`.git/hooks`, `.git/config`, shell rc
files, CLAUDE.md, ...), any secret below under a writable root (it may not replace what it can't
read), and bh-02's configuration directories under one (`trusted`: the person's
`$XDG_CONFIG_HOME/bh-02` and `~/.config/bh-02`, when bh-02 runs from the home directory), whose
models file and startup file a later session reads on the host and trusts. What
it may not read: brig's credential list under the home directory, `hide`
under the project (nothing by default), and what the `host` value names as `secrets` (the
sessions' state, where Claude Code keeps its tokens). No
network: the program's own socket is the one way in or out. The worker's environment is scrubbed
to a short allowlist. brig's host process, which starts the worker from outside the jail,
keeps bh-02's own environment: brig's host runtime composes `{**os.environ, **jail.env}` by its
spec, and `jail.env` can add keys but not remove them. So a variable of the launching shell (a
`CLAUDE_*` of a Claude Code that launched bh-02, say) sits in that process, out of an input's
reach (in the jail, `ps` fails with a permission error; measured). A key the person exports
for a model (`key = { env = ... }`) is there too, and in no worker's environment unless `env`
lists it.

One policy, two platforms; only the stack and the read model differ:

- darwin: brig's `scratch_darwin()` (seatbelt). Reads by denylist, which is `spec_for` as it is:
  everything but the secrets. seatbelt judges a rename by its two paths, and pins each directory
  between a write root and a write deny against being renamed away or over, but not one that is
  absent: a tree of an input's own renamed onto it would put its files at the denied path. So
  the jail makes each absent one (`~/.config` above `~/.config/bh-02`, `.git` above `.git/hooks`)
  before the program starts, as an empty directory the pin then holds, with the same record,
  lock and removal as Linux's placeholders below (brig decision-208).
- Linux: brig's `strict_linux()` (bubblewrap). Reads by allowlist, so `allowlisted` turns the
  policy into one: what is readable is the system tree (`/usr`, `/etc`, ...), the interpreter
  (`sys.base_prefix`, `sys.prefix`), the directories the command names, bh-02's own code
  (`code`, read-only: the extensions process imports cordis, with an editable install from the
  workspace), and what the policy lets an input write. Everything else does not exist in the
  jail, the home directory included. brig's supervisor, the jail's PID 1, runs under a Python
  the jail holds, chosen at each compile (`supervisor_interpreter`): the system's
  `/usr/bin/python3` where there is one, else the one bh-02 runs on.
  The secrets stay `read_denies`, now brig's carve-outs: one inside that tree (a `hide`n file
  at the project root, a state directory under it) is masked if it exists, and one that does not
  exist yet is not, which brig's `fs_read` grade says (`best_effort`, naming it).
  bubblewrap holds each absent write-denied path (`.envrc`, `.vscode`, ...)
  by mounting over an empty directory on the host, which the jail makes (and marks as its own)
  before bubblewrap starts; the jail removes the ones it made once brig has verified the worker
  is gone, never before (a mount point removed while the
  jail lives is detached inside it). A mount can be undone from the host (a file renamed over
  a denied or masked one, as a host `git config` does to `.git/config`; a placeholder removed),
  and from then on an input could write or read that path. So the jail watches every path it
  holds (`tripwired`, `tripwire.Tripwire`; never one an input may create) and ends itself at the
  first such change: the next input's jail holds the path again, and the input says why
  (`ended`). Until it has ended (a few milliseconds; measured in the README) a program already
  running in it can get one write or read in, so while the jail holds a secret under a writable
  root `fs_read` stays best-effort (`graded`) and `notice()` says which paths (`held`, `notice_for`).

On both, the jail is launched tethered to bh-02 (`_Held`): when bh-02 ends, however it ends,
brig kills the jail's process group, so a program an input left running doesn't outlive it (on
Linux, bubblewrap's whole namespace; on darwin, what stayed in the group).

How many jails a session starts follows from what keeps its programs apart. Where brig gives a
program namespaces of its own (`Process.namespaces`: bubblewrap as an unprivileged user, nested
user namespaces allowed) a session has one jail for each directory its programs work in, and every
program starts in it: a sibling's socket, signals, `/proc` and scratch are out of its reach, and
stopping one ends its own pid namespace. Where brig does not (darwin; bubblewrap as uid 0; nested
user namespaces blocked) each program keeps a jail of its own, since in one jail a program could
connect to a sibling's socket, or unlink it (measured: TASK-0074's notes). What a shared jail reads
is decided once, when it is created (`_outside`).

Anywhere else `start` refuses and names `runner:unconfined`.
"""

import asyncio
import contextlib
import fcntl
import json
import os
import shutil
import signal
import stat
import subprocess
import tempfile
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from sys import base_prefix, prefix
from sys import executable as host_executable
from sys import path as import_path
from sys import platform as host_platform
from typing import Protocol, runtime_checkable

from brig.core import (
    CREDENTIAL_READ_DENIES_HOME_RELATIVE,
    SELF_MODIFY_WORKSPACE_RELATIVE,
    Channel,
    ChannelKind,
    EnvMode,
    EnvPolicy,
    FsPolicy,
    ReadModel,
    Spec,
)
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, DEFAULT_INTERPRETER, InterpreterNotMounted, pins
from brig.run import (
    EndpointRefused,
    HostRuntime,
    IoPolicy,
    Jail,
    KillItem,
    KillOutcome,
    KillReport,
    Process,
    SupervisorGone,
    SupervisorUnresponsive,
    TetherClosed,
    build_compile_ctx,
    group_alive,
)
from brig.stack import CompiledJail, Stack, scratch_darwin, strict_linux
from host_paths import state_home
from runner_cordis_plugin.runner import ArgvFor
from runner_cordis_plugin.tripwire import Tripwire

__all__ = [
    "MARK",
    "BASELINE_ENV",
    "SYSTEM_READABLE",
    "BrigConfig",
    "BrigJail",
    "Host",
    "allowlisted",
    "git_author",
    "graded",
    "group_alive",
    "held",
    "host_interpreters",
    "identity",
    "link_directories",
    "made_by_the_jail",
    "mountable",
    "notice_for",
    "readable_roots",
    "record_text",
    "recorded",
    "recorded_group",
    "records_dir",
    "released_for",
    "remove_placeholders",
    "self_modify_denied",
    "spec_for",
    "stack_for",
    "still_made",
    "still_running",
    "supervisor_interpreter",
    "told_reads",
    "tripwired",
    "uncovered",
]

_READY_TIMEOUT_S = 10.0

#: How many links one lookup follows before the kernel gives up (ELOOP): `_links_on_the_way` stops there.
_MAX_LINKS = 40

#: The system tree a Linux jail may read: what the interpreter links against and reads at
#: start (`/lib`, `/usr/lib`, `/etc/ld.so.cache`, locale data) and what an input runs (`/bin/sh`,
#: `git`, ...). Entries that do not exist on a host (`/lib64` on arm64) are dropped at start.
SYSTEM_READABLE: tuple[str, ...] = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc")


def _seatbelt(python: str) -> Stack:
    """darwin's preset: a seatbelt profile has no supervisor to name an interpreter for."""
    del python
    return scratch_darwin()


#: Each platform's preset, given the interpreter brig's supervisor runs under (`stack_for`).
_STACKS: Mapping[str, Callable[[str], Stack]] = {"darwin": _seatbelt, "linux": strict_linux}


@runtime_checkable
class Host(Protocol):
    """What the jail needs of the `host` value (CONTRACTS.md: host): the composition's files,
    which an input may not write; the secrets, which it may not read; bh-02's configuration directories
    (`trusted`), whose files the host reads and trusts, which it may not write; the directories
    bh-02 runs its own code from (`code`), which every jail reads and no input writes; and the
    project's auto memory directory (`auto_memory`), which it may write ('' for none)."""

    @property
    def paths(self) -> tuple[str, ...]: ...
    @property
    def secrets(self) -> tuple[str, ...]: ...
    @property
    def trusted(self) -> tuple[str, ...]: ...
    @property
    def code(self) -> tuple[str, ...]: ...
    @property
    def auto_memory(self) -> str: ...


#: The variables the jail always lets through: what a program needs to run at all.
BASELINE_ENV: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL", "TERM")


@dataclass(frozen=True, slots=True)
class BrigConfig:
    """`write`: where an input may write besides its scratch dir (relative to the python row's root).
    `deny`: more paths it may not write. `allow`: names from brig's self-modification list
    (`SELF_MODIFY_WORKSPACE_RELATIVE`: `.git/hooks`, `CLAUDE.md`, ...) an input may write after all;
    by default the project's guidance files, which editing is ordinary work. The rest stay denied:
    they can run code outside the jail later (hooks, shell rc files, editor and Claude settings).
    `hide`: paths it may not read (relative to the root; none by default). `env`: the variables that
    survive the scrub; None (unset) is `BASELINE_ENV` plus the names of the person's `runner.toml`
    (`allowlist.effective`), a list here replaces that whole list."""

    write: Sequence[str] = (".",)
    deny: Sequence[str] = ()
    allow: Sequence[str] = ("CLAUDE.md", "AGENTS.md")
    hide: Sequence[str] = ()
    env: Sequence[str] | None = None


def spec_for(
    *,
    root: str,
    scratch: str,
    home: str,
    config: BrigConfig,
    layers: Sequence[str],
    host: Sequence[str],
    secrets: Sequence[str] = (),
    trusted: Sequence[str] = (),
    code: Sequence[str] = (),
    interpreters: Sequence[str] = (),
    links: Sequence[str] = (),
    memory: str = "",
) -> Spec:
    """The jail's Spec. `host` is every path the host process loads code from; any under a
    writable root is denied, as are the layer files and brig's self-modification list.
    `secrets` (absolute) may not be read, wherever they are. `trusted` (absolute directories:
    bh-02's configuration, whose files the host reads and trusts) and `code` (absolute: the
    directory of every package bh-02 runs code from) may not be written where they are under a
    writable root. `interpreters` (absolute, resolved: the files of the interpreter bh-02 itself
    runs on, `_interpreter_files`) may not be written where they are under one either, nor the
    directory of each of `links` (absolute: the links on the way to them, `_links_on_the_way`;
    `link_directories`). `memory` (absolute: the project's auto memory directory, '' for none) may be
    written, as a root of its own outside the project: no self-modification list applies there,
    since nothing reads it but the memory row, through no link."""
    roots = [str(Path(root, w).resolve()) for w in config.write]
    writable = [*roots, scratch, *([str(Path(memory).resolve())] if memory else [])]
    # A host import path *inside* a writable root is denied. One that *is* a root (the project
    # itself on sys.path, as under `python -m bh_02`) is not: denying it would make the project
    # read-only. What that leaves: a module an input writes at the project root could shadow one
    # the host has not imported yet. The `bh-02` console script never puts the root on sys.path.
    under = [p for p in host if p not in writable and any(p.startswith(r + "/") for r in writable)]
    selfmod = [str(Path(r, name)) for r in roots for name in self_modify_denied(config.allow)]
    hidden = [*(str(Path(root, name).resolve()) for name in config.hide), *secrets]
    # A secret an input may not read, it may not overwrite or remove either: one under a writable
    # root (a `hide`n file, a state directory) is denied writing too, or an input could replace
    # what it can't see.
    kept = [s for s in hidden if any(s == r or s.startswith(r + "/") for r in writable)]
    # bh-02's configuration under a writable root (bh-02 run from the home directory): an input
    # there could replace a file a later session reads on the host and trusts, the person's
    # startup file with a link to one the jail hides, say. Only strictly under one: a root that is
    # the directory or inside it (bh-02 run in its own config) would be left read-only.
    configured = [t for t in trusted if any(t.startswith(r + "/") for r in roots)]
    # bh-02's own code under a writable root (bh-02 working on its own checkout, an editable
    # install; or run from a home the checkout is in): an input there could write a module bh-02
    # imports later (a plugin a layer names, a module a reload imports), so it would choose code
    # bh-02 runs in its own process. By package, whatever `host` holds: a package an import
    # hook finds is on no `sys.path`, and a `src` that is the project itself is not denied there.
    # Only strictly under a root, as `trusted`: one the project is would leave it read-only.
    running = [c for c in code if any(c.startswith(r + "/") for r in roots)]
    # The interpreter bh-02 itself runs on, under a root an input may write (bh-02 run from a
    # directory that holds the uv-managed Python, the home directory say): the next bh-02 start on
    # the host would run what an input wrote there, outside any jail. `host` denies the standard
    # library and the venv's prefix, but in a venv layout the base's own binary is on neither (with
    # no venv the whole prefix is, and this adds nothing). Files only: a deny on a link is the mount
    # on what it leads to, so the file is what holds. Strictly under a root, as `host`.
    allows = tuple(writable)
    interpreter = [i for i in interpreters if i not in allows and any(i.startswith(r + "/") for r in allows)]
    # And the links on the way to it, which a mount on the file does not hold (the entry of a link
    # can be renamed, and an input plant its own interpreter at the name): their directories.
    holders = link_directories(links, allows)
    denies = [
        *layers,
        *under,
        *selfmod,
        *(str(Path(root, d).resolve()) for d in config.deny),
        *kept,
        *configured,
        *running,
        *interpreter,
        *holders,
    ]
    return Spec(
        fs=FsPolicy(
            write_allows=allows,
            write_denies=tuple(dict.fromkeys(denies)),
            read_denies=(
                *(str(Path(home, name)) for name in CREDENTIAL_READ_DENIES_HOME_RELATIVE),
                *hidden,
            ),
        ),
        env=EnvPolicy(
            mode=EnvMode.SCRUB,
            allow_names=tuple(BASELINE_ENV if config.env is None else config.env),
            set=(("TMPDIR", scratch),),
        ),
        # The program's socket: brig's Spec names a channel, not its path (decision-186), and
        # each mechanism grants the channel directory on its own, nothing here; `BrigJail`
        # reserves it (`jail.channel("program")`) and puts its bound path in the program's argv
        # (decision-185, TASK-0079.31).
        channels=(Channel(name="program", kind=ChannelKind.LISTEN),),
    )


def link_directories(links: Sequence[str], writable: Sequence[str]) -> tuple[str, ...]:
    """The directories an input may not write, so that it cannot change a link on the way to the
    interpreter bh-02 runs on. `links` is that chain as the host found it (`_links_on_the_way`):
    where each link's own entry sits, absolute, in the directory that physically holds it.

    A mount on the interpreter's file holds the file, not the links that lead to it: the entry of
    a link in a writable directory can be renamed, and a Python of the input's own planted at its
    name (a project opened at the home directory holds uv's `cpython-3.15-<platform>` link to the
    versioned directory the venv's `python` goes through, and the next `uv run` on the host would
    execute what it planted). Only the directory that holds the link refuses that. So, for each
    link, its directory, when it lies strictly under a root in `writable` (the roots the jail may
    write; elsewhere an input changes nothing). Not a root itself, as for `host`: the project is
    the directory that holds the link, and denying it would leave the project read-only. Each once,
    in the order the links are met."""
    holders = (str(PurePosixPath(link).parent) for link in links)
    return tuple(dict.fromkeys(h for h in holders if any(h.startswith(r + "/") for r in writable)))


def allowlisted(spec: Spec, readable: Sequence[str]) -> Spec:
    """`spec`, reading by allowlist: `readable` is the tree an input may read, and the policy's
    read denies become the carve-outs inside it. The environment and the channel are the
    policy's, unchanged, and so are the writes but one kind: a path denied both reading and
    writing (a secret under the project) keeps only its read deny. bwrap masks an existing one
    with a read-only `/dev/null`, which refuses writes and removal too (a write deny as well
    would be a bind of the real file, under the mask). An absent one has nothing to mask, so an
    input could create it; it is left alone: a directory there would be in the person's way, and
    nothing of bh-02's reads one."""
    return replace(
        spec,
        fs=FsPolicy(
            write_allows=spec.fs.write_allows,
            write_denies=tuple(d for d in spec.fs.write_denies if d not in spec.fs.read_denies),
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(readable),
            read_denies=spec.fs.read_denies,
        ),
    )


def readable_roots(
    *,
    argv: Sequence[str],
    interpreter: Sequence[str],
    system: Sequence[str],
    code: Sequence[str] = (),
) -> tuple[str, ...]:
    """What a Linux jail reads besides what it may write: the system tree, the interpreter's
    trees (the standard library under `sys.base_prefix`, the environment under `sys.prefix`),
    the directory of every absolute path the command names (the worker program's own), and
    bh-02's own code (`code`: the directory of each package it runs, which the extensions'
    worker imports cordis from; with an editable install, the workspace's `src/cordis`, which
    the interpreter's trees don't hold). Not the host's whole `sys.path`: under pytest or
    `python -m` it holds the workspace root, and with it the whole workspace, for
    nothing a worker needs."""
    named = [str(Path(arg).parent) for arg in argv if arg.startswith("/")]
    return tuple(dict.fromkeys([*system, *interpreter, *named, *code]))


def uncovered(denies: Sequence[str]) -> tuple[str, ...]:
    """The write denies that no other one contains. bubblewrap mounts each in turn, and one
    inside a directory already bound read-only (an absent secret under a directory the host
    imports code from) would need a mount point made on a read-only mount, which fails the
    launch; the outer deny holds it already."""
    return tuple(d for d in denies if not any(d.startswith(o + "/") for o in denies if o != d))


def held(spec: Spec, absent: Collection[str]) -> tuple[str, ...]:
    """The read denies a Linux jail (`spec`, `allowlisted`) holds at or under a root an input
    may write: one that is there (not in `absent`), which bubblewrap masks with a mount on the
    path itself, and an absent one no input can create, at or under a write deny (a directory
    bound read-only), where only
    the host could put a file, which the jail could then read. A mount is on the host's
    directory entry, so replacing that entry on the host (an editor saves by renaming a new file
    over it) or removing it detaches the mount inside the jail, and an input can then read and
    rewrite what is there (measured). Not an absent one nothing holds (a `hide`n file the project
    has none of): an input may create it, and a file the host creates there is readable, which
    brig's `fs_read` grade names. The rest are outside every writable root, where the allowlist
    alone keeps them out of the jail."""
    roots, denies = spec.fs.write_allows, spec.fs.write_denies
    return tuple(
        d
        for d in spec.fs.read_denies
        if any(d == r or d.startswith(r + "/") for r in roots)
        and (d not in absent or any(d == w or d.startswith(w + "/") for w in denies))
    )


def tripwired(spec: Spec, absent: Collection[str]) -> tuple[str, ...]:
    """The paths a Linux jail holds with a mount that the host can undo: every write deny under
    a root an input may write (an existing path bound read-only over itself, or a placeholder) and
    every secret held there (`held`; `absent` names the read denies that are not there). Replacing,
    moving or removing one on the host ends the jail (`Tripwire`); a deny outside every writable
    root is not mounted at all. Never a path an input may create: that would end the jail it
    runs in, blaming the host."""
    roots = spec.fs.write_allows
    under = [d for d in spec.fs.write_denies if any(d.startswith(r + "/") for r in roots)]
    return tuple(dict.fromkeys([*under, *held(spec, absent)]))


def notice_for(platform: str, holds: Sequence[str]) -> str:
    """What the person should know at the start of a session about the secrets under a root an
    input may write (`held`), or nothing: on darwin seatbelt matches paths, so nothing the host
    does to them lets an input in."""
    if platform != "linux" or not holds:
        return ""
    return (
        f"The jail keeps inputs from reading {', '.join(holds)}. On Linux it does that with a mount "
        "on each path that is there. The host can undo a mount: when a file at one of these paths "
        "is replaced (an editor saves by renaming a new file over it) or removed while the Python "
        "process runs, bh-02 ends the jail at once (a running input with it) and the next input's "
        "jail holds the path again. A program an input left running can still read or rewrite it "
        "in the milliseconds that takes, so edit them after `/release`."
    )


def released_for(running: bool = False) -> str:
    """What `/release` tells the person after it has stopped what it could: that a program this
    jail started still runs (`running`: an owner that did not stop its own), whose jail holds
    what it holds. Empty when nothing does."""
    if not running:
        return ""
    return (
        "A program this runner started still runs (its row did not stop it on /release), and "
        "its jail holds what it holds: /rows shows the rows; /restart one, then /release again."
    )


def told_reads(trees: Sequence[str], own: Sequence[str]) -> tuple[str, ...]:
    """The trees a jail reads, as the model is told them: each once, none that another of them
    holds (bh-02's own code, or the interpreter's environment, inside the project), the jail's
    own directories (its scratch and the program's socket, named anew at every start) as `$TMPDIR`
    alone, so the prompt is the same from one start to the next (the claude-code provider starts
    Claude Code again when it changes)."""
    kept = [t for t in trees if not any(t == o or t.startswith(o + "/") for o in own)]
    outer = [t for t in kept if not any(t.startswith(o + "/") for o in kept)]
    return (*dict.fromkeys(outer), "$TMPDIR")


def git_author(name: str, email: str) -> tuple[tuple[str, str], ...]:
    """The person's git identity as the variables git reads before any config file:
    `GIT_AUTHOR_*` and `GIT_COMMITTER_*`, for what is not empty. A Linux jail has no home
    directory, so a jailed `git commit` can't read `~/.gitconfig`; these carry the name and
    email alone, never the rest of the person's config (aliases, credential helpers, includes)."""
    pairs = [("NAME", name), ("EMAIL", email)]
    return tuple(
        (f"GIT_{who}_{what}", value) for who in ("AUTHOR", "COMMITTER") for what, value in pairs if value
    )


def graded(report: Mapping[str, str], holds: Sequence[str]) -> dict[str, str]:
    """brig's grades, with `fs_read` best-effort while a Linux jail holds a secret with a mount
    (`held`): brig grades a masked path enforced, and it is, until the host replaces or
    removes it."""
    out = dict(report)
    if holds and out.get("fs_read") == "enforced":
        out["fs_read"] = "best_effort"
    return out


def made_by_the_jail(absent: Sequence[str]) -> tuple[str, ...]:
    """The directories made on the host for bubblewrap to mount over at absent write-denied
    paths (each path and each missing parent; `absent` lists them all), or on darwin for
    seatbelt's pins to hold (`BrigJail._absent_pins`), deepest first: the order
    they can be removed in once the jail is gone (and, reversed, made in)."""
    return tuple(sorted(set(absent), key=lambda p: (-p.count("/"), p)))


def host_interpreters() -> tuple[str, ...]:
    """Where a Linux host's Python for brig's supervisor may be, best first: brig's own default,
    the system's (`/usr/bin/python3`, which every host that works today has, so it keeps being
    the one), then the Python bh-02 itself runs on: `sys.base_prefix`'s, which the jail mounts
    for the program it starts anyway, so a host with its system Python elsewhere (or none)
    still has one. Never `sys.prefix`'s: a venv's `python` is that one's link, with the venv's
    site-packages on its path, and the supervisor is stdlib-only."""
    return (DEFAULT_INTERPRETER, str(Path(base_prefix, "bin", "python3")))


def supervisor_interpreter(
    found: Mapping[str, str],
    mounted: Sequence[str],
    *,
    writable: Sequence[str] = (),
    denied: Sequence[str] = (),
) -> str:
    """The interpreter brig's supervisor, the jail's PID 1, runs under (`strict_linux(python=...)`):
    the first of `found` that the jail holds whole. `found` is each candidate as spelled, best
    first, with the path it resolves to; `mounted` is the Spec's read roots (the system, the
    interpreter's trees, bh-02's code: bound read-only). brig checks the spelling only, and leaves a
    link that leads out of the roots to the Spec's author (Debian's `/usr/bin/python3` goes to
    `/etc/alternatives`), so a candidate counts when its spelling and its target are both at or
    under a root: a link out of them would dangle in the jail, and a jail whose PID 1 can't start
    is no jail.

    `writable` is the Spec's write roots and `denied` its write denies. An input could replace what
    runs as the jail's PID 1, so a path under a writable root counts only where a write deny holds
    it. bh-02's base interpreter lies under the project when the project is the home directory (a
    uv-managed Python under `~/.local`), and `spec_for` denies the standard library the host imports
    from there, the interpreter's file and the directory of each link on the way to it
    (`link_directories`): the `bin/python3` link that leads to it is held by its directory, as a deny
    on the link itself, a mount on the file, would not hold its entry. A candidate that is not on
    that way, a link in the project `spec_for` was not handed, is not held, and not a Python the
    jail holds (unless bh-02 runs on that interpreter itself, when `prefix` is in the host and the
    whole tree is denied).

    When none qualifies, brig's own default: a Spec that does not mount it is refused by brig
    (`InterpreterNotMounted`), which `BrigJail.compile` turns into the runner's own error
    (`_no_python_message`). One that does mount it but has no Python there fails to start with
    the supervisor's own stderr (`SupervisorFailed`). Nothing here hides either."""

    def under(roots: Sequence[str], path: str) -> bool:
        return any(PurePosixPath(path).is_relative_to(root) for root in roots)

    def whole(path: str) -> bool:
        return under(mounted, path) and (not under(writable, path) or under(denied, path))

    for spelled, target in found.items():
        if whole(spelled) and whole(target):
            return spelled
    return DEFAULT_INTERPRETER


def _no_python_message(looked_for: Sequence[str], python: str) -> str:
    """What the person reads when brig refuses the jail for want of a Python it mounts: the
    candidates looked for (`host_interpreters`), brig's reason in bh-02's terms (`python`, the
    one brig refused, is under no path the jail mounts), and the steps a bh-02 user takes, as the
    missing-bwrap error names them. brig's own text (its advice is for code that embeds brig)
    stays on the exception's `__cause__`."""
    looked = ", ".join(looked_for) or "none"
    return (
        "runner:confined cannot start its jail on this host: the jail runs brig's supervisor as its "
        "PID 1, under a Python the jail mounts, and none of the Pythons looked for "
        f"({looked}) is one. brig refused the jail (InterpreterNotMounted): {python} is under no path "
        "the jail mounts. Install python3, or use `runner:unconfined` for the runner row (or "
        "`bh-02 --no-jail`), knowing it confines nothing"
    )


def _present(candidates: Sequence[str]) -> dict[str, str]:
    """Each of `candidates` that is an executable file on this host (through its links), with the
    path it resolves to: what `supervisor_interpreter` chooses among."""
    return {c: str(Path(c).resolve()) for c in candidates if Path(c).is_file() and os.access(c, os.X_OK)}


def _interpreter_files(spelled: Sequence[str]) -> tuple[str, ...]:
    """The files the interpreter bh-02 itself runs on is: where each name in `spelled` (how the host
    reaches it: `sys.executable`, the base installation's `bin/python3`) leads once every link on
    the way is followed, as `spec_for` is handed `host`'s paths, resolved. The file, not the names:
    a write through any of them reaches it, and a mount holds it, where the entry of a link in a
    writable directory is held by none. A name that is empty (an embedded interpreter has no
    `sys.executable`) leads nowhere and is left out."""
    return tuple(dict.fromkeys(str(Path(name).resolve()) for name in spelled if name))


def _stepped(
    here: PurePosixPath, pending: Sequence[str], led_to: str | None
) -> tuple[PurePosixPath, tuple[str, ...]]:
    """One step of the kernel's lookup of a path, as `_links_on_the_way` takes it: `here` is the
    directory reached, as it physically is (no link in it), and `pending` what is left to look up,
    its first component the one just looked at, which `led_to` says is a link (to this text) or
    not (`None`). Returns the directory the lookup is in and what is left. A component that is not
    a link is entered (`..` leaves); a link is replaced by what it leads to, which starts at `/` if
    absolute and at the directory that holds the link if not."""
    part, rest = pending[0], tuple(pending[1:])
    if led_to is None:
        return (here.parent if part == ".." else here / part), rest
    target = PurePosixPath(led_to)
    if target.is_absolute():
        return PurePosixPath(target.anchor), (*target.parts[1:], *rest)
    return here, (*target.parts, *rest)


def _links_on_the_way(spelled: Sequence[str]) -> tuple[str, ...]:
    """Every link on the way from each name in `spelled` (`_interpreter_files`) to the file it leads
    to, the entry of each as it sits on disk: the link `python3` in a venv, the `python` it leads to,
    a link to a directory in the middle of a path (uv's `cpython-3.15-<platform>`, which the venv's
    `python` goes through), one the target of another leads through, in the order met. Walked one
    component at a time (`_stepped`), so each link is found in the directory that physically holds
    it (a name reached through a link to a directory is that directory's, which is where a mount
    lands), and what `link_directories` decides on is where the entries are. The kernel's own limit
    on links in one lookup ends a loop, which is no interpreter.

    Raises:
        OSError: a link was replaced as it was read (the host changed its Python while a jail
            started).
    """
    found: list[str] = []
    for name in spelled:
        if not name:
            continue
        path = PurePosixPath(name)
        here = PurePosixPath(path.anchor) if path.is_absolute() else PurePosixPath(Path.cwd())
        pending, followed = (path.parts[1:] if path.is_absolute() else path.parts), 0
        while pending and followed <= _MAX_LINKS:
            entry = Path(here, pending[0])
            led_to = os.readlink(entry) if entry.is_symlink() else None
            if led_to is not None:
                found.append(str(entry))
                followed += 1
            here, pending = _stepped(here, pending, led_to)
    return tuple(dict.fromkeys(found))


def stack_for(platform: str, python: str = DEFAULT_INTERPRETER) -> Stack:
    """brig's preset for `platform`, or a refusal that says what to use instead. `python` is the
    interpreter inside a Linux jail that brig's supervisor runs under (`supervisor_interpreter`);
    darwin's jail has no supervisor.

    Raises:
        RuntimeError: brig has no preset for `platform`.
    """
    try:
        preset = _STACKS[platform]
    except KeyError:
        raise RuntimeError(
            f"runner:confined runs on darwin (seatbelt) and Linux (bubblewrap); this is {platform}. "
            "Use `runner:unconfined` for the runner row (or `bh-02 --no-jail`), knowing it confines nothing"
        ) from None
    return preset(python)


def self_modify_denied(allow: Sequence[str]) -> tuple[str, ...]:
    """brig's self-modification list without the names `allow` lets an input write. A name that
    is not on the list is a mistake in the row's config, never silently ignored."""
    unknown = [name for name in allow if name not in SELF_MODIFY_WORKSPACE_RELATIVE]
    if unknown:
        raise ValueError(
            f"the runner row's `allow` names {', '.join(map(repr, unknown))}, which brig does not deny "
            f"in the first place; `allow` takes only names from its self-modification list: "
            f"{', '.join(SELF_MODIFY_WORKSPACE_RELATIVE)}. To let an input write another path, "
            "use `write`"
        )
    return tuple(name for name in SELF_MODIFY_WORKSPACE_RELATIVE if name not in allow)


def mountable(denies: Sequence[str], instead: Mapping[str, str]) -> tuple[str, ...]:
    """The write denies bubblewrap can mount, each once, with `instead` mapping a deny to the
    path denied in its place. An absent one under a path that exists as a FILE (`.git/hooks`
    where `.git` is a worktree's or submodule's `gitdir:` pointer) can't have a mount point made
    for it (bwrap: "Can't mkdir parents ... Not a directory", and the Python process never starts), so it
    maps to that file, bound read-only over itself: neither rewritten nor removed, so nothing is
    ever created under it. An absent one whose parent is absent too (`.git/config` in a project
    that is not a repository) maps to its topmost absent ancestor (`.git`): one empty directory
    held on the host rather than a `.git/config` directory inside one, which would break the
    person's own `git init` there while the Python process runs."""
    return tuple(dict.fromkeys(instead.get(deny, deny) for deny in denies))


def still_running(report: KillReport) -> str:
    """What a teardown could not end, for the person: each item that failed, named, with what
    it said; "" when everything ended or was already gone."""
    return "; ".join(
        f"{item.kind} {item.identity}: {item.detail}"
        for item in report.items
        if item.outcome not in (KillOutcome.ENDED, KillOutcome.ALREADY_GONE)
    )


def records_dir(environ: Mapping[str, str], home: str) -> str:
    """Where a jail records the placeholders it made, one file per jail: bh-02's state
    directory (`$XDG_STATE_HOME/bh-02`, else `~/.local/state/bh-02`; `host_paths.state_home`),
    outside every jail."""
    return str(state_home(environ, Path(home)) / "bh-02" / "jails")


def identity(found: os.stat_result) -> str:
    """Which directory a placeholder is, where the filesystem takes no `MARK`: its inode and
    when it changed. The inode alone is not enough: a directory removed and made again at the
    same path can get the same one back (measured, on overlayfs). The change time is as fine as
    the kernel's clock tick, so one made again within the same few milliseconds would pass for
    the jail's; and a placeholder something was added to and removed from since (another jail's
    placeholders inside it) reads as changed, and is kept."""
    return f"{found.st_ino}:{found.st_ctime_ns}"


def record_text(made: Sequence[tuple[str, str]], group: int | None = None) -> str:
    """A jail's record of its placeholders: each path, deepest first, with how the directory
    there is known to be the jail's (`mark:<jail id>`, else its `identity`), so a later sweep
    removes only a directory the jail made; and once bubblewrap is started, its process group,
    so a sweep never removes what a jail still alive holds."""
    whole: dict[str, object] = {"made": [[path, found] for path, found in made]}
    if group is not None:
        whole["group"] = group
    return json.dumps(whole) + "\n"


def recorded(text: str) -> list[tuple[str, str]]:
    """The placeholders a record names (`record_text`), each with how the jail knows it; nothing
    for a record that can't be read as one, which is then only removed, and none for an entry that
    names no way to know it (a record edited or damaged), since nothing proves a jail made it."""
    try:
        made = json.loads(text)["made"]
        return [(str(path), found) for path, found in made if isinstance(found, str)]
    except ValueError, KeyError, TypeError:
        return []


def recorded_group(text: str) -> int | None:
    """The process group of the bubblewrap a record names (`record_text`); None when it names
    none (written before bubblewrap started) or can't be read."""
    try:
        group = json.loads(text)["group"]
    except ValueError, KeyError, TypeError:
        return None
    return group if isinstance(group, int) else None


def still_made(was: str, found: str, mark: str | None) -> bool:
    """Whether a directory is still the placeholder a jail recorded as `was`: its `MARK` (the
    jail's id, in an extended attribute the jail set on it as it made it), or where the
    filesystem takes none, its `identity`. A mark survives what is added and removed under it;
    the person's own directory has none."""
    if was.startswith("mark:"):
        return mark == was.removeprefix("mark:")
    return was == found


def remove_placeholders(made: Sequence[tuple[str, str]]) -> None:
    """Remove each placeholder a jail made (deepest first) that is still what it made (an empty
    directory, `still_made`). One the person has put something in, or replaced with one of their
    own, stays. Only once no jail can have mounted over it: removed while a jail lives, it stops
    being a mount point inside it, and the path it denies is writable there."""
    for path, was in made:
        with contextlib.suppress(OSError):
            found = os.lstat(path)
            if stat.S_ISDIR(found.st_mode) and still_made(was, identity(found), _mark_of(path)):
                os.rmdir(path)


@dataclass(frozen=True, slots=True)
class _Facts:
    """What one jail is, kept with it for every program it runs (CONTRACTS.md: runner): its grades
    (`graded`), what the person should know about it (`notice_for`), the trees its programs read
    when that is all they read (`told_reads`: a Linux jail's; empty on darwin) and the roots they
    may write but its scratch. All decided when the jail is created, never by a later start."""

    report: Mapping[str, str]
    notice: str = ""
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()


class _Held:
    """One brig jail and what bh-02 holds on the host for it: `jail`, `facts` (what it is), the
    directories it made (`made`, deepest first) and the programs running in it (`programs`).
    `shared` says whether another program may start in it (`Process.namespaces`, found at its first
    start), and `cwd` is the directory it was created for, its write roots' own.

    `tether` is the write end of the jail's tether (brig SPEC.md section 8): held by this
    process alone, so when bh-02 ends, however it ends (`SIGKILL` included), the kernel closes
    it and brig's watcher kills the jail's whole process group, a program an input left running
    in the background with it. `end` closes it once brig's teardown is done.

    `wire` (Linux) watches the paths the jail holds with a mount and ends the jail when the host
    undoes one (`Tripwire`); `ended` says so. `end` stops it first: removing the placeholders
    would read as the host undoing them.

    `lock` (Linux) is this jail's shared hold on the user's bh-02 jail lock, taken before the
    jail looked at the filesystem and held while it runs. A placeholder is removed only by a
    jail that can then take the lock exclusively: no other bh-02 jail is running, so none has
    mounted over one (a second session in the same project binds the first one's `.claude/`
    read-only, and removing it on the host detaches that bind; measured). `record` is the file
    that names them meanwhile (`records_dir`): if this jail can't remove them (another runs) or
    never ends (bh-02 crashed), the next jail to start with none running does."""

    def __init__(
        self,
        jail: Jail,
        first: Process,
        facts: _Facts,
        jail_dir: str,
        made: Sequence[tuple[str, str]],
        lock: int | None,
        record: str | None,
        tether: int | None = None,
        wire: Tripwire | None = None,
    ) -> None:
        self.jail = jail
        self.facts = facts
        self.shared = False
        self.programs: list[_Jailed] = []
        self._first_pid = first.pid
        self._wire = wire
        self._tether = tether
        self._jail_dir = jail_dir
        self._made: list[tuple[str, str]] = list(made)
        self._lock = lock
        self._record = record
        self._ending: asyncio.Future[None] | None = None
        self._write()

    def ended(self) -> str:
        """Why the jail ended its programs itself (the host undid a mount, `tripped_for`), or ""."""
        return self._wire.tripped if self._wire is not None else ""

    @property
    def over(self) -> bool:
        """Whether `end` has been asked for."""
        return self._ending is not None

    def usable(self) -> bool:
        """Whether another program can start in it: a shared jail still there. PID 1 of its
        namespaces is what lives as long as they do; `Jail.alive` reads gone with no program in
        it, as this jail is between one Python process and the next."""
        group = self.jail.instance_group
        return self.shared and not self.over and not self.ended() and group is not None and group_alive(group)

    def _write(self) -> None:
        """The record as it stands: the placeholders, and which process group holds the jail they
        are mounted in: a Linux jail's instance (`Jail.instance_group`: PID 1 of its namespaces,
        which lives as long as they do, though the program ends first and a `setsid()` child of
        it runs on), else the first program's own, which leads its group. A sweep that read the
        program's group would call a jail dead that a background server still holds."""
        if self._record is not None:
            group = self.jail.instance_group
            with contextlib.suppress(OSError):
                Path(self._record).write_text(
                    record_text(self._made, self._first_pid if group is None else group)
                )

    async def end(self) -> None:
        """brig's teardown, then what the jail made, once: whoever asks first does it, and anyone
        after waits for that."""
        if self._ending is None:
            self._ending = asyncio.ensure_future(self._teardown())
        await asyncio.shield(self._ending)

    async def _teardown(self) -> None:
        if self._wire is not None:
            await asyncio.to_thread(self._wire.stop)
        report = await asyncio.to_thread(self.jail.destroy)
        gone = all(item.outcome in (KillOutcome.ENDED, KillOutcome.ALREADY_GONE) for item in report.items)
        if gone and self._lock is not None:
            _clear_up(self._lock, self._made, self._record)
        if self._lock is not None:
            os.close(self._lock)
            self._lock = None
        if self._tether is not None:
            os.close(self._tether)
            self._tether = None
        shutil.rmtree(self._jail_dir, ignore_errors=True)


class _Jailed:
    """A program brig started (`process`) in the jail `held`: interrupt is SIGINT to its group;
    stop ends this program alone where the jail is shared (brig's `Process.stop`, which ends its
    pid namespace), and the whole jail where it is this program's own. `report`, `notice`, `reads`
    and `writes` are the jail's, read whether or not the program still runs."""

    def __init__(self, held: _Held, process: Process) -> None:
        self._held = held
        self._process = process
        self._stopping: asyncio.Future[None] | None = None

    def interrupt(self) -> bool:
        return self._process.interrupt()

    def ended(self) -> str:
        """Why the jail ended its programs itself, this one among them (the host undid a mount,
        `tripped_for`), or "". Every program in the jail says the same."""
        return self._held.ended()

    def report(self) -> Mapping[str, str]:
        """The jail's grades: brig's, with `fs_read` best-effort while it holds a secret with a
        mount the host can undo (`graded`)."""
        return self._held.facts.report

    def notice(self) -> str:
        """What the person should know about this jail (`notice_for`): on Linux, the secrets it
        holds with a mount the host can undo; empty on darwin."""
        return self._held.facts.notice

    def reads(self) -> tuple[str, ...]:
        """The trees the jail's programs can read, when that is all they can read (`told_reads`):
        a Linux jail's allowlist (the system, the interpreter, the directories its creating start
        named, bh-02's own code) and the roots it may write. Empty on darwin, whose jail reads
        everything but the secrets."""
        return self._held.facts.reads

    def writes(self) -> tuple[str, ...]:
        """The directories the jail's programs may write, but its own scratch: the project and
        what `write` adds."""
        return self._held.facts.writes

    async def connect(self, *, limit: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """A stream to this start's program, through brig's verified dial (`Process.connect`,
        decision-185): the host's one check of what answers at the reserved socket, never a raw
        connect to the path (a process of the jail could plant a link there). `limit` is the
        stream's own, as `asyncio.open_connection` takes it.

        Raises:
            ConnectionError: what answered is not this process's own listener (brig's
                `EndpointRefused`, wrapped so no owner need import brig to catch it).
            OSError: nothing listens there yet.
        """
        try:
            sock = await asyncio.to_thread(self._process.connect)
        except EndpointRefused as refused:
            raise ConnectionError(str(refused)) from refused
        return await asyncio.open_connection(sock=sock, limit=limit)

    @property
    def stopped(self) -> bool:
        """Whether its owner has stopped it."""
        return self._stopping is not None

    async def stop(self) -> None:
        """End this program, once: a second stop waits for the first."""
        if self._stopping is None:
            self._stopping = asyncio.ensure_future(self._stopped())
        await asyncio.shield(self._stopping)

    async def _stopped(self) -> None:
        """A jail of its own, or one already over, ends whole. In a shared jail, `Process.stop`
        alone; a stop that could not end the program ends the jail, so what its owner stopped
        never runs on."""
        if not self._held.usable():
            await self._held.end()
            return
        try:
            report = await asyncio.to_thread(lambda: self._process.stop())
        except AttributeError, SupervisorGone, SupervisorUnresponsive:
            await self._held.end()  # its supervisor is gone, and the jail with it, or as good as
            return
        if any(item.outcome not in (KillOutcome.ENDED, KillOutcome.ALREADY_GONE) for item in report.items):
            await self._held.end()
        with contextlib.suppress(ValueError):
            self._held.programs.remove(self)


def _clear_up(lock: int, made: Sequence[tuple[str, str]], record: str | None) -> None:
    """Remove what a jail that is gone made (`made`) and its record, if `lock` can be taken
    exclusively: no other bh-02 jail runs, so none has mounted over them. Else they stay, with
    the record, for the next jail to start with none running."""
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # another jail runs: what it may have mounted over stays, and the record
    remove_placeholders(made)
    if record is not None:
        with contextlib.suppress(OSError):
            os.unlink(record)


#: The extended attribute a Linux jail marks each placeholder with: the jail's id.
MARK = "user.bh-02.placeholder"

#: The user's bh-02 jail lock: shared by every running jail, taken exclusively to clean up.
_LOCK = "/tmp/bh-02-jails-{uid}.lock"


def _place(path: str, jail_id: str) -> str | None:
    """Make the placeholder at `path`, mark it as this jail's at once, and say how it is known:
    `mark:<id>`, or where the filesystem takes no extended attribute, its `identity`. None when
    something is there already (the person's, or another jail's: never this one's to remove) or
    it can't be made (then bubblewrap makes it, unmarked, or fails to start)."""
    try:
        os.mkdir(path)
    except OSError:
        return None
    mark: Callable[..., None] | None = getattr(os, "setxattr", None)  # Linux only
    if mark is not None:
        try:
            mark(path, MARK, jail_id.encode(), follow_symlinks=False)
        except OSError:
            pass
        else:
            return f"mark:{jail_id}"
    try:
        return identity(os.lstat(path))
    except OSError:
        return None


def _mark_of(path: str) -> str | None:
    """The jail id a placeholder is marked with (`MARK`), or None."""
    read: Callable[..., bytes] | None = getattr(os, "getxattr", None)  # Linux only
    if read is None:
        return None
    try:
        return read(path, MARK, follow_symlinks=False).decode(errors="replace")
    except OSError:
        return None


def _started_in(jail: Jail, argv_for: ArgvFor, *, cwd: str) -> Process:
    """Reserve-then-start (decision-184, decision-185, TASK-0079.31): `jail.channel("program")`
    reserves a socket in the jail's own channel directory, `argv_for(reservation.bound_path)` is the
    program's, and `channel=` the reservation binds it there, never a path `argv_for` chose on its
    own.

    Raises:
        UnknownChannel: the compiled `Spec` declares no "program" channel (a bug here).
        ReservationRefused: a reservation `jail.channel` just made was refused (unreachable
            outside brig's own bugs: nothing else could race it, one reservation per start).
        ExecWrapNotAPrefix: the compiled wrap is not a pure argv prefix.
        TetherClosed: the jail's tether has already ended.
        WorkloadSpawnFailed: the argv could not be spawned in the jail.
        SupervisorGone: a supervised jail's control socket is closed.
        SupervisorUnresponsive: its supervisor did not answer, and the jail was destroyed.
        OSError: a record could not be written.
    """
    reservation = jail.channel("program")
    argv = list(argv_for(reservation.bound_path))
    return jail.start(argv, cwd=cwd, io=IoPolicy(), channel=reservation)


def _lost_for(said: str) -> str:
    """What the person is told when the host refused a mount that keeps programs apart (brig's
    decision-212), through the jail's `notice()`, which the status bar's jail field shows: what
    brig said, and what it means for this session."""
    return (
        f"{said}. So each program keeps a jail of its own instead of sharing the session's: they "
        "stay apart, at the cost of a jail each. Ask whoever runs this host why it refuses that mount."
    )


def _launch(
    compiled: CompiledJail,
    *,
    argv_for: ArgvFor,
    cwd: str,
    jail_id: str,
    jail_dir: str,
    tether: int,
    told: Callable[[str], None],
) -> tuple[Jail, Process]:
    """A new jail, with `argv_for` its first program: brig's `Jail.create` through the host runtime,
    tethered to `tether` (the read end; the jail holds a duplicate), then `_started_in`. A refused
    start (the reservation included) changes nothing in brig (the jail is its creator's), so this
    ends the jail itself before saying why: what `create` started (a `JAIL_LIFETIME` helper) never
    outlives a start nobody was handed. The start's error is the one that crosses, whatever the
    ending found: each item it could not end, or its own failure, is a note on it (`_unended`).

    Raises:
        LaunchRefused: the jail needs a capability the host runtime lacks.
        JailDirInUse: `jail_dir` holds an earlier jail's records that still run.
        HelperFailed: a helper the jail starts at its creation failed.
        UnknownChannel: the compiled `Spec` declares no "program" channel (a bug here).
        ReservationRefused: a reservation `jail.channel` just made was refused (unreachable
            outside brig's own bugs: nothing else could race it, one reservation per start).
        ExecWrapNotAPrefix: the compiled wrap is not a pure argv prefix (the jail is destroyed).
        TetherClosed: `tether` has already ended (the jail is destroyed).
        WorkloadSpawnFailed: the argv could not be spawned in the jail (the jail is destroyed).
        OSError: the jail directory or a record could not be written.
    """
    jail = Jail.create(
        compiled,
        runtime=HostRuntime(),
        cwd=cwd,
        jail_id=jail_id,
        jail_dir=jail_dir,
        tether=tether,
        told=told,  # never a warning on the stderr of a terminal the app owns
    )
    try:
        return jail, _started_in(jail, argv_for, cwd=cwd)
    except BaseException as error:
        try:
            report = jail.destroy()
        except Exception as failed:
            error.add_note(
                f"ending jail {jail_id} after its refused start failed too ({failed!r}): what it "
                f"started may still run; look for its processes in {jail_dir} and end them"
            )
        else:
            for note in _unended(jail_id, report.items):
                error.add_note(note)
        raise


def _outside(argv: Sequence[str], spec: Spec) -> tuple[str, ...]:
    """The absolute paths `argv` names that a jail compiled to `spec` neither reads nor writes: what
    a program started in it could not reach. A shared jail's reads are decided when it is created,
    so a later start never adds to them, and one that names these is refused. Pure."""
    roots = (*spec.fs.read_allows, *spec.fs.write_allows)
    named = (arg for arg in argv if arg.startswith("/"))
    return tuple(
        path
        for path in named
        if not any(PurePosixPath(os.path.normpath(path)).is_relative_to(r) for r in roots)
    )


def _unreachable_message(paths: Sequence[str], cwd: str) -> str:
    """What an owner reads when a start names what the session's jail can't reach."""
    return (
        f"runner:confined cannot start this program in the session's jail for {cwd}: it names "
        f"{', '.join(paths)}, which that jail does not read. A jail's reads are decided when it is "
        "created and never widened by a later start. Put the program in a directory bh-02's own "
        "code is in (`host.code`), or under the project"
    )


def _unended(jail_id: str, items: Sequence[KillItem]) -> tuple[str, ...]:
    """What the person must know of a jail ended after a refused start: one line for each item
    brig's teardown neither ended nor found gone, with its detail; nothing when all went."""
    return tuple(
        f"ending jail {jail_id} after its refused start left its {item.kind} {item.identity} "
        f"{item.outcome.value}: {item.detail}; end it yourself (`kill -KILL -- -{item.identity}` "
        "for a process group)"
        for item in items
        if item.outcome not in (KillOutcome.ENDED, KillOutcome.ALREADY_GONE)
    )


class BrigJail:
    """The confined runner's mechanism (`runner.Mechanism`): brig's preset for this platform.

    `lock` is the path of the jail lock (Linux). Left out, it is the user's one bh-02 lock
    (`/tmp/bh-02-jails-<uid>.lock`), which every bh-02 session of the user shares, so a jail sweeps
    what another session's jails left and none removes a placeholder while another runs. Only tests
    pass one of their own (a `tmp_path`), so that another session's jail running on the person's
    machine can't hold the lock out from under them.

    `interpreters` (Linux) are the Pythons brig's supervisor may run under, best first: left out,
    the host's own (`host_interpreters`); each compile takes the first the jail mounts
    (`supervisor_interpreter`). Only tests pass any, to stand for a host whose Python is elsewhere.
    """

    def __init__(
        self,
        config: BrigConfig,
        host: Host,
        *,
        platform: str = host_platform,
        lock: str | None = None,
        interpreters: Sequence[str] | None = None,
        note: str = "",
    ) -> None:
        self._config = config
        self._host = host
        self._note = note
        self._platform = platform
        self._lock = lock if lock is not None else _LOCK.format(uid=os.getuid())
        self._interpreters = host_interpreters() if interpreters is None else tuple(interpreters)
        # The grades are known before anything starts: compile once against a throwaway directory.
        # A platform brig has no preset for grades nothing; `start` says what to use instead.
        # What a jail is (its own grades among it) is kept with it (`_Facts`).
        self._report: Mapping[str, str] = {}
        # every jail that may still run; the shared one for each directory, what the next start
        # there joins; the starts under way, which `release` waits for; and what makes one start at
        # a time choose a jail, so two owners starting at once share one
        self._held: list[_Held] = []
        self._shared: dict[str, _Held] = {}
        self._starting: set[asyncio.Future[None]] = set()
        self._choosing = asyncio.Lock()
        if platform in _STACKS:
            with tempfile.TemporaryDirectory(prefix="bh-j-", dir="/tmp") as probe:
                self._report = self.compile(probe, ".", ())[1]

    def report(self) -> Mapping[str, str]:
        """The grades, known before anything starts (what `approval` reads); no start changes
        them. A started program's jail's are its `report()`."""
        return self._report

    async def __aenter__(self) -> BrigJail:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """End every jail, whatever runs in it: for the runner row's own end, by when the rows that
        depend on it have stopped their programs. A shared jail outlives its programs (the next one
        starts in it), and this is what ends it, so what it made on the host goes with it."""
        await asyncio.gather(*self._starting)
        async with self._choosing:
            for held in self._held:
                await held.end()
            self._held = []
            self._shared = {}

    async def release(self) -> str:
        """For `/release`, once each owner has stopped its own program (`runner.Runner`): wait
        for a start under way, end every jail nothing runs in (the next start creates one), sweep
        what jails that are gone left, and say whether a program still runs (`released_for`), whose
        jail stays. Empty when there is nothing to say."""
        await asyncio.gather(*self._starting)  # a start under way: its placeholders made first
        async with self._choosing:
            running = [
                held
                for held in self._held
                if not held.over and any(not program.stopped for program in held.programs)
            ]
            for held in self._held:
                if held not in running:
                    await held.end()
            self._held = running
            self._shared = {cwd: held for cwd, held in self._shared.items() if held in running}
        await asyncio.to_thread(self._swept, records_dir(os.environ, str(Path.home())))
        return released_for(running=bool(running))

    async def start(self, argv_for: ArgvFor, *, cwd: str) -> _Jailed:
        """Start `argv_for(path)` in `cwd`, `path` the socket reserved for the program
        (reserve-then-start, `_started_in`): in the shared jail for `cwd` if there is one that can
        take it, else in a new jail compiled from the policy, which only a program with namespaces
        of its own shares with those after it (the module's docstring).

        Raises:
            RuntimeError: this platform has no preset, the jail can't start here, its program never
                listened, or `argv_for` names what the shared jail can't reach (`_outside`).
        """
        starting: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._starting.add(starting)
        try:
            async with self._choosing:
                held, process = await self._placed(argv_for, cwd=cwd)
                started = _Jailed(held, process)
                held.programs.append(started)
            await self._until_ready(started, process)
            return started
        finally:
            self._starting.discard(starting)
            if not starting.done():  # a `release` cancelled as it waited cancels it
                starting.set_result(None)

    async def _until_ready(self, started: _Jailed, process: Process) -> None:
        """Readiness through the same verified dial as `connect` (decision-185): a planted link, or
        an answer from outside the process's own group, refuses at once rather than waiting out
        the timeout (decision-186).

        Raises:
            RuntimeError: the program never listened; it is stopped first.
        """
        try:
            await asyncio.to_thread(process.wait_ready, _READY_TIMEOUT_S)
        except BaseException as error:
            log = Path(process.stderr_path)
            detail = log.read_text(errors="replace")[-2000:] if log.is_file() else ""
            await started.stop()
            raise RuntimeError(f"the jailed program never listened: {error}\n{detail}") from error

    async def _placed(self, argv_for: ArgvFor, *, cwd: str) -> tuple[_Held, Process]:
        """A jail for `argv_for` and its program started there: the shared one for `cwd` while it
        can take one, else a new one. A shared jail found over, or that ends as this start asks,
        is ended, and this start goes to a new one: no owner's start fails for that.

        Raises:
            RuntimeError: `argv_for` names what the shared jail can't reach (`_outside`).
        """
        where = str(Path(cwd).resolve())
        held = self._shared.get(where)
        if held is not None and held.usable():
            unreachable = _outside(tuple(argv_for("")), held.jail.spec)
            if unreachable:
                raise RuntimeError(_unreachable_message(unreachable, where))
            with contextlib.suppress(SupervisorGone, SupervisorUnresponsive, TetherClosed):
                return held, await asyncio.to_thread(_started_in, held.jail, argv_for, cwd=cwd)
        if held is not None:
            del self._shared[where]
            await held.end()
            self._held = [each for each in self._held if each is not held]
        held, process = await self._launched(argv_for, cwd=cwd)
        self._held = [*(each for each in self._held if not each.over), held]
        held.shared = process.namespaces
        if held.shared:
            self._shared[where] = held
        return held, process

    async def _launched(self, argv_for: ArgvFor, *, cwd: str) -> tuple[_Held, Process]:
        stack_for(self._platform)  # refuses on a platform brig has no preset for
        if self._platform == "linux" and not Path(DEFAULT_BWRAP_PATH).exists():
            raise RuntimeError(
                "runner:confined runs programs under bubblewrap on Linux, and there is no "
                f"{DEFAULT_BWRAP_PATH}: "
                "install the `bubblewrap` package, or use `runner:unconfined` for the runner row "
                "(or `bh-02 --no-jail`), knowing it confines nothing"
            )
        # Before anything looks at the filesystem: no placeholder may be removed from here on
        # (but those of jails that are gone, which `_hold` removes first when none is running).
        records = records_dir(os.environ, str(Path.home()))
        lock: int | None = await asyncio.to_thread(self._hold, records)
        jail_dir = tempfile.mkdtemp(prefix="bh-j-", dir="/tmp")
        record: str | None = None
        placed: list[tuple[str, str]] = []
        wire: Tripwire | None = None
        # The jail ends with this process, however it ends (`_Held`). os.pipe's ends are not
        # inherited, so no other child of bh-02 (the Claude Code CLI) holds the write end.
        watched, tether = os.pipe()
        try:
            author = git_author(*self._git_identity(cwd)) if self._platform == "linux" else ()
            # A preview of the argv, the reserved path not chosen yet (`""`, which `readable_roots`
            # and `_linked_dirs` skip: neither names an absolute path): what the compile grants on
            # Linux is the program's own directories, never one a channel will bind on its own.
            preview = tuple(argv_for(""))
            jail, report = self.compile(jail_dir, cwd, preview, author)
            absent = self._absent_secrets(jail.spec)
            facts = self._facts(jail.spec, report, absent, jail_dir)
            absent_holds = self._absent_denies if self._platform == "linux" else self._absent_pins
            made = made_by_the_jail(absent_holds(jail.spec))
            if made:
                # Recorded before anything is made, each by the mark it will carry, then made and
                # marked one by one, parents first, and recorded as made: a crash at any point
                # leaves a record whose every directory is either provably the jail's or kept.
                jail_id = Path(jail_dir).name
                record = self._recorded(records, jail_id, [(path, f"mark:{jail_id}") for path in made])
                for path in reversed(made):
                    known = _place(path, jail_id)
                    if known is not None:
                        placed.insert(0, (path, known))
                if record is not None:
                    self._recorded(records, jail_id, placed)
            if self._platform == "linux":
                # After the placeholders are made, before bubblewrap mounts over them: from here
                # on, the host undoing a mount is seen.
                wire = Tripwire(tripwired(jail.spec, absent))
            lost: list[str] = []
            launching = asyncio.ensure_future(
                asyncio.to_thread(
                    _launch,
                    jail,
                    argv_for=argv_for,
                    cwd=cwd,
                    jail_id=Path(jail_dir).name,
                    jail_dir=jail_dir,
                    tether=watched,
                    told=lost.append,
                )
            )
            try:
                running, process = await asyncio.shield(launching)
            except asyncio.CancelledError:
                # The launch's thread runs on whatever happens here: wait for it before its fds
                # are closed and its placeholders removed, and end what it started. A launch that
                # raised has nothing to end here: `_launch` destroyed its jail before raising.
                with contextlib.suppress(Exception):
                    await asyncio.to_thread((await launching)[0].destroy)
                raise
        except BaseException:
            if wire is not None:
                wire.stop()
            if lock is not None:
                _clear_up(lock, placed, record)  # bubblewrap never ran: nothing is mounted on them
                os.close(lock)
            os.close(tether)
            shutil.rmtree(jail_dir, ignore_errors=True)
            raise
        finally:
            os.close(watched)
        if wire is not None:
            wire.arm(
                lambda: still_running(running.destroy(grace=0.0)),
                fallback=lambda: os.killpg(running.instance_group or process.pid, signal.SIGKILL),
            )
        if lost:
            facts = replace(facts, notice="\n".join(filter(None, (facts.notice, *map(_lost_for, lost)))))
        return _Held(running, process, facts, jail_dir, placed, lock, record, tether, wire), process

    def compile(
        self,
        jail_dir: str,
        cwd: str,
        argv: Sequence[str],
        author: Sequence[tuple[str, str]] = (),
    ) -> tuple[CompiledJail, Mapping[str, str]]:
        """The jail for `argv` in `cwd`, compiled, and its grades. `argv` is the program's command
        with an empty path where its socket goes (`argv_for("")`: the socket is reserved only
        once the jail exists, `_launch`): the directories `readable_roots` grants on Linux are its
        own, never a path a channel will bind, which the mechanism grants on its own
        (decision-186). `author` (Linux: `git_author`)
        is set in the worker's environment besides the policy's own.

        Raises:
            RuntimeError: on Linux, no Python the jail mounts is among the interpreters
                (`_no_python_message`); brig's `InterpreterNotMounted` is its cause.
        """
        scratch = str(Path(jail_dir, "tmp"))
        Path(scratch).mkdir(parents=True, exist_ok=True)
        host = [str(Path(p).resolve()) for p in (*import_path, prefix) if p]
        names = (host_executable, str(Path(base_prefix, "bin", "python3")))  # how the host reaches its Python
        spec = spec_for(
            root=cwd,
            scratch=scratch,
            home=str(Path.home()),
            config=self._config,
            layers=self._host.paths,
            host=host,
            secrets=self._host.secrets,
            trusted=self._host.trusted,
            code=self._host.code,
            interpreters=_interpreter_files(names),
            links=_links_on_the_way(names),
            memory=self._host.auto_memory,
        )
        python = DEFAULT_INTERPRETER
        if self._platform == "linux":
            readable = readable_roots(
                argv=argv, interpreter=(base_prefix, prefix), system=SYSTEM_READABLE, code=self._host.code
            )
            links = [link for arg in argv if arg.startswith("/") for link in self._linked_dirs(arg)]
            spec = allowlisted(spec, [p for p in (*readable, *links) if Path(p).exists()])
            denies = uncovered(mountable(spec.fs.write_denies, self._instead(spec)))
            spec = replace(spec, fs=replace(spec.fs, write_denies=denies))
            spec = replace(spec, env=replace(spec.env, set=(*spec.env.set, *author)))
            python = supervisor_interpreter(
                _present(self._interpreters),
                spec.fs.read_allows,
                writable=spec.fs.write_allows,
                denied=spec.fs.write_denies,
            )
        ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=self._platform)
        try:
            jail = stack_for(self._platform, python).compile(spec, ctx=ctx)
        except InterpreterNotMounted as error:
            raise RuntimeError(_no_python_message(self._interpreters, python)) from error
        report = {axis.value: grade.grade.value for axis, grade in jail.report.axes.items()}
        holds = held(spec, self._absent_secrets(spec)) if self._platform == "linux" else ()
        return jail, graded(report, holds)

    def _facts(self, spec: Spec, report: Mapping[str, str], absent: Collection[str], jail_dir: str) -> _Facts:
        """What a jail compiled to `spec` (in `jail_dir`; `absent`, the read denies that are not
        there) is, for every program in it: its grades, its notice, the trees it reads (Linux) and
        the roots it may write but its scratch. The program's reserved socket lives in `jail_dir`
        (brig's own channel directory, decision-186), so excluding `jail_dir` excludes it too;
        `spec.fs.write_allows` never names it (the mechanism grants it on its own)."""
        writes = tuple(w for w in spec.fs.write_allows if not Path(w).is_relative_to(jail_dir))
        if self._platform != "linux":
            return _Facts(report, self._note, writes=writes)
        trees = (*spec.fs.read_allows, *spec.fs.write_allows)
        return _Facts(
            report,
            "\n".join(filter(None, (self._note, notice_for(self._platform, held(spec, absent))))),
            told_reads(trees, (jail_dir,)),
            writes,
        )

    def _linked_dirs(self, path: str) -> list[str]:
        """Every symlinked directory on the way to `path`, following its links. bubblewrap mounts
        a tree at the path the Spec spells, so a tree reached through a link must be named as
        the link too: a uv venv's `python` points into `cpython-3.15-...`, a link to the
        `cpython-3.15.0rc2-...` that `sys.base_prefix` names (measured: without it the worker's
        exec fails with "No such file or directory")."""
        found: list[str] = []
        hop = os.path.abspath(path)
        for _ in range(40):  # the kernel's own limit on links in one lookup
            parts = Path(hop).parts
            at = next(
                (Path(*parts[:i]) for i in range(2, len(parts) + 1) if Path(*parts[:i]).is_symlink()), None
            )
            if at is None:
                return found
            if at != Path(hop):
                found.append(str(at))
            hop = os.path.normpath(Path(at.parent, os.readlink(at), Path(hop).relative_to(at)))
        return found

    def _git_identity(self, cwd: str) -> tuple[str, str]:
        """`user.name` and `user.email` as git resolves them on the host for `cwd` (the
        project's own config over the person's global one); empty when git or either is
        missing, and then a jailed commit says what git says without them."""
        git = shutil.which("git")
        if git is None:
            return "", ""
        found = []
        for key in ("user.name", "user.email"):
            try:
                done = subprocess.run(
                    [git, "config", "--get", key], cwd=cwd, capture_output=True, text=True, timeout=5
                )
            except OSError, subprocess.SubprocessError:
                found.append("")
            else:
                found.append(done.stdout.strip() if done.returncode == 0 else "")
        return found[0], found[1]

    def _hold(self, records: str) -> int:
        """A shared hold on this user's bh-02 jail lock (see `_Jailed`), waiting while a jail
        that is removing its placeholders holds it exclusively. Taken exclusively first when it
        can be: then no bh-02 of this user holds a jail, and every record left (a crashed
        session's, or one that stopped while another ran) names placeholders that are removed
        with it, unless the bubblewrap process group it names still runs. The lock dies with
        bh-02 at once, its jail a moment later (the tether's watcher kills it), and until then
        its mounts are there, which removing a placeholder would detach. The hold is then made
        shared (not atomically: in between another jail may take it
        exclusively, which only removes its own)."""
        lock = os.open(self._lock, os.O_RDWR | os.O_CREAT, 0o600)
        self._sweep(lock, records)
        fcntl.flock(lock, fcntl.LOCK_SH)
        return lock

    def _sweep(self, lock: int, records: str) -> None:
        """Take `lock` exclusively if it can be, and then remove what every record left in
        `records` names, but those whose jail still runs (`_hold`). A jail is its instance's
        process group (`_Jailed._write`), not a program's pid: it lives as long as the jail's
        namespaces do, whatever its programs do, and a group outlives its leader.
        `group_alive` counts a zombie as gone and a process table it can't read as
        running, so only what is proved dead is removed; a pid reused as a group since reads as
        alive, which only keeps placeholders longer."""
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        for left in sorted(Path(records).glob("*.json")) if Path(records).is_dir() else ():
            with contextlib.suppress(OSError):
                text = left.read_text()
                group = recorded_group(text)
                if group is not None and group_alive(group):
                    continue  # its bh-02 is gone, but the jail is not: what it holds stays
                remove_placeholders(recorded(text))
                left.unlink()

    def _swept(self, records: str) -> None:
        """`_sweep` with a hold of its own, let go of at once: for `release`, with no jail of
        this one's running."""
        lock = os.open(self._lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            self._sweep(lock, records)
        finally:
            os.close(lock)

    def _recorded(self, records: str, jail_id: str, made: Sequence[tuple[str, str]]) -> str | None:
        """Write this jail's record of `made` (`record_text`) and return its path; None when the
        state directory can't be written (then only this jail's own `stop` removes them)."""
        record = Path(records, f"{jail_id}.json")
        try:
            record.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            record.write_text(record_text(made))
        except OSError:
            return None
        return str(record)

    def _instead(self, spec: Spec) -> dict[str, str]:
        """Each absent write deny whose nearest existing ancestor is a file, mapped to that file;
        and each whose parent is absent too, under a write root, mapped to its topmost absent
        ancestor (see `mountable`)."""
        roots = [Path(r) for r in spec.fs.write_allows]
        instead: dict[str, str] = {}
        for deny in spec.fs.write_denies:
            path, top = Path(deny), Path(deny)
            while not path.exists() and path != path.parent:
                top, path = path, path.parent
            if str(path) != deny and path.exists() and not path.is_dir():
                instead[deny] = str(path)
            elif str(top) != deny and any(top.is_relative_to(r) and top != r for r in roots):
                instead[deny] = str(top)
        return instead

    def _absent_secrets(self, spec: Spec) -> frozenset[str]:
        """The read denies that are not there, by the test brig's compile uses to choose what it
        masks (`os.path.exists`): nothing masks one, so a jail holds it only where no input can
        create it (`held`)."""
        return frozenset(d for d in spec.fs.read_denies if not os.path.exists(d))

    def _absent_pins(self, spec: Spec) -> list[str]:
        """Every directory between a write root and a write deny under it (brig's `pins`) that
        does not exist: what a darwin jail makes on the host before its program starts, so that
        seatbelt's pin on it refuses a rename onto it (brig decision-208). Each one, not only the
        topmost: a deeper one left absent could still be renamed onto."""
        return [
            path for path in pins(spec.fs.write_allows, spec.fs.write_denies) if not os.path.lexists(path)
        ]

    def _absent_denies(self, spec: Spec) -> list[str]:
        """Every write-denied path under a write root that does not exist, and each of its
        missing parents: what bubblewrap will create on the host to mount over."""
        roots = [str(Path(r).resolve()) for r in spec.fs.write_allows]
        absent: list[str] = []
        for deny in spec.fs.write_denies:
            path = Path(deny).resolve()
            if not any(path.is_relative_to(r) and str(path) != r for r in roots):
                continue
            while not path.exists() and str(path) not in roots:
                absent.append(str(path))
                path = path.parent
        return absent
