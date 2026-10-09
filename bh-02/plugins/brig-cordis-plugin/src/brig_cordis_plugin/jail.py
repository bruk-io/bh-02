"""The `jail` value over brig: a Spec built from where the work is, compiled, launched, graded.

`spec_for` is the whole policy as a pure function. What an input may write: the project root
(`write`) and a scratch directory of the jail's own. What it may not, even inside those: the
composition's layer files (an input rewriting one would reshape the program running it, outside
the jail), every path the host imports code from (`sys.path` entries and the interpreter's
prefix), the directory of every package bh-02 runs code from (`code`: bh-02's own, cordis's,
brig's and each plugin's, as installed; under a writable root when bh-02 works on its own
checkout, an editable install), whose modules bh-02 imports in its own process, brig's own
self-modification list (`.git/hooks`, `.git/config`, shell rc
files, CLAUDE.md, ...), any secret below under a writable root (it may not replace what it can't
read), and bh-02's configuration directories under one (`trusted`: the person's
`$XDG_CONFIG_HOME/bh-02` and `~/.config/bh-02`, when bh-02 runs from the home directory), whose
models file and startup file a later session reads on the host and trusts. What
it may not read: brig's credential list under the home directory, `hide`
under the project, and what the `layers` value names as `secrets` (bh-02's own `local.env`,
wherever bh-02 runs from, and the sessions' state, where Claude Code keeps its tokens). No
network: the kernel's own socket is the one way in or out. The worker's environment is scrubbed
to a short allowlist. brig's host process, which starts the worker from outside the jail,
keeps bh-02's own environment: brig's launcher composes `{**os.environ, **jail.env}` by its
spec, and `jail.env` can add keys but not remove them. So a variable of the launching shell (a
`CLAUDE_*` of a Claude Code that launched bh-02, say) sits in that process, out of an input's
reach (in the jail, `ps` fails with a permission error; measured). bh-02's own token is never there: it goes
only to the Claude Code child.

One policy, two platforms; only the stack and the read model differ:

- darwin: brig's `scratch_darwin()` (seatbelt). Reads by denylist, which is `spec_for` as it is:
  everything but the secrets.
- Linux: brig's `strict_linux()` (bubblewrap). Reads by allowlist, so `allowlisted` turns the
  policy into one: what is readable is the system tree (`/usr`, `/etc`, ...), the interpreter
  (`sys.base_prefix`, `sys.prefix`), the directories the command names, and what the policy
  lets an input write. Everything else does not exist in the jail, the home directory included.
  The secrets stay `read_denies`, now brig's carve-outs: one inside that tree (a `local.env` at
  the project root) is masked if it exists, and one that does not exist yet is not, which
  brig's `fs_read` grade says (`best_effort`, naming it); an absent one where bh-02 looks for
  its credential (`layers.credentials`) keeps its write deny, so an input can't plant one there.
  bubblewrap holds each absent write-denied path (`.envrc`, `.vscode`, such a `local.env`, ...)
  by mounting over an empty directory on the host, which the jail makes (and marks as its own)
  before bubblewrap starts; the jail removes the ones it made once brig has verified the worker
  is gone, never before (a mount point removed while the
  jail lives is detached inside it). A mount can be undone from the host (a file renamed over
  a denied or masked one, as a host `git config` does to `.git/config`; a placeholder removed),
  and from then on an input could write or read that path. So the jail watches every path it
  holds (`tripwired`, `tripwire.Tripwire`; never one an input may create, as the project's own
  absent `local.env`) and ends itself at the first such change: the next
  input's jail holds the path again, and the input says why (`ended`). Until it has ended (a few
  milliseconds; measured in the README) a program already running in it can get one write or
  read in, so while the jail holds a secret under a writable root `fs_read` stays best-effort
  (`graded`) and `notice()` says which paths (`held`, `notice_for`).

On both, the jail is launched tethered to bh-02 (`_Jailed`): when bh-02 ends, however it ends,
brig kills the jail's process group, so a program an input left running doesn't outlive it (on
Linux, bubblewrap's whole namespace; on darwin, what stayed in the group).

Anywhere else `start` refuses and names `kernel:unjailed`.
"""

import asyncio
import contextlib
import fcntl
import json
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from sys import base_prefix, prefix
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
from brig.mech.bwrap import DEFAULT_BWRAP_PATH
from brig.run import Handle, IoPolicy, KillOutcome, SubprocessLauncher, build_compile_ctx
from brig.stack import CompiledJail, Stack, scratch_darwin, strict_linux
from brig_cordis_plugin.tripwire import Tripwire

__all__ = [
    "MARK",
    "SYSTEM_READABLE",
    "BrigConfig",
    "BrigJail",
    "Layers",
    "allowlisted",
    "git_author",
    "graded",
    "held",
    "holding",
    "identity",
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
    "told_reads",
    "tripwired",
    "uncovered",
]

_READY_TIMEOUT_S = 10.0

#: The system tree a Linux jail may read: what the interpreter links against and reads at
#: start (`/lib`, `/usr/lib`, `/etc/ld.so.cache`, locale data) and what an input runs (`/bin/sh`,
#: `git`, ...). Entries that do not exist on a host (`/lib64` on arm64) are dropped at start.
SYSTEM_READABLE: tuple[str, ...] = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc")

_STACKS: Mapping[str, Callable[[], Stack]] = {"darwin": scratch_darwin, "linux": strict_linux}


@runtime_checkable
class Layers(Protocol):
    """What the jail needs of the `layers` value (CONTRACTS.md: layers): the composition's files,
    which an input may not write; where bh-02 looks for its credential, where an input may
    create nothing; the secrets, which it may not read; bh-02's configuration directories
    (`trusted`), whose files the host reads and trusts, which it may not write; the directories
    bh-02 runs its own code from (`code`), which it may not write either; and the project's auto
    memory directory (`memory`), which it may write ('' for none)."""

    @property
    def paths(self) -> tuple[str, ...]: ...
    @property
    def credentials(self) -> tuple[str, ...]: ...
    @property
    def secrets(self) -> tuple[str, ...]: ...
    @property
    def trusted(self) -> tuple[str, ...]: ...
    @property
    def code(self) -> tuple[str, ...]: ...
    @property
    def memory(self) -> str: ...


@dataclass(frozen=True, slots=True)
class BrigConfig:
    """`write`: where an input may write besides its scratch dir (relative to the kernel's root).
    `deny`: more paths it may not write. `allow`: names from brig's self-modification list
    (`SELF_MODIFY_WORKSPACE_RELATIVE`: `.git/hooks`, `CLAUDE.md`, ...) an input may write after all;
    by default the project's guidance files, which editing is ordinary work. The rest stay denied:
    they can run code outside the jail later (hooks, shell rc files, editor and Claude settings).
    `hide`: paths it may not read (relative to the root): a project's `local.env` may hold a
    credential. `env`: the variables that survive the scrub."""

    write: Sequence[str] = (".",)
    deny: Sequence[str] = ()
    allow: Sequence[str] = ("CLAUDE.md", "AGENTS.md")
    hide: Sequence[str] = ("local.env",)
    env: Sequence[str] = ("PATH", "HOME", "LANG", "LC_ALL", "TERM")


def spec_for(
    *,
    root: str,
    endpoint: str,
    scratch: str,
    home: str,
    config: BrigConfig,
    layers: Sequence[str],
    host: Sequence[str],
    secrets: Sequence[str] = (),
    trusted: Sequence[str] = (),
    code: Sequence[str] = (),
    memory: str = "",
) -> Spec:
    """The jail's Spec. `host` is every path the host process loads code from; any under a
    writable root is denied, as are the layer files and brig's self-modification list.
    `secrets` (absolute) may not be read, wherever they are. `trusted` (absolute directories:
    bh-02's configuration, whose files the host reads and trusts) and `code` (absolute: the
    directory of every package bh-02 runs code from) may not be written where they are under a
    writable root. `memory` (absolute: the project's auto memory directory, '' for none) may be
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
    # root (the project's `local.env`) is denied writing too, or an input could replace the
    # credential it can't see.
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
    denies = [
        *layers,
        *under,
        *selfmod,
        *(str(Path(root, d).resolve()) for d in config.deny),
        *kept,
        *configured,
        *running,
    ]
    return Spec(
        fs=FsPolicy(
            write_allows=tuple(writable),
            write_denies=tuple(dict.fromkeys(denies)),
            read_denies=(
                *(str(Path(home, name)) for name in CREDENTIAL_READ_DENIES_HOME_RELATIVE),
                *hidden,
            ),
        ),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=tuple(config.env), set=(("TMPDIR", scratch),)),
        channels=(Channel(name="kernel", kind=ChannelKind.LISTEN, endpoint=endpoint),),
    )


def allowlisted(spec: Spec, readable: Sequence[str], hold: Collection[str] = ()) -> Spec:
    """`spec`, reading by allowlist: `readable` is the tree an input may read, and the policy's
    read denies become the carve-outs inside it. The environment and the channel are the
    policy's, unchanged, and so are the writes but one kind: a path denied both reading and
    writing (a secret under the project) keeps only its read deny. bwrap masks an existing one
    with a read-only `/dev/null`, which refuses writes and removal too (a write deny as well
    would be a bind of the real file, under the mask). An absent one has nothing to mask, so a
    input could create it: those in `hold` (absent places bh-02 looks for its credential, where a
    planted `local.env` would be read at the next launch) keep their write deny, an empty
    directory held read-only there for the session (`made_by_the_jail`). The rest (the project's
    own absent `local.env`) are left alone: a directory there would be in the person's way, and
    nothing of bh-02's reads one."""
    return replace(
        spec,
        fs=FsPolicy(
            write_allows=spec.fs.write_allows,
            write_denies=tuple(d for d in spec.fs.write_denies if d not in spec.fs.read_denies or d in hold),
            read_model=ReadModel.ALLOW_LIST,
            read_allows=tuple(readable),
            read_denies=spec.fs.read_denies,
        ),
    )


def readable_roots(
    *, argv: Sequence[str], interpreter: Sequence[str], system: Sequence[str]
) -> tuple[str, ...]:
    """What a Linux jail reads besides what it may write: the system tree, the interpreter's
    trees (the standard library under `sys.base_prefix`, the environment under `sys.prefix`),
    and the directory of every absolute path the command names (the worker program's own). Not
    the host's whole `sys.path`: under pytest or `python -m` it holds the workspace root, and
    with it the workspace's `local.env`, for nothing a stdlib-only worker needs."""
    named = [str(Path(arg).parent) for arg in argv if arg.startswith("/")]
    return tuple(dict.fromkeys([*system, *interpreter, *named]))


def uncovered(denies: Sequence[str]) -> tuple[str, ...]:
    """The write denies that no other one contains. bubblewrap mounts each in turn, and one
    inside a directory already bound read-only (an absent secret under a directory the host
    imports code from) would need a mount point made on a read-only mount, which fails the
    launch; the outer deny holds it already."""
    return tuple(d for d in denies if not any(d.startswith(o + "/") for o in denies if o != d))


def held(spec: Spec, absent: Collection[str]) -> tuple[str, ...]:
    """The read denies a Linux jail (`spec`, `allowlisted`) holds at or under a root an input
    may write: one that is there (not in `absent`), which bubblewrap masks with a mount on the
    path itself, and an absent one no input can create, at or under a write deny (the empty
    directory where bh-02 looks for its credential, or a directory bound read-only), where only
    the host could put a file, which the jail could then read. A mount is on the host's
    directory entry, so replacing that entry on the host (an editor saves by renaming a new file
    over it) or removing it detaches the mount inside the jail, and an input can then read and
    rewrite what is there (measured). Not an absent one nothing holds (the project's own
    `local.env`): an input may create it, and a file the host creates there is readable, which
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
        "on each path that is there, and, where bh-02 looks for its credential and there is none, "
        "with an empty directory, so nothing can be created there while the kernel runs: "
        "`/release` stops the kernel and frees it until the next input, which is when to add your "
        "credential. The host can undo a mount: when a file is created at one of these paths, or "
        "replaced (an editor saves local.env by renaming a new file over it) or removed while the "
        "kernel runs, bh-02 ends the jail at once (a running input with it) and the next input's "
        "jail holds the path again. A program an input left running can still read or rewrite it "
        "in the milliseconds that takes, so edit them after `/release`."
    )


def holding(credentials: Sequence[str], denies: Sequence[str]) -> tuple[str, ...]:
    """The places bh-02 looks for its credential that a Linux jail holds with an empty
    directory (`allowlisted`'s `hold`): those still among its write denies, which it mounts."""
    return tuple(c for c in credentials if c in denies)


def released_for(free: Sequence[str], still: Sequence[str], others: bool = False) -> str:
    """What `/release` tells the person: where bh-02 looks for its credential and nothing holds
    now, what another session's jail still holds, and (`others`) that the release stopped a
    program besides the kernel's worker: the extensions' worker, which starts again once the
    next input has started the kernel."""
    said = []
    if free:
        said.append(
            f"Nothing holds {', '.join(free)} until the kernel starts again: create your local.env "
            "there now, then send your message. The next kernel's jail masks it from inputs (a model "
            "already running keeps the credential it started with: `/restart model`)."
        )
    if still:
        said.append(
            f"{', '.join(still)} stays held: another bh-02 session of yours is running a jail, and "
            "none removes a placeholder while another runs. Quit that session, then /release again."
        )
    if others:
        said.append(
            "The extensions' worker stopped too, and what the extensions added with it: they load "
            "again once the next input has started the kernel."
        )
    return " ".join(said)


def told_reads(trees: Sequence[str], own: Sequence[str]) -> tuple[str, ...]:
    """The trees a jail reads, as the model is told them: each once, the jail's own directories
    (its scratch and the kernel's socket, named anew at every start) as `$TMPDIR` alone, so the
    prompt is the same from one kernel to the next (the claude-code provider starts Claude Code
    again when it changes)."""
    kept = [t for t in trees if not any(t == o or t.startswith(o + "/") for o in own)]
    return (*dict.fromkeys(kept), "$TMPDIR")


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
    paths (each path and each missing parent; `absent` lists them all), deepest first: the order
    they can be removed in once the jail is gone (and, reversed, made in)."""
    return tuple(sorted(set(absent), key=lambda p: (-p.count("/"), p)))


def stack_for(platform: str) -> Stack:
    """brig's preset for `platform`, or a refusal that says what to use instead."""
    try:
        return _STACKS[platform]()
    except KeyError:
        raise RuntimeError(
            f"brig:jail runs on darwin (seatbelt) and Linux (bubblewrap); this is {platform}. "
            "Use `kernel:unjailed` for the jail row (or `bh-02 --no-jail`), knowing it confines nothing"
        ) from None


def self_modify_denied(allow: Sequence[str]) -> tuple[str, ...]:
    """brig's self-modification list without the names `allow` lets an input write. A name that
    is not on the list is a mistake in the row's config, never silently ignored."""
    unknown = [name for name in allow if name not in SELF_MODIFY_WORKSPACE_RELATIVE]
    if unknown:
        raise ValueError(
            f"the jail row's `allow` names {', '.join(map(repr, unknown))}, which brig does not deny "
            f"in the first place; `allow` takes only names from its self-modification list: "
            f"{', '.join(SELF_MODIFY_WORKSPACE_RELATIVE)}. To let an input write another path, "
            "use `write`"
        )
    return tuple(name for name in SELF_MODIFY_WORKSPACE_RELATIVE if name not in allow)


def mountable(denies: Sequence[str], instead: Mapping[str, str]) -> tuple[str, ...]:
    """The write denies bubblewrap can mount, each once, with `instead` mapping a deny to the
    path denied in its place. An absent one under a path that exists as a FILE (`.git/hooks`
    where `.git` is a worktree's or submodule's `gitdir:` pointer) can't have a mount point made
    for it (bwrap: "Can't mkdir parents ... Not a directory", and the kernel never starts), so it
    maps to that file, bound read-only over itself: neither rewritten nor removed, so nothing is
    ever created under it. An absent one whose parent is absent too (`.git/config` in a project
    that is not a repository) maps to its topmost absent ancestor (`.git`): one empty directory
    held on the host rather than a `.git/config` directory inside one, which would break the
    person's own `git init` there while the kernel runs."""
    return tuple(dict.fromkeys(instead.get(deny, deny) for deny in denies))


def records_dir(environ: Mapping[str, str], home: str) -> str:
    """Where a Linux jail records the placeholders it made, one file per jail: bh-02's state
    directory (`$XDG_STATE_HOME/bh-02`, else `~/.local/state/bh-02`), outside every jail."""
    state = environ.get("XDG_STATE_HOME") or str(Path(home, ".local", "state"))
    return str(Path(state, "bh-02", "jails"))


def identity(found: os.stat_result) -> str:
    """Which directory a placeholder is, where the filesystem takes no `MARK`: its inode and
    when it changed. The inode alone is not enough: a directory removed and made again at the
    same path can get the same one back (measured, on overlayfs). The change time is as fine as
    the kernel's clock tick, so one made again within the same few milliseconds would pass for
    the jail's; and a placeholder something was added to and removed from since (another jail's
    placeholders inside it) reads as changed, and is kept."""
    return f"{found.st_ino}:{found.st_ctime_ns}"


def record_text(made: Sequence[tuple[str, str | None]], group: int | None = None) -> str:
    """A jail's record of its placeholders: each path, deepest first, with how the directory
    there is known to be the jail's (`mark:<jail id>`, else its `identity`), so a later sweep
    removes only a directory the jail made; and once bubblewrap is started, its process group,
    so a sweep never removes what a jail still alive holds."""
    whole: dict[str, object] = {"made": [[path, found] for path, found in made]}
    if group is not None:
        whole["group"] = group
    return json.dumps(whole) + "\n"


def recorded(text: str) -> list[tuple[str, str | None]]:
    """The placeholders a record names (`record_text`); nothing for a record that can't be read
    as one, which is then only removed."""
    try:
        made = json.loads(text)["made"]
        return [(str(path), found if isinstance(found, str) else None) for path, found in made]
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


def still_made(was: str | None, found: str, mark: str | None) -> bool:
    """Whether a directory is still the placeholder a jail recorded as `was`: its `MARK` (the
    jail's id, in an extended attribute the jail set on it as it made it), or where the
    filesystem takes none, its `identity`. A mark survives what is added and removed under it;
    the person's own directory has none. A path recorded alone (None: an older bh-02's record,
    written before its placeholders were marked) proves nothing, so nothing there is removed."""
    if was is None:
        return False
    if was.startswith("mark:"):
        return mark == was.removeprefix("mark:")
    return was == found


def remove_placeholders(made: Sequence[tuple[str, str | None]]) -> None:
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
    """What one start of the jail is, kept with that start for whoever started it (CONTRACTS.md:
    jail): its grades (`graded`), what the person should know about it (`notice_for`), the trees
    its program reads when that is all it reads (`told_reads`: a Linux jail's; empty on darwin)
    and the roots it may write but its scratch. A jail starts more than one program (the
    kernel's worker, the extensions' worker), each from its own command: what one start is never
    replaces what another is."""

    report: Mapping[str, str]
    notice: str = ""
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()


class _Jailed:
    """A program brig started: interrupt is SIGINT to its group, stop is brig's teardown, then
    the directories the jail made on the host (`made`, deepest first) once it is gone. `facts`
    is what this start is (`report`, `notice`, `reads`, `writes`), read whether or not it still
    runs.

    `tether` is the write end of the launch's tether (brig SPEC.md section 8): held by this
    process alone, so when bh-02 ends, however it ends (`SIGKILL` included), the kernel closes
    it and brig's watcher kills the jail's whole process group, a program an input left running
    in the background with it. `stop` closes it once brig's teardown is done.

    `wire` (Linux) watches the paths the jail holds with a mount and ends the jail when the host
    undoes one (`Tripwire`); `ended` says so. `stop` stops it first: removing the placeholders
    would read as the host undoing them.

    `lock` (Linux) is this jail's shared hold on the user's bh-02 jail lock, taken before the
    jail looked at the filesystem and held while it runs. A placeholder is removed only by a
    jail that can then take the lock exclusively: no other bh-02 jail is running, so none has
    mounted over one (a second session in the same project binds the first one's `.claude/`
    read-only, and removing it on the host detaches that bind; measured). `record` is the file
    that names them meanwhile (`records_dir`): if this jail can't remove them (another runs) or
    never stops (bh-02 crashed), the next jail to start with none running does."""

    def __init__(
        self,
        handle: Handle,
        facts: _Facts,
        jail_dir: str,
        made: Sequence[tuple[str, str]],
        lock: int | None,
        record: str | None,
        tether: int | None = None,
        wire: Tripwire | None = None,
    ) -> None:
        self._handle = handle
        self._facts = facts
        self._wire = wire
        self._tether = tether
        self._jail_dir = jail_dir
        self._made: list[tuple[str, str | None]] = list(made)
        self._lock = lock
        self._record = record
        self._stopping: asyncio.Future[None] | None = None
        self._write()

    def interrupt(self) -> bool:
        return self._handle.interrupt()

    def ended(self) -> str:
        """Why the jail ended its program itself (the host undid a mount, `tripped_for`), or ""."""
        return self._wire.tripped if self._wire is not None else ""

    def report(self) -> Mapping[str, str]:
        """This start's grades: brig's, with `fs_read` best-effort while it holds a secret with a
        mount the host can undo (`graded`)."""
        return self._facts.report

    def notice(self) -> str:
        """What the person should know about this start's jail (`notice_for`): on Linux, the
        secrets it holds with a mount the host can undo; empty on darwin."""
        return self._facts.notice

    def reads(self) -> tuple[str, ...]:
        """The trees this start's program can read, when that is all it can read (`told_reads`):
        a Linux jail's allowlist (the system, the interpreter, the program's own directory) and
        the roots it may write. Empty on darwin, whose jail reads everything but the secrets."""
        return self._facts.reads

    def writes(self) -> tuple[str, ...]:
        """The directories this start's program may write, but the jail's own scratch: the
        project and what `write` adds."""
        return self._facts.writes

    def _write(self) -> None:
        """The record as it stands: the placeholders, and which bubblewrap process holds them."""
        if self._record is not None:
            with contextlib.suppress(OSError):
                Path(self._record).write_text(record_text(self._made, self._handle.pgid))

    @property
    def stopped(self) -> bool:
        """Whether it has been stopped, by whoever started it or by the jail's `release`."""
        return self._stopping is not None

    async def stop(self) -> None:
        """brig's teardown, then what the jail made, once: whoever started the program and the
        jail's `release` may both stop it, and the second waits for the first."""
        if self._stopping is None:
            self._stopping = asyncio.ensure_future(self._teardown())
        await asyncio.shield(self._stopping)

    async def _teardown(self) -> None:
        if self._wire is not None:
            await asyncio.to_thread(self._wire.stop)
        report = await asyncio.to_thread(self._handle.kill)
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


def _clear_up(lock: int, made: Sequence[tuple[str, str | None]], record: str | None) -> None:
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


def _lives(group: int) -> bool:
    """Whether any process of the process group `group` still runs. The group outlives its
    leader (bubblewrap's own first process exits; measured), so the group, not the pid. A pid
    reused as a group since reads as alive, which only keeps placeholders longer."""
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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


class BrigJail:
    """Implements `Jail` (CONTRACTS.md: jail) with brig's preset for this platform."""

    def __init__(self, config: BrigConfig, layers: Layers, *, platform: str = host_platform) -> None:
        self._config = config
        self._layers = layers
        self._platform = platform
        # The grades are known before anything starts: compile once against a throwaway directory.
        # A platform brig has no preset for grades nothing; `start` says what to use instead.
        # What each start is (its own grades among it) is kept with that start (`_Facts`).
        self._report: Mapping[str, str] = {}
        # where bh-02 looks for its credential that a jail of this one's has held: what `release`
        # says about, whichever program's jail held it
        self._holding: tuple[str, ...] = ()
        # every program this jail started that may still run, and the starts under way: what
        # `release` stops (it waits for a start under way, then stops what that started)
        self._live: list[_Jailed] = []
        self._starting: set[asyncio.Future[None]] = set()
        self._released = False
        if platform in _STACKS:
            with tempfile.TemporaryDirectory(prefix="bh-j-", dir="/tmp") as probe:
                self._report = self.compile(probe, str(Path(probe, "k.sock")), ".", ())[1]

    def report(self) -> Mapping[str, str]:
        """The grades, known before anything starts (what `approval` reads); no start changes
        them. A started program's own are its `report()`."""
        return self._report

    def released(self) -> bool:
        """Whether `release` has stopped this jail's programs and none has started since. The
        next start ends it, and the next input's is the kernel's worker; a program whose owner is
        not the kernel (the extensions' worker) waits while it holds, or its jail would hold what
        the release freed again before the person could use it. Never on darwin, whose `release`
        stops nothing."""
        return self._released

    async def release(self) -> str:
        """For `/release`, once the kernel has stopped its own worker. On Linux: stop every
        other program this jail started that still runs (the extensions' worker, whose jail holds
        the same placeholders and a share of the jail lock, so while it ran nothing could be
        freed), each stop removing what its jail made once no jail runs; sweep what jails that
        are gone left; and say which places bh-02 looks for its credential are free now, what
        another session's jail still holds, and that the extensions' worker stopped
        (`released_for`). The jail is then `released` until its next start. Empty when there is
        nothing to say, and on darwin, where seatbelt holds a path without anything on the host
        and nothing is stopped."""
        if self._platform != "linux":
            return ""
        self._released = True  # before anything waits: from here on, what asks starts nothing
        await asyncio.gather(*self._starting)  # a start under way: stopped too, once it is up
        running = [started for started in self._live if not started.stopped]
        for started in self._live:
            await started.stop()
        self._live.clear()
        await asyncio.to_thread(self._swept, records_dir(os.environ, str(Path.home())))
        return released_for(
            [p for p in self._holding if not os.path.lexists(p)],
            [p for p in self._holding if Path(p).is_dir()],
            others=bool(running),
        )

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> _Jailed:
        """Start `argv` in `cwd`, in a jail of its own compiled from the policy, listening on
        `endpoint`. A start ends a release (`released`), before anything waits."""
        self._released = False
        starting: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._starting.add(starting)
        try:
            started = await self._launched(argv, cwd=cwd, endpoint=endpoint)
            self._live = [*(each for each in self._live if not each.stopped), started]
            return started
        finally:
            self._starting.discard(starting)
            if not starting.done():  # a `release` cancelled as it waited cancels it
                starting.set_result(None)

    async def _launched(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> _Jailed:
        stack_for(self._platform)  # refuses on a platform brig has no preset for
        if self._platform == "linux" and not Path(DEFAULT_BWRAP_PATH).exists():
            raise RuntimeError(
                f"brig:jail runs the kernel under bubblewrap on Linux, and there is no {DEFAULT_BWRAP_PATH}: "
                "install the `bubblewrap` package, or use `kernel:unjailed` for the jail row "
                "(or `bh-02 --no-jail`), knowing it confines nothing"
            )
        # Before anything looks at the filesystem: no placeholder may be removed from here on
        # (but those of jails that are gone, which `_hold` removes first when none is running).
        records = records_dir(os.environ, str(Path.home()))
        lock = await asyncio.to_thread(self._hold, records) if self._platform == "linux" else None
        jail_dir = tempfile.mkdtemp(prefix="bh-j-", dir="/tmp")
        record: str | None = None
        placed: list[tuple[str, str]] = []
        wire: Tripwire | None = None
        # The jail ends with this process, however it ends (`_Jailed`). os.pipe's ends are not
        # inherited, so no other child of bh-02 (the Claude Code CLI) holds the write end.
        watched, tether = os.pipe()
        try:
            author = git_author(*self._git_identity(cwd)) if self._platform == "linux" else ()
            jail, report = self.compile(jail_dir, endpoint, cwd, argv, author)
            absent = self._absent_secrets(jail.spec)
            facts = self._facts(jail.spec, report, absent, jail_dir, endpoint)
            if self._platform == "linux":
                held_now = holding(self._layers.credentials, jail.spec.fs.write_denies)
                self._holding = tuple(dict.fromkeys((*self._holding, *held_now)))
            made = made_by_the_jail(self._absent_denies(jail.spec)) if self._platform == "linux" else ()
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
            launching = asyncio.ensure_future(
                asyncio.to_thread(
                    SubprocessLauncher().launch,
                    jail,
                    argv=list(argv),
                    cwd=cwd,
                    io=IoPolicy(),
                    jail_id=Path(jail_dir).name,
                    jail_dir=jail_dir,
                    tether=watched,
                )
            )
            try:
                handle = await asyncio.shield(launching)
            except asyncio.CancelledError:
                # The launch's thread runs on whatever happens here: wait for it before its fds
                # are closed and its placeholders removed, and end what it started.
                with contextlib.suppress(Exception):
                    await asyncio.to_thread((await launching).kill)
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
            wire.arm(handle.pgid)
        started = _Jailed(handle, facts, jail_dir, placed, lock, record, tether, wire)
        try:
            await asyncio.to_thread(handle.wait_ready, "kernel", _READY_TIMEOUT_S)
        except BaseException as error:
            log = Path(jail_dir, "stderr.log")
            detail = log.read_text(errors="replace")[-2000:] if log.is_file() else ""
            await started.stop()
            raise RuntimeError(f"the jailed kernel never listened: {error}\n{detail}") from error
        return started

    def compile(
        self,
        jail_dir: str,
        endpoint: str,
        cwd: str,
        argv: Sequence[str],
        author: Sequence[tuple[str, str]] = (),
    ) -> tuple[CompiledJail, Mapping[str, str]]:
        """The jail for `argv` in `cwd`, compiled, and its grades. `author` (Linux: `git_author`)
        is set in the worker's environment besides the policy's own."""
        scratch = str(Path(jail_dir, "tmp"))
        Path(scratch).mkdir(parents=True, exist_ok=True)
        host = [str(Path(p).resolve()) for p in (*import_path, prefix) if p]
        spec = spec_for(
            root=cwd,
            endpoint=endpoint,
            scratch=scratch,
            home=str(Path.home()),
            config=self._config,
            layers=self._layers.paths,
            host=host,
            secrets=self._layers.secrets,
            trusted=self._layers.trusted,
            code=self._layers.code,
            memory=self._layers.memory,
        )
        if self._platform == "linux":
            readable = readable_roots(argv=argv, interpreter=(base_prefix, prefix), system=SYSTEM_READABLE)
            links = [link for arg in argv if arg.startswith("/") for link in self._linked_dirs(arg)]
            hold = [c for c in self._layers.credentials if not Path(c).exists()]
            spec = allowlisted(spec, [p for p in (*readable, *links) if Path(p).exists()], hold)
            denies = uncovered(mountable(spec.fs.write_denies, self._instead(spec)))
            spec = replace(spec, fs=replace(spec.fs, write_denies=denies))
            spec = replace(spec, env=replace(spec.env, set=(*spec.env.set, *author)))
        ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=self._platform)
        jail = stack_for(self._platform).compile(spec, ctx=ctx)
        report = {axis.value: grade.grade.value for axis, grade in jail.report.axes.items()}
        holds = held(spec, self._absent_secrets(spec)) if self._platform == "linux" else ()
        return jail, graded(report, holds)

    def _facts(
        self, spec: Spec, report: Mapping[str, str], absent: Collection[str], jail_dir: str, endpoint: str
    ) -> _Facts:
        """What a start compiled to `spec` (in `jail_dir`, listening on `endpoint`; `absent`, the
        read denies that are not there) is, for whoever started it: its grades, its notice, the
        trees it reads (Linux) and the roots it may write but its scratch."""
        writes = tuple(w for w in spec.fs.write_allows if not Path(w).is_relative_to(jail_dir))
        if self._platform != "linux":
            return _Facts(report, writes=writes)
        trees = (*spec.fs.read_allows, *spec.fs.write_allows)
        return _Facts(
            report,
            notice_for(self._platform, held(spec, absent)),
            told_reads(trees, (jail_dir, str(Path(endpoint).parent))),
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
        lock = os.open(_LOCK.format(uid=os.getuid()), os.O_RDWR | os.O_CREAT, 0o600)
        self._sweep(lock, records)
        fcntl.flock(lock, fcntl.LOCK_SH)
        return lock

    def _sweep(self, lock: int, records: str) -> None:
        """Take `lock` exclusively if it can be, and then remove what every record left in
        `records` names, but those whose jail still runs (`_hold`)."""
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        for left in sorted(Path(records).glob("*.json")) if Path(records).is_dir() else ():
            with contextlib.suppress(OSError):
                text = left.read_text()
                group = recorded_group(text)
                if group is not None and _lives(group):
                    continue  # its bh-02 is gone, but the jail is not: what it holds stays
                remove_placeholders(recorded(text))
                left.unlink()

    def _swept(self, records: str) -> None:
        """`_sweep` with a hold of its own, let go of at once: for `release`, with no jail of
        this one's running."""
        lock = os.open(_LOCK.format(uid=os.getuid()), os.O_RDWR | os.O_CREAT, 0o600)
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
