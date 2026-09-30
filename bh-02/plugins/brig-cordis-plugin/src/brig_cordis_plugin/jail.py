"""The `jail` value over brig: a Spec built from where the work is, compiled, launched, graded.

`spec_for` is the whole policy as a pure function. What a cell may write: the project root
(`write`) and a scratch directory of the jail's own. What it may not, even inside those: the
composition's layer files (a cell rewriting one would reshape the program running it, outside
the jail), every path the host imports code from (`sys.path` entries and the interpreter's
prefix), brig's own self-modification list (`.git/hooks`, `.git/config`, shell rc files,
CLAUDE.md, ...), and any secret below under a writable root (it may not replace what it can't
read). What it may not read: brig's credential list under the home directory, `hide`
under the project, and what the `layers` value names as `secrets` (bh-02's own `local.env`,
wherever bh-02 runs from, and the sessions' state, where Claude Code keeps its tokens). No
network: the kernel's own socket is the one way in or out. The worker's environment is scrubbed
to a short allowlist. brig's host process, which starts the worker from outside the jail,
keeps bh-02's own environment: brig's launcher composes `{**os.environ, **jail.env}` by its
spec, and `jail.env` can add keys but not remove them. So a variable of the launching shell (a
`CLAUDE_*` of a Claude Code that launched bh-02, say) sits in that process, out of a cell's
reach (in the jail, `ps` fails with a permission error; measured). bh-02's own token is never there: it goes
only to the Claude Code child.

One policy, two platforms; only the stack and the read model differ:

- darwin: brig's `scratch_darwin()` (seatbelt). Reads by denylist, which is `spec_for` as it is:
  everything but the secrets.
- Linux: brig's `strict_linux()` (bubblewrap). Reads by allowlist, so `allowlisted` turns the
  policy into one: what is readable is the system tree (`/usr`, `/etc`, ...), the interpreter
  (`sys.base_prefix`, `sys.prefix`), the directories the command names, and what the policy
  lets a cell write. Everything else does not exist in the jail, the home directory included.
  The secrets stay `read_denies`, now brig's carve-outs: one inside that tree (a `local.env` at
  the project root) is masked if it exists, and one that does not exist yet is not, which
  brig's `fs_read` grade says (`best_effort`, naming it); an absent one where bh-02 looks for
  its credential (`layers.credentials`) keeps its write deny, so a cell can't plant one there.
  bubblewrap makes each absent write-denied path (`.envrc`, `.vscode`, such a `local.env`, ...)
  an empty directory on the host for the jail to mount over; the jail removes the ones it made
  once brig has verified the worker is gone, never before (a mount point removed while the
  jail lives is detached inside it). A mount can be undone from the host (a file renamed over
  a masked one, a placeholder removed), so while the jail holds a secret under a writable root
  `fs_read` is best-effort (`graded`) and `notice()` says which paths (`held`, `notice_for`).

Anywhere else `start` refuses and names `kernel:unjailed`.
"""

import asyncio
import contextlib
import fcntl
import json
import os
import shutil
import stat
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

__all__ = [
    "SYSTEM_READABLE",
    "BrigConfig",
    "BrigJail",
    "Layers",
    "allowlisted",
    "graded",
    "held",
    "identity",
    "made_by_the_jail",
    "mountable",
    "notice_for",
    "readable_roots",
    "record_text",
    "recorded",
    "records_dir",
    "remove_placeholders",
    "self_modify_denied",
    "spec_for",
    "stack_for",
    "uncovered",
]

_READY_TIMEOUT_S = 10.0

#: The system tree a Linux jail may read: what the interpreter links against and reads at
#: start (`/lib`, `/usr/lib`, `/etc/ld.so.cache`, locale data) and what a cell runs (`/bin/sh`,
#: `git`, ...). Entries that do not exist on a host (`/lib64` on arm64) are dropped at start.
SYSTEM_READABLE: tuple[str, ...] = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc")

_STACKS: Mapping[str, Callable[[], Stack]] = {"darwin": scratch_darwin, "linux": strict_linux}


@runtime_checkable
class Layers(Protocol):
    """What the jail needs of the `layers` value (CONTRACTS.md: layers): the composition's files,
    which a cell may not write; where bh-02 looks for its credential, where a cell may create
    nothing; and the secrets, which it may not read."""

    @property
    def paths(self) -> tuple[str, ...]: ...
    @property
    def credentials(self) -> tuple[str, ...]: ...
    @property
    def secrets(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class BrigConfig:
    """`write`: where a cell may write besides its scratch dir (relative to the kernel's root).
    `deny`: more paths it may not write. `allow`: names from brig's self-modification list
    (`SELF_MODIFY_WORKSPACE_RELATIVE`: `.git/hooks`, `CLAUDE.md`, ...) a cell may write after all;
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
) -> Spec:
    """The jail's Spec. `host` is every path the host process loads code from; any under a
    writable root is denied, as are the layer files and brig's self-modification list.
    `secrets` (absolute) may not be read, wherever they are."""
    roots = [str(Path(root, w).resolve()) for w in config.write]
    writable = [*roots, scratch]
    # A host import path *inside* a writable root is denied. One that *is* a root (the project
    # itself on sys.path, as under `python -m bh_02`) is not: denying it would make the project
    # read-only. What that leaves: a module a cell writes at the project root could shadow one
    # the host has not imported yet. The `bh-02` console script never puts the root on sys.path.
    under = [p for p in host if p not in writable and any(p.startswith(r + "/") for r in writable)]
    selfmod = [str(Path(r, name)) for r in roots for name in self_modify_denied(config.allow)]
    hidden = [*(str(Path(root, name).resolve()) for name in config.hide), *secrets]
    # A secret a cell may not read, it may not overwrite or remove either: one under a writable
    # root (the project's `local.env`) is denied writing too, or a cell could replace the
    # credential it can't see.
    kept = [s for s in hidden if any(s == r or s.startswith(r + "/") for r in writable)]
    denies = [*layers, *under, *selfmod, *(str(Path(root, d).resolve()) for d in config.deny), *kept]
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
    """`spec`, reading by allowlist: `readable` is the tree a cell may read, and the policy's
    read denies become the carve-outs inside it. The environment and the channel are the
    policy's, unchanged, and so are the writes but one kind: a path denied both reading and
    writing (a secret under the project) keeps only its read deny. bwrap masks an existing one
    with a read-only `/dev/null`, which refuses writes and removal too (a write deny as well
    would be a bind of the real file, under the mask). An absent one has nothing to mask, so a
    cell could create it: those in `hold` (absent places bh-02 looks for its credential, where a
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


def held(spec: Spec) -> tuple[str, ...]:
    """The read denies a Linux jail holds with a mount on the path itself: those at or under a
    root a cell may write (a masked `local.env`, or the empty directory an absent one is held
    by). A mount is on the host's directory entry, so replacing that entry on the host (an
    editor saves by renaming a new file over it) or removing it detaches the mount inside the
    jail, and a cell can then read and rewrite what is there (measured). The rest are outside
    every writable root, where the allowlist alone keeps them out of the jail."""
    roots = spec.fs.write_allows
    return tuple(d for d in spec.fs.read_denies if any(d == r or d.startswith(r + "/") for r in roots))


def notice_for(platform: str, holds: Sequence[str]) -> str:
    """What the person should know at the start of a session about the secrets under a root a
    cell may write (`held`), or nothing: on darwin seatbelt matches paths, so nothing the host
    does to them lets a cell in."""
    if platform != "linux" or not holds:
        return ""
    return (
        f"The jail keeps cells from reading {', '.join(holds)}. On Linux it does that with a mount "
        "on each path that is there (and, where bh-02 looks for its credential, an empty directory "
        "where there is none, so nothing can be created there until bh-02 stops), and the host "
        "can undo a mount: a file created at one of these paths after the kernel started, or "
        "replaced (an editor saves local.env by renaming a new file over it) or removed while it "
        "runs, can be read and rewritten by a cell. Edit them with bh-02 stopped, or "
        "`/restart kernel` after, which puts a new jail over them."
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
    """The directories bubblewrap creates on the host for absent write-denied paths (each path
    and each missing parent; `absent` lists them all), deepest first: the order they can be
    removed in once the jail is gone."""
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
    """brig's self-modification list without the names `allow` lets a cell write. A name that
    is not on the list is a mistake in the row's config, never silently ignored."""
    unknown = [name for name in allow if name not in SELF_MODIFY_WORKSPACE_RELATIVE]
    if unknown:
        raise ValueError(
            f"the jail row's `allow` names {', '.join(map(repr, unknown))}, which brig does not deny "
            f"in the first place; `allow` takes only names from its self-modification list: "
            f"{', '.join(SELF_MODIFY_WORKSPACE_RELATIVE)}. To let a cell write another path, "
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
    """Which directory a placeholder is: its inode and when it changed. The inode alone is not
    enough: a directory removed and made again at the same path can get the same one back
    (measured, on overlayfs). The change time is as fine as the kernel's clock tick, so one
    made again within the same few milliseconds would pass for the jail's; and a placeholder
    something was added to and removed from since reads as changed, and is kept."""
    return f"{found.st_ino}:{found.st_ctime_ns}"


def record_text(made: Sequence[tuple[str, str | None]]) -> str:
    """A jail's record of its placeholders: each path, deepest first, with its `identity` once
    the jail was up (None before), so a later sweep removes only the directory it made."""
    return json.dumps({"made": [[path, found] for path, found in made]}) + "\n"


def recorded(text: str) -> list[tuple[str, str | None]]:
    """The placeholders a record names (`record_text`); nothing for a record that can't be read
    as one, which is then only removed."""
    try:
        made = json.loads(text)["made"]
        return [(str(path), found if isinstance(found, str) else None) for path, found in made]
    except ValueError, KeyError, TypeError:
        return []


def remove_placeholders(made: Sequence[tuple[str, str | None]]) -> None:
    """Remove each placeholder a jail made (deepest first) that is still what it made: an empty
    directory, the same one (`identity`) when that was recorded. One the person has put something in, or
    replaced with one of their own, stays. Only once no jail can have mounted over it: removed
    while a jail lives, it stops being a mount point inside it, and the path it denies is
    writable there."""
    for path, was in made:
        with contextlib.suppress(OSError):
            found = os.lstat(path)
            if stat.S_ISDIR(found.st_mode) and was in (None, identity(found)):
                os.rmdir(path)


class _Jailed:
    """A program brig started: interrupt is SIGINT to its group, stop is brig's teardown, then
    the directories the jail made on the host (`made`, deepest first) once it is gone.

    `lock` (Linux) is this jail's shared hold on the user's bh-02 jail lock, taken before the
    jail looked at the filesystem and held while it runs. A placeholder is removed only by a
    jail that can then take the lock exclusively: no other bh-02 jail is running, so none has
    mounted over one (a second session in the same project binds the first one's `.claude/`
    read-only, and removing it on the host detaches that bind; measured). `record` is the file
    that names them meanwhile (`records_dir`): if this jail can't remove them (another runs) or
    never stops (bh-02 crashed), the next jail to start with none running does."""

    def __init__(
        self, handle: Handle, jail_dir: str, made: Sequence[str], lock: int | None, record: str | None
    ) -> None:
        self._handle = handle
        self._jail_dir = jail_dir
        self._made: list[tuple[str, str | None]] = [(path, None) for path in made]
        self._lock = lock
        self._record = record

    def interrupt(self) -> bool:
        return self._handle.interrupt()

    def placed(self) -> None:
        """Note which directory each placeholder is now the jail is up (`identity`), in the record
        too, so it is removed later only while it is still the directory the jail made."""
        self._made = [(path, _identity(path)) for path, _ in self._made]
        if self._record is not None:
            with contextlib.suppress(OSError):
                Path(self._record).write_text(record_text(self._made))

    async def stop(self) -> None:
        report = await asyncio.to_thread(self._handle.kill)
        gone = all(item.outcome in (KillOutcome.ENDED, KillOutcome.ALREADY_GONE) for item in report.items)
        if gone and self._lock is not None:
            try:
                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass  # another jail runs: what it may have mounted over stays, and the record
            else:
                remove_placeholders(self._made)
                if self._record is not None:
                    with contextlib.suppress(OSError):
                        os.unlink(self._record)
        if self._lock is not None:
            os.close(self._lock)
            self._lock = None
        shutil.rmtree(self._jail_dir, ignore_errors=True)


def _identity(path: str) -> str | None:
    try:
        return identity(os.lstat(path))
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
        self._report: Mapping[str, str] = {}
        self._notice = ""
        if platform in _STACKS:
            with tempfile.TemporaryDirectory(prefix="bh-j-", dir="/tmp") as probe:
                self._report = self.compile(probe, str(Path(probe, "k.sock")), ".", ())[1]

    def report(self) -> Mapping[str, str]:
        return self._report

    def notice(self) -> str:
        """What the person should know about the jail the kernel runs in (`notice_for`): the
        paths a Linux jail holds with a mount, which the host can undo. Empty on darwin."""
        return self._notice

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> _Jailed:
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
        try:
            jail, self._report = self.compile(jail_dir, endpoint, cwd, argv)
            self._notice = notice_for(self._platform, held(jail.spec) if self._platform == "linux" else ())
            made = made_by_the_jail(self._absent_denies(jail.spec)) if self._platform == "linux" else ()
            if made:  # named before bubblewrap makes them, so a crash from here on leaves a record
                record = self._recorded(records, Path(jail_dir).name, made)
            handle = await asyncio.to_thread(
                SubprocessLauncher().launch,
                jail,
                argv=list(argv),
                cwd=cwd,
                io=IoPolicy(),
                jail_id=Path(jail_dir).name,
                jail_dir=jail_dir,
            )
        except BaseException:
            if lock is not None:
                os.close(lock)
            shutil.rmtree(jail_dir, ignore_errors=True)
            raise
        started = _Jailed(handle, jail_dir, made, lock, record)
        try:
            await asyncio.to_thread(handle.wait_ready, "kernel", _READY_TIMEOUT_S)
            started.placed()
        except BaseException as error:
            log = Path(jail_dir, "stderr.log")
            detail = log.read_text(errors="replace")[-2000:] if log.is_file() else ""
            await started.stop()
            raise RuntimeError(f"the jailed kernel never listened: {error}\n{detail}") from error
        return started

    def compile(
        self, jail_dir: str, endpoint: str, cwd: str, argv: Sequence[str]
    ) -> tuple[CompiledJail, Mapping[str, str]]:
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
        )
        if self._platform == "linux":
            readable = readable_roots(argv=argv, interpreter=(base_prefix, prefix), system=SYSTEM_READABLE)
            links = [link for arg in argv if arg.startswith("/") for link in self._linked_dirs(arg)]
            hold = [c for c in self._layers.credentials if not Path(c).exists()]
            spec = allowlisted(spec, [p for p in (*readable, *links) if Path(p).exists()], hold)
            denies = uncovered(mountable(spec.fs.write_denies, self._instead(spec)))
            spec = replace(spec, fs=replace(spec.fs, write_denies=denies))
        ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=self._platform)
        jail = stack_for(self._platform).compile(spec, ctx=ctx)
        report = {axis.value: grade.grade.value for axis, grade in jail.report.axes.items()}
        return jail, graded(report, held(spec) if self._platform == "linux" else ())

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

    def _hold(self, records: str) -> int:
        """A shared hold on this user's bh-02 jail lock (see `_Jailed`), waiting while a jail
        that is removing its placeholders holds it exclusively. Taken exclusively first when it
        can be: then no bh-02 jail of this user runs, and every record left (a crashed session's,
        or one that stopped while another ran) names placeholders nothing has mounted over, which
        are removed with it. The hold is then made shared (not atomically: in between another
        jail may take it exclusively, which only removes its own)."""
        lock = os.open(f"/tmp/bh-02-jails-{os.getuid()}.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            for left in sorted(Path(records).glob("*.json")) if Path(records).is_dir() else ():
                with contextlib.suppress(OSError):
                    remove_placeholders(recorded(left.read_text()))
                    left.unlink()
        fcntl.flock(lock, fcntl.LOCK_SH)
        return lock

    def _recorded(self, records: str, jail_id: str, made: Sequence[str]) -> str | None:
        """Write this jail's record of `made` (`record_text`) and return its path; None when the
        state directory can't be written (then only this jail's own `stop` removes them)."""
        record = Path(records, f"{jail_id}.json")
        try:
            record.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            record.write_text(record_text([(path, None) for path in made]))
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
