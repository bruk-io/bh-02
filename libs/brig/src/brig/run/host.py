"""`HostRuntime`: brig's own runtime, the one every jail ran under before it had a name.

SPEC.md section 3 (decision-178, decision-0001 step 1). Its instance is host
process groups: `create` runs the compiled jail's argv under the exit wrapper,
detached in a new process group, tethered when asked; `destroy` is SPEC.md
section 9's verified ladder over the workload's group, every exec sibling and
every `JAIL_LIFETIME` helper (`brig/run/teardown.py`); `HostAgent` starts a
sibling under the same wrap (`EQUIVALENT_PROFILE`, or `PLAIN` for the empty
stack), signals a group after checking its leader's identity, waits through the
exit record or its own `Popen`, and stops one group with the same ladder.

Everything here is what `SubprocessLauncher.launch`, `Handle.interrupt`,
`Handle.wait` and `exec_in_jail` did before decision-178, moved rather than
changed. The launcher's own notes on that code follow, as they stood ("this
launcher" is now `create`; sensor stamping and `signatures` stayed in
`launcher.py`):

**`wrap_prefix` (task-046).** `handle.exec` (SPEC.md §9) needs to place a
sibling process inside the same confinement `jail.wrap` compiled for the
workload -- but `Handle` does not carry the `CompiledJail.wrap` callable
itself (only the already-wrapped `argv` it launched), and a callable is not
serializable across `to_dict`/`from_dict`'s process boundary anyway. So
this launcher DERIVES `wrap_prefix` once, here, at launch time
(`_derive_wrap_prefix`): the tuple of tokens `jail.wrap` prepended ahead of
`argv`, verified -- not assumed -- to be a pure prefix (the wrap's output
ends in exactly `argv`, unchanged). `exec_.exec_in_jail` then reproduces
`jail.wrap`'s effect on an arbitrary exec argv by literally prepending this
same prefix, and refuses exec outright when the verification found no pure
prefix (`wrap_prefix is None`) rather than spawn a weaker sibling.

**The exit wrapper (decision-156, 2026-09-08).** This launcher does not
spawn the compiled jail's argv directly any more. It spawns
`brig/run/_exit_status.py`'s wrapper program, which spawns that argv as its
own child, waits for it, and writes the status to `<jail_dir>/exit` -- so a
`Handle` rehydrated in a process that never parented the workload can still
read how it ended, which is the one capability decision-152 admitted it was
giving up. The wrapper prepends NOTHING to the jail's argv: `wrap_prefix` is
still derived against `jail.wrap`'s own output, `Handle.argv` still reports
the jail's compiled argv, and what runs inside the confinement is byte for
byte what ran before. What changes is that `Handle.pid` names the wrapper and
the jail's own process is its child in the same group -- teardown is
group-shaped at every rung, so nothing about kill depends on which of the two
the pid names. See that module for the `SIGKILL` case it cannot cover.

**Start-time stamps (decision-155, 2026-09-08).** The leader's pid and every
`JAIL_LIFETIME` helper's pid are recorded together with the moment that
process started (`brig/run/_identity.py`), because a pid alone is a slot
rather than an occupant: an OS that recycled the number between launch and
teardown would have `alive()` reporting a stranger as this jail and teardown
signalling one. The stamps ride on the `Handle`, so a rehydrated handle
compares them too.
"""

import math
import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from brig.core.runtime import Capability, RuntimeKind
from brig.mech import HelperLifetime
from brig.run import _execs, _exit_status, _identity, _waiters
from brig.run._spawn_pgid import spawn_pgid
from brig.run.exec_ import ExecWrapNotAPrefix
from brig.run.runtime import (
    Agent,
    ExitStatusUnobservable,
    IoPolicy,
    JailRecord,
    ProcessRecord,
)
from brig.run.teardown import KillReport, end_group, kill_named
from brig.stack import CompiledJail

#: How long a LAUNCH_SCOPED helper may take to finish. It is a preparation
#: step, not work: the ceiling exists to turn "declared with the wrong
#: lifetime" from a silent hang into a named failure, not to bound honest
#: slowness, so it is generous.
_LAUNCH_SCOPED_TIMEOUT_S: Final = 120.0


#: How often `HostAgent.wait` re-asks whether the first process is alive
#: while polling. The two cheap sources (this process's waiter record, the
#: exit file) are polled far more often; the liveness question exists only
#: to turn "still running" into "gone, and nothing recorded it", and paying a
#: `/bin/ps` fifty times a second to ask it sooner buys nothing.
_LIVENESS_POLL_S: Final = 0.25


class HelperFailed(RuntimeError):
    """A `LAUNCH_SCOPED` helper exited non-zero, so the workload was never
    started.

    Deliberately NOT `LaunchRefused`: that error means "this launcher lacks
    a capability this jail requires", carries `missing`, and is answered by
    choosing another launcher. This one means the launcher was right and a
    preparation step failed -- answered by fixing the helper. Collapsing the
    two would make `missing` a lie on half the raises.
    """

    def __init__(self, helper_name: str, returncode: int, stderr: str) -> None:
        self.helper_name = helper_name
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"LAUNCH_SCOPED helper {helper_name!r} exited {returncode}; refusing to "
            f"start the workload behind a preparation step that failed: {stderr[:200]!r}"
        )


class LaunchRefused(ValueError):
    """A `CompiledJail`'s `requires` exceed this launcher's `capabilities`.

    SPEC.md §8: "Refusal names the missing feature." `missing` is the
    structured field a caller inspects instead of parsing `str(exc)`.
    """

    def __init__(self, missing: frozenset[Capability], launcher_name: str) -> None:
        self.missing = missing
        self.launcher_name = launcher_name
        super().__init__(str(self))

    def __str__(self) -> str:
        names = ", ".join(sorted(feature.value for feature in self.missing))
        return (
            f"launcher {self.launcher_name!r} cannot honor required "
            f"feature(s) not in its capabilities: {names}"
        )


def _derive_wrap_prefix(
    wrapped_argv: tuple[str, ...], argv: tuple[str, ...]
) -> tuple[str, ...] | None:
    """DERIVE and VERIFY -- never assume -- that `wrapped_argv` (the stack's
    compiled `wrap` applied to `argv`) is `argv` prefixed by a PURE argv
    prefix: `tuple(wrapped_argv[-len(argv):]) == argv` and
    `len(wrapped_argv) >= len(argv)`. Returns the prefix tuple where that
    holds, `None` where it does not -- `exec_.exec_in_jail` (SPEC.md §9)
    refuses exec on `None` rather than spawn a weaker sibling.

    The empty-`argv` case is special-cased deliberately: Python's
    `seq[-0:]` is `seq[0:]` (the WHOLE sequence), not the empty suffix,
    because `-0 == 0` -- using `wrapped_argv[-len(argv):]` unconditionally
    would silently treat every wrap as a match when `argv` is `()`, which
    is exactly the "assumed, not verified" failure this function exists to
    close.
    """
    n = len(argv)
    suffix = wrapped_argv[-n:] if n else ()
    if len(wrapped_argv) < n or suffix != argv:
        return None
    return wrapped_argv[: len(wrapped_argv) - n]


def _write_staged_files(jail_dir: str, jail: CompiledJail) -> None:
    for staged in jail.staged:
        path = os.path.join(jail_dir, staged.relpath)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as f:
            f.write(staged.content)
        os.chmod(path, staged.mode)


def _spawn(
    wrapped_argv: tuple[str, ...],
    *,
    cwd: str,
    env: Mapping[str, str],
    stdout_path: str,
    stderr_path: str,
    jail_dir: str,
    tether: int | None = None,
) -> subprocess.Popen[bytes]:
    """Spawn the jail's argv under the exit wrapper, detached, new group.

    `start_new_session=True` is what puts the group leader in its own
    process group and detaches it from the launching process's controlling
    terminal/session -- SPEC.md §8's "detached, new process group" for the
    `subprocess` launcher, in one keyword.

    The process this returns is `_exit_status.WRAPPER_SOURCE`, not the
    jail's argv: the wrapper spawns THAT as its own child, inheriting this
    cwd, env and stdio unchanged, and writes the status to
    `<jail_dir>/exit` when it ends (decision-156). The ready pipe is what
    keeps a workload that cannot be exec'd a LAUNCH failure rather than a
    handle for something already dead -- the wrapper writes one token
    through it the instant the spawn succeeds or fails, and closing it is
    the only other way this read can end.
    """
    read_fd, write_fd = os.pipe()
    try:
        with (
            open(stdout_path, "wb") as stdout_f,
            open(stderr_path, "wb") as stderr_f,
            open(os.devnull, "rb") as stdin_f,
        ):
            proc = subprocess.Popen(
                _exit_status.wrapper_argv(sys.executable, jail_dir, write_fd, wrapped_argv, tether),
                cwd=cwd,
                env=dict(env),
                stdin=stdin_f,
                stdout=stdout_f,
                stderr=stderr_f,
                start_new_session=True,
                pass_fds=(write_fd,) if tether is None else (write_fd, tether),
            )
        os.close(write_fd)
        write_fd = -1
        token = os.read(read_fd, 4096)
    finally:
        if write_fd != -1:
            os.close(write_fd)
        os.close(read_fd)

    if token.startswith(b"err:"):
        proc.wait()
        raise _exit_status.WorkloadSpawnFailed(
            f"the workload {wrapped_argv[0]!r} could not be spawned inside its jail: "
            + token[4:].decode(errors="replace")
        )
    if token != b"ok":
        proc.wait()
        raise _exit_status.WorkloadSpawnFailed(
            f"the exit wrapper for {wrapped_argv[0]!r} ended before it spawned the "
            f"workload (reported {token!r}); see {stderr_path}"
        )
    return proc


def _start_helpers(
    jail: CompiledJail, *, cwd: str, env: Mapping[str, str], jail_dir: str
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Start `Step.helpers`, returning the pids AND start-time stamps of the
    ones that persist (`_identity.start_stamp`, decision-155 -- a pid alone
    is a number a later teardown can find pointing at a stranger).

    `Helper` and `HelperLifetime` have been in the mechanism contract since
    M2 and nothing ever started one -- the declared-but-uncalled shape this
    repo's CLAUDE.md names as its recurring defect. M6's `connect_proxy` is
    the first mechanism that needs them, so they run now.

    Two lifetimes, and the difference is when this function returns:

    `LAUNCH_SCOPED` helpers run to COMPLETION here, before the workload is
    spawned -- "gone before the workload runs" (SPEC.md §6) is a guarantee
    the workload can rely on, not a hope, so this blocks on them. A non-zero
    exit is a launch failure: a helper that was supposed to prepare
    something and did not must not be followed by a workload assuming it
    did.

    `JAIL_LIFETIME` helpers are started detached, in their own process
    group, and their pids returned so the `Handle` can carry them. They are
    reaped by the same paths that reap the workload -- the exit waiter when
    it exits on its own, `kill_jail` when it is torn down -- rather than by
    a pipe-EOF scheme. Pid-watch is chosen over pipe-EOF (SPEC.md §6 allows
    either, "chosen once, documented") because this launcher already owns a
    per-jail waiter thread, and because a pid recorded on the Handle
    survives serialization: a rehydrated handle in another process can kill
    a helper it never started, which an inherited pipe fd could never give
    it.
    """
    persistent: list[int] = []
    stamps: list[str] = []
    for helper in jail.helpers:
        if helper.lifetime is HelperLifetime.LAUNCH_SCOPED:
            try:
                done = subprocess.run(
                    list(helper.argv),
                    cwd=cwd,
                    env=dict(env),
                    capture_output=True,
                    check=False,
                    timeout=_LAUNCH_SCOPED_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as expired:
                # Found by a mutation check that flipped `connect_proxy`'s
                # proxy from JAIL_LIFETIME to LAUNCH_SCOPED: the proxy runs
                # forever by design, so an unbounded `run` here wedged the
                # launcher with no output at all -- no error, no workload,
                # no diagnostic. The declaring mechanism is the bug in that
                # case, and this is what says so instead of hanging.
                stderr = expired.stderr or b""
                raise HelperFailed(
                    helper.name,
                    -1,
                    f"did not exit within {_LAUNCH_SCOPED_TIMEOUT_S}s. A LAUNCH_SCOPED "
                    "helper must run to completion before the workload; a process that "
                    "runs for the life of the jail must be declared JAIL_LIFETIME. "
                    + stderr.decode(errors="replace"),
                ) from expired
            if done.returncode != 0:
                raise HelperFailed(
                    helper.name, done.returncode, done.stderr.decode(errors="replace")
                )
            continue
        log_path = os.path.join(jail_dir, f"helper-{helper.name}.log")
        with open(log_path, "wb") as sink, open(os.devnull, "rb") as devnull:
            proc = subprocess.Popen(
                list(helper.argv),
                cwd=cwd,
                env=dict(env),
                stdin=devnull,
                stdout=sink,
                stderr=sink,
                start_new_session=True,
            )
        # Deliberately NOT held: unlike the workload, a helper's exit STATUS
        # is not a claim anyone makes, so letting `subprocess._cleanup` reap
        # it is harmless. What matters is that it can be KILLED, and a pid on
        # the Handle is what gives every teardown path -- including a
        # rehydrated one in another process -- the ability to do that.
        persistent.append(proc.pid)
        # Read while the helper is as young as it will ever be: the stamp
        # is what makes `helper_pids` an identity rather than a number a
        # later teardown might find pointing at a stranger (decision-155).
        stamps.append(_identity.start_stamp(proc.pid))
    return tuple(persistent), tuple(stamps)


def _refused(jail: CompiledJail, capabilities: frozenset[Capability]) -> frozenset[Capability]:
    """The capabilities `jail` requires that `capabilities` lacks."""
    return jail.requires - capabilities


@dataclass(frozen=True, slots=True)
class HostRuntime:
    """Host process groups as a jail's instance (decision-178).

    Holds no state: everything a later call needs is in the `JailRecord`
    `create` returns, so a record rehydrated in another process is
    controlled the same way. The one thing that does not cross processes is
    what `_waiters` and a `HostAgent` hold in memory (the exit observation,
    a sibling's `Popen`); the exit file and the registration directory under
    `jail_dir` are what stand in for them elsewhere."""

    kind: RuntimeKind = RuntimeKind.HOST
    capabilities: frozenset[Capability] = frozenset(
        {Capability.NEW_PROCESS_GROUP, Capability.DETACH}
    )

    def create(
        self,
        jail: CompiledJail,
        *,
        argv: Sequence[str],
        cwd: str,
        io: IoPolicy,
        jail_id: str,
        jail_dir: str,
        tether: int | None,
    ) -> JailRecord:
        """What `SubprocessLauncher.launch` did, in its order: create
        `jail_dir`, clear any exit record an earlier launch left in it
        (decision-162), write `jail.staged`, start `jail.helpers`, spawn
        `jail.wrap(argv)` under the exit wrapper, detached in a new process
        group with stdio per `io`, read its identity, and hand its reap to a
        waiter thread.

        `tether` (decision-167, SPEC.md section 8) is the read end of a pipe
        whose write end the caller keeps: once every write end is closed, the
        workload's process group is sent `SIGKILL`. `None`: the jail lives
        until it ends or is destroyed.

        Raises:
            LaunchRefused: `jail.requires` names a feature `capabilities`
                lacks.
            HelperFailed: a `LAUNCH_SCOPED` helper exited non-zero or did not
                finish.
            _exit_status.WorkloadSpawnFailed: the workload could not be
                spawned inside its jail.
        """
        missing = _refused(jail, self.capabilities)
        if missing:
            raise LaunchRefused(missing, "host")

        os.makedirs(jail_dir, exist_ok=True)
        # Before anything is staged or spawned: a status left in this
        # directory by an EARLIER launch would be returned by this launch's
        # own `Handle.wait` as if it were this workload's (decision-162).
        _exit_status.clear_exit_status(jail_dir)
        _write_staged_files(jail_dir, jail)

        argv_t = tuple(argv)
        wrapped_argv = tuple(jail.wrap(argv_t))
        # SPEC.md §9's exec fidelity depends on this: `exec_.exec_in_jail`
        # trusts `wrap_prefix` to reproduce the workload's own compiled
        # wrap for an arbitrary exec argv, so it must be DERIVED and
        # VERIFIED here, once, against the actual compiled wrap's output --
        # never assumed from the mechanism roster or the stack's shape.
        wrap_prefix = _derive_wrap_prefix(wrapped_argv, argv_t)

        # The workload's env is the launching process's own environment
        # (so `bash`/PATH-relative lookups work at all) overlaid with the
        # jail's compiled env (SPEC.md §7 Composition: mechanism env
        # merges, later-wins). M2 has zero mechanisms, so `jail.env` is
        # ordinarily empty and this is exactly os.environ; real scrubbing
        # is a mechanism's job and arrives with M3 (env axis grades
        # UNENFORCED here regardless of what this launcher passes through).
        full_env: dict[str, str] = {**os.environ, **jail.env}

        stdout_path = os.path.join(jail_dir, io.stdout_name)
        stderr_path = os.path.join(jail_dir, io.stderr_name)

        helper_pids, helper_stamps = _start_helpers(jail, cwd=cwd, env=full_env, jail_dir=jail_dir)

        proc = _spawn(
            wrapped_argv,
            cwd=cwd,
            env=full_env,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            jail_dir=jail_dir,
            tether=tether,
        )
        pid = proc.pid
        # decision-155: read the leader's start time now, while it is
        # certainly still the process this launch just created. Every
        # liveness and kill decision compares it against the pid's current
        # occupant, so a recycled pid reads as gone rather than as this
        # jail. `_identity.UNKNOWN` when the host can't read it (`/proc` or
        # `ps` unavailable or failing); teardown then signals nothing for
        # this record and reports it FAILED while its group runs
        # (decision-172).
        start_time = _identity.start_stamp(pid)
        # task-075: same darwin getpgid-zombie race as `exec_.py` -- a fast
        # workload command that exits before this read would crash
        # `launch()` after the spawn but before the SPAWN record and the
        # exit-waiter registration. See `brig/run/_spawn_pgid.py`.
        pgid = spawn_pgid(proc)

        # One thread owns this workload's reap, records its exit status, and
        # asks every sensor what it makes of that ending. Without it,
        # `subprocess._cleanup()` reaps the workload at the next Popen
        # anywhere in the process and the status is lost -- see
        # brig/run/_waiters.py for why holding the Popen instead is worse.
        _waiters.watch(proc, jail_id=jail_id, sensors=jail.sensors)

        return JailRecord(
            kind=self.kind,
            jail_id=jail_id,
            jail_dir=jail_dir,
            cwd=cwd,
            jail_env=frozendict(jail.env),
            wrap_prefix=wrap_prefix,
            first=ProcessRecord(
                pid=pid,
                pgid=pgid,
                start_time=start_time,
                argv=wrapped_argv,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            ),
            helper_pids=helper_pids,
            helper_stamps=helper_stamps,
        )

    def alive(self, jail: JailRecord) -> bool:
        """Whether the first process still runs, by identity: its pid and the
        start time recorded for it (decision-155). A recycled pid and a
        zombie read gone (decision-171); an unknown stamp degrades to the
        pid-only check. This answers for the leader only; `destroy` is what
        ends a group."""
        return _identity.identity_holds(jail.first.pid, jail.first.start_time)

    def destroy(self, jail: JailRecord) -> KillReport:
        """SPEC.md section 9's ladder over the first process's group, every
        exec sibling registered under `jail_dir`, then every `JAIL_LIFETIME`
        helper, each verified (`teardown.kill_named`). Total: raises nothing
        from an item."""
        return kill_named(
            pgid=jail.first.pgid,
            pid=jail.first.pid,
            start_time=jail.first.start_time,
            jail_dir=jail.jail_dir,
            helper_pids=jail.helper_pids,
            helper_stamps=jail.helper_stamps,
        )

    def agent(self, jail: JailRecord) -> Agent:
        """A fresh `HostAgent` bound to `jail`. Every host jail has one: a
        sibling is started from the record alone."""
        return HostAgent(jail)


class HostAgent:
    """Starts, signals, waits for and stops processes in one host jail.

    A class because it holds state its own methods change: the `Popen` of
    every sibling it started, so `wait` can collect its status, and which of
    them it has already deregistered. Whoever holds the agent holds those
    `Popen`s (an `ExecHandle` holds the agent that started it), so a sibling
    nobody waits for is dropped with its handle and reaped by `subprocess`,
    as before decision-178."""

    def __init__(self, jail: JailRecord) -> None:
        self._jail = jail
        self._spawned: dict[int, subprocess.Popen[bytes]] = {}
        self._deregistered: set[int] = set()

    def start(self, argv: Sequence[str], *, cwd: str, io: IoPolicy) -> ProcessRecord:
        """Run `argv` as a sibling under the jail's own wrap: `(*wrap_prefix,
        *argv)`, env `{**os.environ, **jail_env}`, stdio per `io` under
        `jail_dir`, stdin `/dev/null`, a new process group, registered under
        `jail_dir` before this returns so a teardown in any process finds it.

        Raises:
            ExecWrapNotAPrefix: the jail's wrap is not a pure argv prefix
                (`wrap_prefix is None`); raised before anything is opened or
                spawned, rather than start a sibling under a weaker
                confinement than the jail's first process.
        """
        argv_t = tuple(argv)
        wrap_prefix = self._jail.wrap_prefix
        if wrap_prefix is None:
            raise ExecWrapNotAPrefix(self._jail.first.argv, argv_t)

        spawned_argv = (*wrap_prefix, *argv_t)
        # The launcher's OWN env composition (`create`'s `full_env`),
        # evaluated fresh at exec time -- the sibling's starting environment is
        # the workload's declared overlay over this process's environment, in
        # both fidelity cases (decision-152; see `exec_.py`'s docstring).
        spawn_env: dict[str, str] = {**os.environ, **self._jail.jail_env}
        stdout_path = os.path.join(self._jail.jail_dir, io.stdout_name)
        stderr_path = os.path.join(self._jail.jail_dir, io.stderr_name)

        with (
            open(stdout_path, "wb") as stdout_f,
            open(stderr_path, "wb") as stderr_f,
            open(os.devnull, "rb") as stdin_f,
        ):
            proc = subprocess.Popen(
                spawned_argv,
                cwd=cwd,
                env=spawn_env,
                stdin=stdin_f,
                stdout=stdout_f,
                stderr=stderr_f,
                start_new_session=True,
            )

        pid = proc.pid
        # SPEC.md §9 / decision-042 (task-027): the registration carries the
        # sibling's pgid EXPLICITLY, read fresh via `os.getpgid` -- never
        # inferred from `pid`. `start_new_session=True` makes them equal
        # today, but an inferred identity would be a claim about a launcher
        # detail, not a recorded fact; `teardown.kill_jail` (task-027) reads
        # this field back from a REHYDRATED handle in a separate process, so
        # the fact has to be on disk, not reconstructed.
        # task-075: the read goes through `spawn_pgid`, because darwin's
        # `getpgid()` raises ESRCH for a sibling that has ALREADY EXITED (a
        # fast command like `/usr/bin/true` under any scheduling delay) -- a
        # bare call here crashed `exec_in_jail` after the spawn but before the
        # registration, leaving the sibling unregistered and its zombie to the
        # GC. The fallback records the same fact (setsid-before-exec makes the
        # group the pid from birth); see `brig/run/_spawn_pgid.py`.
        pgid = spawn_pgid(proc)
        # decision-155: the registration carries WHEN this sibling started as
        # well as its number, so a teardown running later -- possibly in another
        # process -- can tell it from whatever the OS handed that pid to next.
        # Read here, while the sibling is as young as it will ever be.
        start_time = _identity.start_stamp(pid)
        _execs.register(self._jail.jail_dir, pid, pgid, start_time)
        self._spawned[pid] = proc

        return ProcessRecord(
            pid=pid,
            pgid=pgid,
            start_time=start_time,
            argv=spawned_argv,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    def signal(self, process: ProcessRecord, sig: signal.Signals) -> bool:
        """Deliver `sig` to `process`'s **group** (`os.killpg`), never a
        single pid. `True` means the kernel accepted it for delivery, not
        that anything stopped. `False`: the leader's pid now names a
        different process (decision-155, nothing sent), or the group is gone
        (`ProcessLookupError`) or not this process's to signal
        (`PermissionError`)."""
        if _identity.recycled(process.pid, process.start_time):
            return False
        try:
            os.killpg(process.pgid, sig)
        except ProcessLookupError, PermissionError:
            return False
        return True

    def wait(self, process: ProcessRecord, timeout: float | None) -> int | None:
        """The exit status of `process`, or `None` while it still runs at
        the deadline (`timeout=None`: none).

        The first process: this process's waiter record if it holds one,
        else `<jail_dir>/exit`, written by the exit wrapper (decision-156).
        A sibling this agent started: its own `Popen`, and the first status
        observed deregisters it, once.

        Raises:
            ExitStatusUnobservable: the first process is gone and neither
                source recorded how it ended; or `process` is a sibling this
                agent did not start, whose status nothing records.
        """
        if process == self._jail.first:
            return self._wait_first(timeout)
        proc = self._spawned.get(process.pid)
        if proc is None:
            raise ExitStatusUnobservable(
                f"pid {process.pid} was not started by this agent, and nothing records how a "
                f"sibling in jail {self._jail.jail_id!r} ended"
            )
        try:
            status = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        if process.pid not in self._deregistered:
            _execs.deregister(self._jail.jail_dir, process.pid)
            self._deregistered.add(process.pid)
        return status

    def _wait_first(self, timeout: float | None) -> int | None:
        """`Handle.wait`'s loop before decision-178, unchanged but for
        returning `None` at the deadline instead of raising.

        Raises:
            ExitStatusUnobservable: gone, and no record in either place.
        """
        first = self._jail.first
        jail_dir = self._jail.jail_dir
        deadline = math.inf if timeout is None else time.monotonic() + timeout
        next_liveness_check = 0.0
        gone = False
        while True:
            record = _waiters.recorded_exit(first.pid)
            if record is not None:
                return record.returncode
            recorded = _exit_status.read_exit_status(jail_dir)
            if recorded is not None:
                return recorded
            if gone:
                # Gone, and no record in either place. Give the wrapper and
                # the waiter thread a moment -- ending, writing and
                # recording are not one atomic step.
                grace = time.monotonic() + 1.0
                while time.monotonic() < grace:
                    record = _waiters.recorded_exit(first.pid)
                    if record is not None:
                        return record.returncode
                    recorded = _exit_status.read_exit_status(jail_dir)
                    if recorded is not None:
                        return recorded
                    time.sleep(0.02)
                raise ExitStatusUnobservable(
                    f"pid {first.pid} is gone and nothing recorded how jail "
                    f"{self._jail.jail_id!r} ended: no exit file at "
                    f"{_exit_status.exit_path(jail_dir)!r} and no observation in "
                    "this process"
                )
            now = time.monotonic()
            if now >= next_liveness_check:
                # Liveness costs a process-table read on every platform but
                # Linux (`brig/run/_identity.py`), so this loop asks it on a
                # slower cadence than it polls the two cheap sources above.
                # The answer is the same answer, at most `_LIVENESS_POLL_S`
                # later.
                gone = not _identity.identity_holds(first.pid, first.start_time)
                next_liveness_check = now + _LIVENESS_POLL_S
                continue
            if now > deadline:
                return None
            time.sleep(0.02)

    def stop(self, process: ProcessRecord) -> KillReport:
        """SPEC.md section 9's ladder against `process`'s group alone,
        verified: one item, `workload_group` for the first process and
        `exec_sibling` for any other. A sibling stays registered, as after
        `destroy`, so a later `destroy` reports it `ALREADY_GONE`."""
        kind = "workload_group" if process == self._jail.first else "exec_sibling"
        return KillReport(items=(end_group(kind, process.pgid, process.pid, process.start_time),))
