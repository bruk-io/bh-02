"""The confined runner's shell over brig (`runner:confined`): the policy (`policy.spec_for`, a
`Policy` of bh-02's own) gathered from the host, shaped for the platform, turned into brig's Spec
(`brig_spec.to_brig_spec`, the one converter), compiled, launched and graded. This module and that
one are the only ones that import brig.

One policy, two platforms; only the stack and the read model differ:

- darwin: brig's `scratch_darwin()` (seatbelt). Reads by denylist, which is `spec_for` as it is:
  everything but the secrets.
- Linux: brig's `strict_linux()` (bubblewrap). Reads by allowlist, so `allowlisted` turns the
  policy into one: what is readable is the system tree (`/usr`, `/etc`, ...), the interpreter
  (`sys.base_prefix`, `sys.prefix`), the directories the command names, bh-02's own code
  (`code`, read-only: the extensions process imports cordis, with an editable install from the
  workspace), and what the policy lets an input write. Everything else does not exist in the
  jail, the home directory included. brig's supervisor, the jail's PID 1, runs under a Python
  the jail holds, chosen at each compile (`supervisor_interpreter`): the system's
  `/usr/bin/python3` where there is one, else the one bh-02 runs on.
  The secrets stay masks, now brig's carve-outs: one inside that tree (a `hide`n file
  at the project root, a state directory under it) is masked if it exists, and one that does not
  exist yet is not, which brig's `fs_read` grade says (`best_effort`, naming it).
  bubblewrap holds each absent write-denied path by mounting over a placeholder
  (`placeholders`), and a mount can be undone from the host (a file renamed over a denied or
  masked one, as a host `git config` does to `.git/config`; a placeholder removed), and from then
  on an input could write or read that path. So the jail watches every path it holds
  (`mounts.tripwired`, `tripwire.Tripwire`; never one an input may create) and ends itself at
  the first such change: the next input's jail holds the path again, and the input says why
  (`ended`). Until it has ended (a few milliseconds; measured in the README) a program already
  running in it can get one write or read in, so while the jail holds a secret under a writable
  root `fs_read` stays best-effort (`mounts.graded`) and `notice()` says which paths
  (`mounts.held`, `mounts.notice_for`).

On both, the jail is launched tethered to bh-02 (`_Jailed`): when bh-02 ends, however it ends,
brig kills the jail's process group, so a program an input left running doesn't outlive it (on
Linux, bubblewrap's whole namespace; on darwin, what stayed in the group).

Anywhere else `start` refuses and names `runner:unconfined`.
"""

import asyncio
import contextlib
import fcntl
import os
import shutil
import signal
import tempfile
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from sys import base_prefix, prefix
from sys import executable as host_executable
from sys import path as import_path
from sys import platform as host_platform
from typing import Protocol, runtime_checkable

from brig.mech.bwrap import DEFAULT_BWRAP_PATH, DEFAULT_INTERPRETER, InterpreterNotMounted
from brig.run import (
    HostRuntime,
    IoPolicy,
    Jail,
    KillItem,
    KillOutcome,
    KillReport,
    Process,
    build_compile_ctx,
    group_alive,
)
from brig.stack import CompiledJail, Stack, scratch_darwin, strict_linux
from runner_cordis_plugin.brig_spec import to_brig_spec
from runner_cordis_plugin.facts import (
    absent_denies,
    absent_secrets,
    git_identity,
    instead,
    interpreter_files,
    links_on_the_way,
    present,
)
from runner_cordis_plugin.mounts import (
    graded,
    held,
    mountable,
    notice_for,
    released_for,
    tripwired,
    uncovered,
)
from runner_cordis_plugin.placeholders import (
    clear_up,
    lock_path,
    made_by_the_jail,
    open_lock,
    place,
    record_text,
    recorded,
    recorded_group,
    records_dir,
    remove_placeholders,
)
from runner_cordis_plugin.policy import (
    BrigConfig,
    Policy,
    allowlisted,
    git_author,
    readable_roots,
    spec_for,
    told_reads,
)
from runner_cordis_plugin.runner import ArgvFor, reserved_endpoint, unreserve_endpoint
from runner_cordis_plugin.tripwire import Tripwire

__all__ = [
    "SYSTEM_READABLE",
    "BrigJail",
    "Host",
    "group_alive",
    "host_interpreters",
    "stack_for",
    "still_running",
    "supervisor_interpreter",
]

_READY_TIMEOUT_S = 10.0


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


def still_running(report: KillReport) -> str:
    """What a teardown could not end, for the person: each item that failed, named, with what
    it said; "" when everything ended or was already gone."""
    return "; ".join(
        f"{item.kind} {item.identity}: {item.detail}"
        for item in report.items
        if item.outcome not in (KillOutcome.ENDED, KillOutcome.ALREADY_GONE)
    )


@dataclass(frozen=True, slots=True)
class _Facts:
    """What one start of the jail is, kept with that start for whoever started it (CONTRACTS.md:
    runner): its grades (`graded`), what the person should know about it (`notice_for`), the trees
    its program reads when that is all it reads (`told_reads`: a Linux jail's; empty on darwin)
    and the roots it may write but its scratch. A jail starts more than one program (the
    Python process, the extensions process), each from its own command: what one start is never
    replaces what another is."""

    report: Mapping[str, str]
    notice: str = ""
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()


class _Jailed:
    """A program brig started (`process`, the one process of its own `jail`): interrupt is
    SIGINT to its group, stop is brig's teardown of the jail (`Jail.destroy`), then the
    directories the jail made on the host (`made`, deepest first) once it is gone. `facts` is
    what this start is (`report`, `notice`, `reads`, `writes`), read whether or not it still
    runs.

    `tether` is the write end of the jail's tether (brig SPEC.md section 8): held by this
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
        jail: Jail,
        process: Process,
        facts: _Facts,
        jail_dir: str,
        endpoint: str,
        made: Sequence[tuple[str, str]],
        lock: int | None,
        record: str | None,
        tether: int | None = None,
        wire: Tripwire | None = None,
    ) -> None:
        self.endpoint = endpoint
        self._jail = jail
        self._process = process
        self._facts = facts
        self._wire = wire
        self._tether = tether
        self._jail_dir = jail_dir
        self._made: list[tuple[str, str]] = list(made)
        self._lock = lock
        self._record = record
        self._stopping: asyncio.Future[None] | None = None
        self._write()

    def interrupt(self) -> bool:
        return self._process.interrupt()

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
        a Linux jail's allowlist (the system, the interpreter, the program's own directory,
        bh-02's own code) and the roots it may write. Empty on darwin, whose jail reads
        everything but the secrets."""
        return self._facts.reads

    def writes(self) -> tuple[str, ...]:
        """The directories this start's program may write, but the jail's own scratch: the
        project and what `write` adds."""
        return self._facts.writes

    def _write(self) -> None:
        """The record as it stands: the placeholders, and which process group holds the jail they
        are mounted in: a Linux jail's instance (`Jail.instance_group`: PID 1 of its namespaces,
        which lives as long as they do, though the program ends first and a `setsid()` child of
        it runs on), else the program's own, which leads its group. A sweep that read the
        program's group would call a jail dead that a background server still holds."""
        if self._record is not None:
            group = self._jail.instance_group
            with contextlib.suppress(OSError):
                Path(self._record).write_text(
                    record_text(self._made, self._process.pid if group is None else group)
                )

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
        report = await asyncio.to_thread(self._jail.destroy)
        gone = all(item.outcome in (KillOutcome.ENDED, KillOutcome.ALREADY_GONE) for item in report.items)
        if gone and self._lock is not None:
            clear_up(self._lock, self._made, self._record)
        if self._lock is not None:
            os.close(self._lock)
            self._lock = None
        if self._tether is not None:
            os.close(self._tether)
            self._tether = None
        shutil.rmtree(self._jail_dir, ignore_errors=True)
        unreserve_endpoint(self.endpoint)


async def _until_listening(endpoint: str, timeout: float) -> None:
    """Wait until something accepts on `endpoint` (connect, then leave without a word), as
    brig's `Jail.wait_ready` did until its decision-186 took it away with the path a channel
    named. The owner dials the same path as found; TASK-0079.31 moves both to brig's verified
    dial (`Process.connect`).

    Raises:
        TimeoutError: nothing accepted within `timeout` seconds.
    """
    async with asyncio.timeout(timeout):
        while True:
            with contextlib.suppress(OSError):
                _, writer = await asyncio.open_unix_connection(endpoint)
                writer.close()
                return
            await asyncio.sleep(0.02)


def _launch(
    compiled: CompiledJail, *, argv: Sequence[str], cwd: str, jail_id: str, jail_dir: str, tether: int
) -> tuple[Jail, Process]:
    """A jail of its own for `argv`: brig's `Jail.create` through the host runtime, tethered
    to `tether` (the read end; the jail holds a duplicate), then its first and only `start`.
    A refused start changes nothing in brig (the jail is its creator's), so this ends the jail
    itself before saying why: what `create` started (a `JAIL_LIFETIME` helper) never outlives a
    start nobody was handed. The start's error is the one that crosses, whatever the ending
    found: each item it could not end, or its own failure, is a note on it (`_unended`).

    Raises:
        LaunchRefused: the jail needs a capability the host runtime lacks.
        JailDirInUse: `jail_dir` holds an earlier jail's records that still run.
        HelperFailed: a helper the jail starts at its creation failed.
        ExecWrapNotAPrefix: the compiled wrap is not a pure argv prefix (the jail is destroyed).
        TetherClosed: `tether` has already ended (the jail is destroyed).
        WorkloadSpawnFailed: `argv` could not be spawned in the jail (the jail is destroyed).
        OSError: the jail directory or a record could not be written.
    """
    jail = Jail.create(
        compiled, runtime=HostRuntime(), cwd=cwd, jail_id=jail_id, jail_dir=jail_dir, tether=tether
    )
    try:
        return jail, jail.start(argv, cwd=cwd, io=IoPolicy())
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
    (`jails.lock` in bh-02's state directory, `placeholders.lock_path`), which every bh-02 session
    of the user shares, so a jail sweeps what another session's jails left and none removes a
    placeholder while another runs. Only tests
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
        self._lock = lock if lock is not None else lock_path(os.environ, str(Path.home()))
        self._interpreters = host_interpreters() if interpreters is None else tuple(interpreters)
        # The grades are known before anything starts: compile once against a throwaway directory.
        # A platform brig has no preset for grades nothing; `start` says what to use instead.
        # The probe's endpoint is in a subdirectory: bwrap refuses one directly in the jail directory.
        # What each start is (its own grades among it) is kept with that start (`_Facts`).
        self._report: Mapping[str, str] = {}
        # every program this jail started that may still run, and the starts under way: what
        # `release` waits for (a start under way) and says still runs (an owner that kept its own)
        self._live: list[_Jailed] = []
        self._starting: set[asyncio.Future[None]] = set()
        if platform in _STACKS:
            with tempfile.TemporaryDirectory(prefix="bh-j-", dir="/tmp") as probe:
                self._report = self.compile(probe, str(Path(probe, "chan", "k.sock")), ".", ())[1]

    def report(self) -> Mapping[str, str]:
        """The grades, known before anything starts (what `approval` reads); no start changes
        them. A started program's own are its `report()`."""
        return self._report

    async def release(self) -> str:
        """For `/release`, once each owner has stopped its own program (`runner.Runner`). On
        Linux: wait for a start under way, sweep what jails that are gone left (each stop already
        removed what its jail made once no jail runs), and say whether a program of this jail's
        still runs (`released_for`). Empty when there is nothing to say, and on
        darwin, where seatbelt holds a path without anything on the host."""
        if self._platform != "linux":
            return ""
        await asyncio.gather(*self._starting)  # a start under way: its placeholders made first
        self._live = [started for started in self._live if not started.stopped]
        await asyncio.to_thread(self._swept, records_dir(os.environ, str(Path.home())))
        return released_for(running=bool(self._live))

    async def start(self, argv_for: ArgvFor, *, cwd: str) -> _Jailed:
        """Start the program `argv_for(endpoint)` in `cwd`, in a jail of its own compiled from the
        policy, listening on the endpoint this start reserved (`started.endpoint`)."""
        starting: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._starting.add(starting)
        try:
            started = await self._launched(argv_for, cwd=cwd)
            self._live = [*(each for each in self._live if not each.stopped), started]
            return started
        finally:
            self._starting.discard(starting)
            if not starting.done():  # a `release` cancelled as it waited cancels it
                starting.set_result(None)

    async def _launched(self, argv_for: ArgvFor, *, cwd: str) -> _Jailed:
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
        lock = await asyncio.to_thread(self._hold, records) if self._platform == "linux" else None
        jail_dir = tempfile.mkdtemp(prefix="bh-j-", dir="/tmp")
        endpoint = reserved_endpoint()
        record: str | None = None
        placed: list[tuple[str, str]] = []
        wire: Tripwire | None = None
        # The jail ends with this process, however it ends (`_Jailed`). os.pipe's ends are not
        # inherited, so no other child of bh-02 (the Claude Code CLI) holds the write end.
        watched, tether = os.pipe()
        try:
            argv = argv_for(endpoint)
            author = git_author(*git_identity(cwd)) if self._platform == "linux" else ()
            policy, python = self._planned(jail_dir, endpoint, cwd, argv, author)
            jail, report = self._compiled(policy, python, jail_dir)
            absent = absent_secrets(policy.masks)
            facts = self._facts(policy, report, absent, jail_dir, endpoint)
            made = (
                made_by_the_jail(absent_denies(policy.writable, policy.write_denies))
                if self._platform == "linux"
                else ()
            )
            if made:
                # Recorded before anything is made, each by the mark it will carry, then made and
                # marked one by one, parents first, and recorded as made: a crash at any point
                # leaves a record whose every directory is either provably the jail's or kept.
                jail_id = Path(jail_dir).name
                record = self._recorded(records, jail_id, [(path, f"mark:{jail_id}") for path in made])
                for path in reversed(made):
                    known = place(path, jail_id)
                    if known is not None:
                        placed.insert(0, (path, known))
                if record is not None:
                    self._recorded(records, jail_id, placed)
            if self._platform == "linux":
                # After the placeholders are made, before bubblewrap mounts over them: from here
                # on, the host undoing a mount is seen.
                wire = Tripwire(tripwired(policy, absent))
            launching = asyncio.ensure_future(
                asyncio.to_thread(
                    _launch,
                    jail,
                    argv=argv,
                    cwd=cwd,
                    jail_id=Path(jail_dir).name,
                    jail_dir=jail_dir,
                    tether=watched,
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
                clear_up(lock, placed, record)  # bubblewrap never ran: nothing is mounted on them
                os.close(lock)
            os.close(tether)
            shutil.rmtree(jail_dir, ignore_errors=True)
            unreserve_endpoint(endpoint)
            raise
        finally:
            os.close(watched)
        if wire is not None:
            wire.arm(
                lambda: still_running(running.destroy(grace=0.0)),
                fallback=lambda: os.killpg(running.instance_group or process.pid, signal.SIGKILL),
            )
        started = _Jailed(running, process, facts, jail_dir, endpoint, placed, lock, record, tether, wire)
        try:
            await _until_listening(endpoint, _READY_TIMEOUT_S)
        except BaseException as error:
            log = Path(process.stderr_path)
            detail = log.read_text(errors="replace")[-2000:] if log.is_file() else ""
            await started.stop()
            raise RuntimeError(f"the jailed program never listened: {error}\n{detail}") from error
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
        is set in the worker's environment besides the policy's own.

        Raises:
            RuntimeError: on Linux, no Python the jail mounts is among the interpreters
                (`_no_python_message`); brig's `InterpreterNotMounted` is its cause.
        """
        policy, python = self._planned(jail_dir, endpoint, cwd, argv, author)
        return self._compiled(policy, python, jail_dir)

    def _planned(
        self, jail_dir: str, endpoint: str, cwd: str, argv: Sequence[str], author: Sequence[tuple[str, str]]
    ) -> tuple[Policy, str]:
        """The policy for `argv` in `cwd` as this platform's jail takes it, and the interpreter
        brig's supervisor runs under (`DEFAULT_INTERPRETER` where there is none to choose)."""
        scratch = str(Path(jail_dir, "tmp"))
        Path(scratch).mkdir(parents=True, exist_ok=True)
        host = [str(Path(p).resolve()) for p in (*import_path, prefix) if p]
        names = (host_executable, str(Path(base_prefix, "bin", "python3")))  # how the host reaches its Python
        policy = spec_for(
            root=cwd,
            endpoint=endpoint,
            scratch=scratch,
            home=str(Path.home()),
            config=self._config,
            layers=self._host.paths,
            host=host,
            secrets=self._host.secrets,
            trusted=self._host.trusted,
            code=self._host.code,
            interpreters=interpreter_files(names),
            links=[link.entry for link in links_on_the_way(names)],
            memory=self._host.auto_memory,
        )
        python = DEFAULT_INTERPRETER
        if self._platform == "linux":
            readable = readable_roots(
                argv=argv, interpreter=(base_prefix, prefix), system=SYSTEM_READABLE, code=self._host.code
            )
            # a tree reached through a link must be named as the link too: bubblewrap mounts a tree
            # at the path the policy spells (a uv venv's `python` points into `cpython-3.15-...`, a
            # link to the `cpython-3.15.0rc2-...` that `sys.base_prefix` names; measured: without it
            # the worker's exec fails with "No such file or directory")
            links = [
                link.entry
                for arg in argv
                if arg.startswith("/")
                for link in links_on_the_way([os.path.abspath(arg)])
                if link.through
            ]
            policy = allowlisted(policy, [p for p in (*readable, *links) if Path(p).exists()])
            denies = uncovered(mountable(policy.write_denies, instead(policy.write_denies, policy.writable)))
            policy = replace(policy, write_denies=denies, env_set=(*policy.env_set, *author))
            python = supervisor_interpreter(
                present(self._interpreters),
                policy.readable,
                writable=policy.writable,
                denied=policy.write_denies,
            )
        return policy, python

    def _compiled(self, policy: Policy, python: str, jail_dir: str) -> tuple[CompiledJail, Mapping[str, str]]:
        """`policy` compiled for this platform's jail (`to_brig_spec`), and its grades."""
        spec = to_brig_spec(policy)
        ctx = build_compile_ctx(spec, jail_dir=jail_dir, platform=self._platform)
        try:
            jail = stack_for(self._platform, python).compile(spec, ctx=ctx)
        except InterpreterNotMounted as error:
            raise RuntimeError(_no_python_message(self._interpreters, python)) from error
        report = {axis.value: grade.grade.value for axis, grade in jail.report.axes.items()}
        holds = held(policy, absent_secrets(policy.masks)) if self._platform == "linux" else ()
        return jail, graded(report, holds)

    def _facts(
        self, policy: Policy, report: Mapping[str, str], absent: Collection[str], jail_dir: str, endpoint: str
    ) -> _Facts:
        """What a start of `policy` (in `jail_dir`, listening on `endpoint`; `absent`, the masks
        that are not there) is, for whoever started it: its grades, its notice, the trees it
        reads (Linux) and the roots it may write but its scratch."""
        socket_dir = str(Path(endpoint).parent)
        writes = tuple(w for w in policy.writable if not Path(w).is_relative_to(jail_dir) and w != socket_dir)
        if self._platform != "linux":
            return _Facts(report, self._note, writes=writes)
        trees = (*policy.readable, *policy.writable)
        return _Facts(
            report,
            "\n".join(filter(None, (self._note, notice_for(self._platform, held(policy, absent))))),
            told_reads(trees, (jail_dir, socket_dir)),
            writes,
        )

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
        lock = open_lock(self._lock)
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
        lock = open_lock(self._lock)
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
