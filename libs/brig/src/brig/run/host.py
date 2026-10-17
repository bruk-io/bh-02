"""`HostRuntime`: brig's own runtime, the one every jail ran under before it had a name.

SPEC.md section 3 (decision-178, decision-0001 step 1). Its instance is host
process groups. Since decision-181 (TASK-0079.25) `create` holds no process:
it makes `jail_dir`, clears what an earlier jail left there (refused while any
of it runs), stages files, runs and starts the helpers, derives `wrap_prefix`
and keeps the tether; every process, the first included, is a
`HostSupervisor.start`, with its own exit wrapper, its own tether watcher and
its own records directory `<jail_dir>/procs/<id>/` (`brig/run/_records.py`).
`destroy` is SPEC.md section 9's verified ladder per process in start order,
then every `JAIL_LIFETIME` helper (`brig/run/teardown.py`); `HostSupervisor`
signals a group after checking its leader's identity, waits through the exit
waiter or the process's exit record, and stops one group with the same ladder.

Everything here is what the launcher, the handle's `interrupt` and `wait`, and
its `exec` did before decision-178, moved rather than changed; decision-183
deleted those callers, and `Jail` (`brig/run/jail.py`) is this runtime's
embedder-side face. The notes on that code follow:

**`wrap_prefix` (task-046).** Every start (SPEC.md §9) must place its
process inside the same confinement `jail.wrap` compiled -- but a jail's dict
cannot carry the `CompiledJail.wrap` callable across `to_dict`/`from_dict`'s
process boundary. So `create` DERIVES `wrap_prefix` once
(`_derive_wrap_prefix`, against a fixed sentinel argv, `_WRAP_SENTINEL`,
decision-181): the tuple of tokens `jail.wrap` prepended ahead of `argv`,
verified -- not assumed -- to be a pure prefix (the wrap's output ends in
exactly `argv`, unchanged). `HostSupervisor.start` then reproduces
`jail.wrap`'s effect on any argv by literally prepending this same prefix,
and refuses outright when the verification found no pure prefix
(`wrap_prefix is None`) rather than spawn a weaker process.

**The exit wrapper (decision-156, 2026-09-08).** A start does not spawn the
compiled jail's argv directly. It spawns `brig/run/_exit_status.py`'s wrapper
program, which spawns that argv as its own child, waits for it, and writes
the status to the process's exit record, `<jail_dir>/procs/<id>/exit`
(decision-181) -- so a `Jail` rehydrated in a process that never parented the
workload can still read how it ended. The wrapper prepends NOTHING to the
jail's argv: `wrap_prefix` is still derived against `jail.wrap`'s own output,
`Process.argv` reports the jail's compiled argv, and what runs inside the
confinement is byte for byte what ran before. `Process.pid` names the wrapper
and the jail's own process is its child in the same group -- teardown is
group-shaped at every rung, so nothing about it depends on which of the two
the pid names. See that module for the `SIGKILL` case it cannot cover. A
`JAIL_LIFETIME` helper is started under the same wrapper, on the host and not inside
the jail, for the watcher that ties it to the jail's tether or lifeline (decision-199).

**Start-time stamps (decision-155, 2026-09-08).** Every process leader's pid
and every `JAIL_LIFETIME` helper's pid are recorded together with the moment
that process started (`brig/run/_identity.py`), because a pid alone is a slot
rather than an occupant: an OS that recycled the number between start and
teardown would have `alive()` reporting a stranger as this jail and teardown
signalling one. The stamps ride in the records and the jail's dict, so a
rehydrated jail compares them too.
"""

import contextlib
import errno
import math
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from brig.core.runtime import Capability, RuntimeKind, SupervisorPlan, channel_dir
from brig.mech import HelperLifetime
from brig.run import _exit_status, _identity, _records, _waiters
from brig.run._spawn_pgid import spawn_pgid
from brig.run._supervised import LinkedSupervisor
from brig.run._supervisor_link import SupervisorGone, SupervisorLink
from brig.run._supervisor_program import PROTOCOL, SUPERVISOR_SOURCE, supervisor_argv
from brig.run._tether import HeldLifeline, HeldTether
from brig.run.dial import dial
from brig.run.exec_ import ExecWrapNotAPrefix
from brig.run.runtime import (
    ExitStatusUnobservable,
    Held,
    IoPolicy,
    JailRecord,
    ProcessNamespaces,
    ProcessRecord,
    Reservation,
    Supervisor,
    SupervisorRecord,
    channel_dir_of,
    refuse_foreign_reservation,
    reserved_socket,
    socket_endpoint,
)
from brig.run.teardown import (
    DEFAULT_GRACE_S,
    KillOutcome,
    KillReport,
    UnreadableProcessTable,
    end_group,
    kill_named,
    live_groups,
    read_process_table,
)
from brig.stack import CompiledJail

#: How long a LAUNCH_SCOPED helper may take to finish. It is a preparation
#: step, not work: the ceiling exists to turn "declared with the wrong
#: lifetime" from a silent hang into a named failure, not to bound honest
#: slowness, so it is generous.
_LAUNCH_SCOPED_TIMEOUT_S: Final = 120.0


#: How often `HostSupervisor.wait` re-asks whether the first process is alive
#: while polling. The two cheap sources (this process's waiter record, the
#: exit file) are polled far more often; the liveness question exists only
#: to turn "still running" into "gone, and nothing recorded it", and paying a
#: `/bin/ps` fifty times a second to ask it sooner buys nothing.
_LIVENESS_POLL_S: Final = 0.25


#: How long a supervisor may take to import everything and say hello (decision-191). A jail
#: whose bwrap or interpreter fails ends the socket at once, which is read as the failure it
#: is; this is for a host too loaded to start a Python in time, so it is generous.
_SUPERVISOR_READY_TIMEOUT_S: Final = 60.0

#: `<jail_dir>/supervisor`: the supervisor's own stdio and exit record, host-opened, which no
#: grant reaches (the jail directory is sealed, decision-173).
_SUPERVISOR_DIRNAME: Final = "supervisor"


class SupervisorFailed(RuntimeError):
    """The jail's supervisor did not start, so there is no jail: bwrap or the interpreter
    failed, the protocol is not the one this brig speaks, or nothing was heard within the
    time a start is given (decision-191). The message carries what the supervisor's own stderr
    said (bwrap's errors included) and where it is."""


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
    holds, `None` where it does not -- every start (SPEC.md §9) refuses on
    `None` rather than spawn a weaker process.

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


def _make_channel_dir(jail_dir: str) -> None:
    """Make the jail's channel directory, `<jail_dir>/chan` (decision-184),
    mode 0700, or keep the directory an earlier jail made there. Every
    mechanism that grants it binds or allows it by path, and a bind follows a
    link, so anything there that is not a directory (a link, a file) is
    refused rather than used.

    Raises:
        FileExistsError: `chan` is there and is not a directory.
        OSError: it could not be made or examined.
    """
    path = channel_dir(jail_dir)
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        if not stat.S_ISDIR(os.lstat(path).st_mode):
            raise FileExistsError(
                errno.EEXIST,
                "the jail's channel directory is there and is not a directory brig made "
                "(a link or a file), so granting it would grant whatever it names; remove "
                "it, or choose another jail directory",
                path,
            ) from None


def _spawn(
    wrapped_argv: tuple[str, ...],
    *,
    cwd: str,
    env: Mapping[str, str],
    stdout_path: str,
    stderr_path: str | None,
    exit_file: str,
    tether: int | None = None,
    stdin_fd: int | None = None,
    keep_fds: tuple[int, ...] = (),
    helper: str | None = None,
) -> subprocess.Popen[bytes]:
    """Spawn the jail's argv under the exit wrapper, detached, new group.

    `start_new_session=True` is what puts the group leader in its own
    process group and detaches it from the launching process's controlling
    terminal/session -- SPEC.md §8's "detached, new process group" for the
    `subprocess` launcher, in one keyword.

    The process this returns is `_exit_status.WRAPPER_SOURCE`, not the
    jail's argv: the wrapper spawns THAT as its own child, inheriting this
    cwd, env and stdio unchanged, and writes the status to `exit_file`, the
    process's own exit record, when it ends (decision-156, decision-181).
    `tether` is passed to this wrapper alone (`pass_fds`). `stdin_fd` is the workload's stdin,
    `/dev/null` when none (the supervisor's is the program's source, which `bwrap` reads from
    descriptor 0, decision-190), and `keep_fds` are inherited by the wrapper and its child
    alone (the supervisor's control socket, decision-191). `stderr_path` `None` sends stderr to
    `stdout_path`'s file, as a helper's log is (`helper` names the `JAIL_LIFETIME` helper
    this starts, decision-199, which runs on the host rather than inside the jail: only the
    error says so). The ready pipe is what
    keeps a workload that cannot be exec'd a LAUNCH failure rather than a
    handle for something already dead -- the wrapper writes one token
    through it the instant the spawn succeeds or fails, and closing it is
    the only other way this read can end.
    """
    read_fd, write_fd = os.pipe()
    try:
        with (
            open(stdout_path, "wb") as stdout_f,
            contextlib.ExitStack() as more,
            open(os.devnull, "rb") as devnull_f,
        ):
            proc = subprocess.Popen(
                _exit_status.wrapper_argv(
                    sys.executable, exit_file, write_fd, wrapped_argv, tether, keep_fds
                ),
                cwd=cwd,
                env=dict(env),
                stdin=devnull_f if stdin_fd is None else stdin_fd,
                stdout=stdout_f,
                stderr=(
                    subprocess.STDOUT
                    if stderr_path is None
                    else more.enter_context(open(stderr_path, "wb"))
                ),
                start_new_session=True,
                pass_fds=(write_fd, *(() if tether is None else (tether,)), *keep_fds),
            )
        os.close(write_fd)
        write_fd = -1
        token = os.read(read_fd, 4096)
    finally:
        if write_fd != -1:
            os.close(write_fd)
        os.close(read_fd)

    if token != b"ok":
        # The wrapper's group may hold its tether watcher, started before the
        # workload: end the group while the wrapper is still unreaped (so its
        # number can't be anyone else's), then reap the wrapper.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    kind = "workload" if helper is None else "helper"
    if token.startswith(b"err:"):
        raise _exit_status.WorkloadSpawnFailed(
            f"the {kind} {wrapped_argv[0] if helper is None else helper!r} could not be spawned "
            f"{'inside its jail' if helper is None else 'on the host'}: "
            + token[4:].decode(errors="replace")
        )
    if token != b"ok":
        raise _exit_status.WorkloadSpawnFailed(
            f"the exit wrapper for {wrapped_argv[0]!r} ended before it spawned the "
            f"{kind} (reported {token!r}); see {stdout_path if stderr_path is None else stderr_path}"
        )
    return proc


def _helper_tether(
    jail: CompiledJail, tether: HeldTether | None
) -> tuple[HeldLifeline | None, int | None]:
    """What a jail's `JAIL_LIFETIME` helpers are tethered to (decision-199), and the descriptor
    their wrappers' watchers read: the jail's tether when it has one, as every process of it is;
    else, for a supervised jail, a lifeline it makes, whose write end it alone holds (its
    processes end with the socket its supervisor reads, and a helper can't watch that); else
    nothing, since nothing ties an unsupervised, untethered jail's processes to its creator
    either. Nothing is made, and a tether that has ended is not asked, for a jail with no
    `JAIL_LIFETIME` helper.

    Raises:
        TetherClosed: the jail's tether has already ended, so a helper started now would be
            ended at once.
        OSError: the lifeline's pipe could not be made.
    """
    if not any(helper.lifetime is HelperLifetime.JAIL_LIFETIME for helper in jail.helpers):
        return None, None
    if tether is not None:
        return None, tether.fd()
    if jail.supervisor is None:
        return None, None
    lifeline = HeldLifeline()
    return lifeline, lifeline.fd()


def _start_helpers(
    jail: CompiledJail, *, cwd: str, env: Mapping[str, str], jail_dir: str, tether: int | None
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Start `Step.helpers`, returning the pids AND start-time stamps of the
    ones that persist (`_identity.start_stamp`, decision-155 -- a pid alone
    is a number a later teardown can find pointing at a stranger).

    `Helper` and `HelperLifetime` have been in the mechanism contract since
    M2 and nothing ever started one -- the declared-but-uncalled shape this
    repo's guidance names as its recurring defect. M6's `connect_proxy` is
    the first mechanism that needs them, so they run now.

    Two lifetimes, and the difference is when this function returns:

    `LAUNCH_SCOPED` helpers run to COMPLETION here, before the workload is
    spawned -- "gone before the workload runs" (SPEC.md §6) is a guarantee
    the workload can rely on, not a hope, so this blocks on them. A non-zero
    exit is a launch failure: a helper that was supposed to prepare
    something and did not must not be followed by a workload assuming it
    did.

    `JAIL_LIFETIME` helpers are started like a process of the jail, under
    the exit wrapper (`_spawn`), detached in a group of their own, and their
    pids returned so the jail's record can carry them (the wrapper's: its
    group is the helper's, and it lives exactly as long as the helper does).
    Their log is `helper-<name>.log`, stdout and stderr together, and their
    exit record `helper-<name>.exit`, which nothing reads.

    A helper is ended two ways. By `destroy`, through the pid and start stamp
    the record carries (SPEC.md §9, decision-132): a pid recorded in the jail's
    dict survives serialization, so a rehydrated jail in another process can
    kill a helper it never started, which an inherited pipe fd could never give
    it. And, when nobody is left to call `destroy`, by `tether` (decision-199):
    the read end of the jail's tether, or of a supervised jail's lifeline, which
    the wrapper's watcher reads from before the helper starts, ending the
    helper's group once every write end is closed, the creator's death
    included. `None`: nothing ties the helper to its creator, as nothing ties
    the jail's processes (`_helper_tether`).

    Raises:
        HelperFailed: a `LAUNCH_SCOPED` helper exited non-zero or did not finish.
        WorkloadSpawnFailed: a `JAIL_LIFETIME` helper could not be spawned.
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
        proc = _spawn(
            tuple(helper.argv),
            cwd=cwd,
            env=env,
            stdout_path=os.path.join(jail_dir, f"helper-{helper.name}.log"),
            stderr_path=None,
            exit_file=os.path.join(jail_dir, f"helper-{helper.name}.exit"),
            tether=tether,
            helper=helper.name,
        )
        # Deliberately NOT held: unlike the workload, a helper's exit STATUS
        # is not a claim anyone makes, so letting `subprocess._cleanup` reap
        # it is harmless. What matters is that it can be KILLED, and a pid in
        # the jail's record is what gives every teardown path -- including a
        # rehydrated one in another process -- the ability to do that.
        persistent.append(proc.pid)
        # Read while the helper is as young as it will ever be: the stamp
        # is what makes `helper_pids` an identity rather than a number a
        # later teardown might find pointing at a stranger (decision-155).
        stamps.append(_identity.start_stamp(proc.pid))
    return tuple(persistent), tuple(stamps)


def _source_fd() -> int:
    """A descriptor at offset 0 of an anonymous memory file holding the supervisor's program,
    which `bwrap` reads to end-of-file from its stdin (`--ro-bind-data 0`, decision-190): the
    program reaches the jail from the host's memory, never from a file anyone could write.

    Raises:
        OSError: no memory file could be made (not Linux, or out of descriptors)."""
    fd = os.memfd_create("brig-supervisor")
    try:
        data = memoryview(SUPERVISOR_SOURCE.encode())
        while data:
            data = data[os.write(fd, data) :]
        os.lseek(fd, 0, os.SEEK_SET)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _log_tail(path: str, size: int = 2000) -> str:
    """The end of the log at `path`, for an error that says what the supervisor's own stderr
    said (bwrap's mount errors land there); empty when it can't be read."""
    try:
        with open(path, "rb") as log:
            return log.read()[-size:].decode(errors="replace").strip()
    except OSError:
        return ""


def _launch_supervisor(
    plan: SupervisorPlan,
    *,
    jail: CompiledJail,
    wrap_prefix: tuple[str, ...] | None,
    env: Mapping[str, str],
    cwd: str,
    jail_dir: str,
    jail_id: str,
    tether: HeldTether | None,
) -> tuple[SupervisorRecord, SupervisorLink, ProcessNamespaces]:
    """Start the jail's supervisor, the jail's only process until it starts others, and wait
    for it to say it is ready (decision-191, decision-192), and what it says about the namespaces
    its processes will have (decision-195).

    It runs `(*wrap_prefix, *supervisor_argv)` under its own exit wrapper, detached in a new
    process group, tethered when the jail is, exactly as any process of an unsupervised jail
    was: that group is the instance, and ending it ends the jail. Its stdin is its program's
    source (read by `bwrap`, stage 7a), its stdout and stderr files in `<jail_dir>/supervisor/`,
    and its control socket, a `SOCK_SEQPACKET` socketpair made here before it exists, a
    descriptor the wrapper and its child keep and nothing else does.

    Raises:
        ExecWrapNotAPrefix: the compiled wrap is not a pure argv prefix, or does not map the
            supervisor's argv to it followed by the argv.
        TetherClosed: the jail's tether has already ended.
        WorkloadSpawnFailed: the supervisor's own argv could not be spawned.
        SupervisorFailed: the supervisor never said it was ready; the instance was ended first.
        OSError: the supervisor's directory, files or program could not be made.
    """
    directory = os.path.join(jail_dir, _SUPERVISOR_DIRNAME)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    stdout_path = os.path.join(directory, "stdout.log")
    stderr_path = os.path.join(directory, "stderr.log")
    host_end, jail_end = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    source = -1
    try:
        argv = supervisor_argv(plan, jail_end.fileno())
        if wrap_prefix is None or tuple(jail.wrap(argv)) != (*wrap_prefix, *argv):
            raise ExecWrapNotAPrefix(wrap_prefix, argv)
        tether_fd = None if tether is None else tether.fd()
        source = _source_fd()
        proc = _spawn(
            (*wrap_prefix, *argv),
            cwd=cwd,
            env=env,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            exit_file=os.path.join(directory, _records.EXIT_FILENAME),
            tether=tether_fd,
            stdin_fd=source,
            keep_fds=(jail_end.fileno(),),
        )
    except BaseException:
        host_end.close()
        raise
    finally:
        jail_end.close()
        if source != -1:
            os.close(source)
    pid = proc.pid
    stamp = _identity.start_stamp(pid)
    _waiters.watch(proc, jail_id=jail_id)  # reaped when its wrapper ends, as every start's is

    def unresponsive() -> None:
        end_group("supervisor", pid, pid, stamp, grace=0.0)  # a deadline passed: at once

    link = SupervisorLink(host_end, unresponsive=unresponsive)
    try:
        hello = link.wait_hello(_SUPERVISOR_READY_TIMEOUT_S)
        problem = (
            None
            if hello.get("protocol") == PROTOCOL
            else f"it speaks protocol {hello.get('protocol')!r} and this brig speaks {PROTOCOL}"
        )
    except SupervisorGone:
        problem = "its control socket closed before it said it was ready"
    except TimeoutError:
        problem = f"it said nothing within {_SUPERVISOR_READY_TIMEOUT_S}s"
    if problem is not None:
        link.close()
        item = end_group("supervisor", pid, pid, stamp, grace=0.0)
        said = _log_tail(stderr_path)
        raise SupervisorFailed(
            f"brig's supervisor did not start in jail {jail_id!r}: {problem}. Its stderr "
            f"({stderr_path}) said: {said or 'nothing'}. Usual causes: the interpreter "
            f"{plan.interpreter!r} is missing from the jail or older than Python 3.9, "
            "bubblewrap refused a mount, or the kernel has no pidfd (Linux 5.3)"
            + (
                ""
                if item.outcome is not KillOutcome.FAILED
                else f"; ending it failed: {item.detail}"
            )
        )
    return SupervisorRecord(pid=pid, start_time=stamp), link, _namespaces_of(hello)


def _namespaces_of(hello: Mapping[str, Any]) -> ProcessNamespaces:
    """What a supervisor's hello says of its processes' namespaces (decision-195): held, or
    not and why. A hello that says nothing of them, or something that is not that, is not held:
    no claim is made on a supervisor's silence."""
    said = hello.get("namespaces")
    if isinstance(said, dict) and isinstance(said.get("held"), bool):
        reason = said.get("reason")
        return ProcessNamespaces(said["held"], reason if isinstance(reason, str) else "")
    return ProcessNamespaces(False, "the supervisor did not say whether it could")


def _refused(jail: CompiledJail, capabilities: frozenset[Capability]) -> frozenset[Capability]:
    """The capabilities `jail` requires that `capabilities` lacks."""
    return jail.requires - capabilities


#: The argv `create` applies the compiled `wrap` to, to derive `wrap_prefix`
#: (decision-181), since `create` has no process's argv to derive it from. Each
#: token holds a NUL, which no real argv can (`execve` takes C strings, and
#: `subprocess` refuses an embedded NUL), so it never equals an argv a start
#: is asked for. Two tokens, so a wrap that rewrites either the first or a
#: later argument fails the prefix check here, and in the creating process
#: every start also checks `wrap` of its own argv against the prefix.
_WRAP_SENTINEL: Final = ("\x00brig-wrap-sentinel-argv0", "\x00brig-wrap-sentinel-argv1")


def _clear_earlier_records(
    jail_dir: str, *, read_table: Callable[[], str] = read_process_table
) -> None:
    """Remove the records an earlier jail left under `<jail_dir>/procs`, once
    nothing they name runs; on any doubt remove nothing and refuse
    (decision-181). Per record, the stamp before the group
    (`_records.standing`): a leader that holds its identity runs; one whose pid
    now names another process holds no group; one that is gone runs while its
    group has a live member. An unreadable record, an unknown stamp, a link or
    a file under `procs/`, or a process table that can't be read is a doubt.
    `read_table` is the process table's seam, as `group_alive`'s.

    Raises:
        _records.JailDirInUse: something a record names runs, or is in doubt.
        OSError: the records could not be removed.
    """
    scanned = _records.scan(jail_dir)
    if not scanned.records and not scanned.unreadable:
        return
    try:
        live: frozenset[int] | None = live_groups(read_table())
    except OSError, subprocess.CalledProcessError, UnreadableProcessTable:
        live = None
    pids = {record.pid for record in scanned.records}
    held = _records.held_by(
        jail_dir,
        scanned,
        stamps={pid: _identity.start_stamp(pid) for pid in pids},
        zombies=frozenset(pid for pid in pids if _identity.is_zombie(pid)),
        live_groups=live,
    )
    if held:
        raise _records.JailDirInUse(jail_dir, held)
    _records.remove_procs(jail_dir)


@dataclass(frozen=True, slots=True)
class HostRuntime:
    """Host process groups as a jail's instance (decision-178).

    Holds no state: everything a later call needs is in the `JailRecord`
    `create` returns and in the records under `<jail_dir>/procs`, so a record
    rehydrated in another process is controlled the same way. What does not
    cross processes is what `_waiters` holds (the exit observation) and the
    record's `Held` (the compiled wrap, the sensors, the tether); each
    process's exit record stands in for the first elsewhere."""

    kind: RuntimeKind = RuntimeKind.HOST
    capabilities: frozenset[Capability] = frozenset(
        {Capability.NEW_PROCESS_GROUP, Capability.DETACH}
    )

    def create(
        self,
        jail: CompiledJail,
        *,
        cwd: str,
        jail_id: str,
        jail_dir: str,
        tether: int | None,
    ) -> JailRecord:
        """Make the jail's instance, with no process in it (decision-181):
        create `jail_dir`, clear the records an earlier jail left there
        (refused while any of it runs or is in doubt), make its channel
        directory `<jail_dir>/chan` (decision-184), write `jail.staged`,
        then the jail's own record (`jail.json`: whether it is tethered),
        run `LAUNCH_SCOPED` helpers to completion and start `JAIL_LIFETIME`
        ones, and derive `wrap_prefix` once, from `jail.wrap` applied to a
        fixed sentinel argv, verified as a pure prefix (`None`: every start
        refuses). Spawns no workload: every process is a `HostSupervisor.start`, or, in a
        jail whose compiled stack declares a supervisor (decision-190), a request to the
        supervisor `create` starts here as the jail's PID 1 and waits to be ready
        (`_launch_supervisor`, decision-191).

        `tether` (decision-167, SPEC.md section 8) is the read end of a pipe
        whose write end the caller keeps: the jail holds a duplicate of it
        (`HeldTether`), so the caller may close its own read end once this
        returns, and every start is tethered to it, and every `JAIL_LIFETIME`
        helper too (decision-199). `None`: the jail lives until its processes
        end or it is destroyed, and so do its helpers, but for a supervised jail's:
        those end when the jail object is collected or its creator dies, as its
        processes do (`_helper_tether`).

        Raises:
            ValueError: `jail` was compiled for another runtime than this one's `kind`
                (decision-202: a container's jail is not made of host process groups).
            LaunchRefused: `jail.requires` names a feature `capabilities`
                lacks.
            _records.JailDirInUse: `jail_dir` holds an earlier jail's records
                and something they name runs, or brig can't tell.
            HelperFailed: a `LAUNCH_SCOPED` helper exited non-zero or did not
                finish.
            ExecWrapNotAPrefix: a supervised jail's wrap is not a pure argv
                prefix (decision-190).
            TetherClosed: a supervised jail's tether has already ended, or a
                tethered jail has a `JAIL_LIFETIME` helper and its tether has.
            WorkloadSpawnFailed: a `JAIL_LIFETIME` helper, or a supervised
                jail's supervisor, could not be spawned.
            SupervisorFailed: a supervised jail's supervisor never said it was
                ready; what `create` started is ended first.
            OSError: `tether` is not an open descriptor, or `jail_dir` could
                not be made or written, or its `chan` is there and is not a
                directory (`FileExistsError`).
        """
        if jail.runtime is not self.kind:
            raise ValueError(
                f"HostRuntime.create: the jail was compiled for the {jail.runtime.value} runtime, "
                f"and this is the {self.kind.value} runtime; pass the jail to a runtime of its "
                "kind (SPEC.md section 8, decision-202)"
            )
        missing = _refused(jail, self.capabilities)
        if missing:
            raise LaunchRefused(missing, "host")

        tether_hold = None if tether is None else HeldTether(tether)
        os.makedirs(jail_dir, exist_ok=True)
        _clear_earlier_records(jail_dir)
        _make_channel_dir(jail_dir)
        _write_staged_files(jail_dir, jail)

        # SPEC.md §9's exec fidelity depends on this: every start trusts
        # `wrap_prefix` to reproduce the jail's compiled wrap for its own argv,
        # so it is DERIVED and VERIFIED here, once, against the compiled wrap's
        # actual output -- never assumed from the mechanism roster.
        wrap_prefix = _derive_wrap_prefix(tuple(jail.wrap(_WRAP_SENTINEL)), _WRAP_SENTINEL)

        # The env is the creating process's own environment overlaid with the
        # jail's compiled env (SPEC.md §7 Composition: mechanism env merges,
        # later-wins); scrubbing is a mechanism's job.
        full_env: dict[str, str] = {**os.environ, **jail.env}
        # Whether this jail is tethered, kept apart from any dict, so a jail
        # rehydrated from a hand-edited one can't start untethered (TASK-0079.26).
        # Written after the staged files, so no staged file can stand in for it.
        _records.write_jail_record(jail_dir, jail_id=jail_id, tethered=tether is not None)
        lifeline, helper_tether = _helper_tether(jail, tether_hold)
        helper_pids, helper_stamps = _start_helpers(
            jail, cwd=cwd, env=full_env, jail_dir=jail_dir, tether=helper_tether
        )

        instance: SupervisorRecord | None = None
        link: SupervisorLink | None = None
        namespaces: ProcessNamespaces | None = None
        if jail.supervisor is not None:
            # A jail whose PID 1 is brig's supervisor (decision-190): the whole composed wrap
            # runs around it, once, and every process of the jail is a request to it.
            try:
                instance, link, namespaces = _launch_supervisor(
                    jail.supervisor,
                    jail=jail,
                    wrap_prefix=wrap_prefix,
                    env=full_env,
                    cwd=cwd,
                    jail_dir=jail_dir,
                    jail_id=jail_id,
                    tether=tether_hold,
                )
            except BaseException:
                kill_named(
                    known=(),
                    jail_dir=jail_dir,
                    helper_pids=helper_pids,
                    helper_stamps=helper_stamps,
                )
                raise
        held = Held(
            wrap=jail.wrap, sensors=jail.sensors, tether=tether_hold, link=link, lifeline=lifeline
        )

        return JailRecord(
            kind=self.kind,
            jail_id=jail_id,
            jail_dir=jail_dir,
            cwd=cwd,
            jail_env=frozendict(jail.env),
            wrap_prefix=wrap_prefix,
            helper_pids=helper_pids,
            helper_stamps=helper_stamps,
            supervisor=instance,
            namespaces=namespaces,
            held=held,
        )

    def alive(self, jail: JailRecord) -> bool:
        """Whether anything of the jail runs (decision-181): a process it
        started whose leader holds its identity -- each known process by the
        identity `jail` holds, then every other record under `procs/` -- or a
        `JAIL_LIFETIME` helper that does. A recycled pid and a zombie read gone
        (decision-155, decision-171); an unknown stamp degrades to the pid-only
        check. A jail with nothing started and no helper reads gone. This
        answers for leaders; `destroy` is what ends groups. A supervised jail
        (decision-192) is alive while its supervisor's group leader holds its
        identity, with or without a process in it."""
        return (
            any(self.process_alive(jail, process) for process in self.processes(jail))
            or (
                jail.supervisor is not None
                and _identity.identity_holds(jail.supervisor.pid, jail.supervisor.start_time)
            )
            or any(
                _identity.identity_holds(pid, stamp)
                for pid, stamp in zip(jail.helper_pids, jail.helper_stamps, strict=True)
            )
        )

    def processes(self, jail: JailRecord) -> tuple[ProcessRecord, ...]:
        """The processes `jail` holds, by the records it holds, then every
        other readable record under `<jail_dir>/procs`, each in start order. A
        disk copy of a held process is not used (decision-181); `destroy`
        reports one that disagrees."""
        held = {process.id for process in jail.processes}
        return (
            *jail.processes,
            *(p for p in _records.scan(jail.jail_dir).records if p.id not in held),
        )

    def tethered(self, jail: JailRecord) -> bool | None:
        """What `<jail_dir>/jail.json` says, written by `create`; `None` when
        it is missing, unreadable, or names another jail."""
        return _records.read_tethered(jail.jail_dir, jail.jail_id)

    def process_alive(self, jail: JailRecord, process: ProcessRecord) -> bool:
        """Whether `process`'s leader holds its identity: a recycled pid and a
        zombie read gone (decision-155, decision-171); an unknown stamp
        degrades to the pid-only check."""
        del jail
        return _identity.identity_holds(process.pid, process.start_time)

    def destroy(self, jail: JailRecord, *, grace: float = DEFAULT_GRACE_S) -> KillReport:
        """SPEC.md section 9's ladder per process in start order -- the ones
        `jail` holds, then every other record under `procs/` -- then every
        `JAIL_LIFETIME` helper, each verified (`teardown.kill_named`). Total:
        raises nothing from an item.

        In a supervised jail (decision-191, decision-192) each process's group is laddered
        first, as in any jail, and then the instance: the link is closed just before its
        ladder, so the supervisor reads end-of-file and ends everything it holds, which is the
        prompt end (a supervisor's PID 1 drops the ladder's `SIGTERM`, so the ladder alone would
        wait out its grace), and the ladder verifies it, `SIGKILL` included. With `grace` 0
        it is the other way about: the instance is killed first, at once (decision-193)."""
        held = jail.held
        return kill_named(
            known=jail.processes,
            jail_dir=jail.jail_dir,
            helper_pids=jail.helper_pids,
            helper_stamps=jail.helper_stamps,
            supervisor=(
                None
                if jail.supervisor is None
                else (jail.supervisor.pid, jail.supervisor.start_time)
            ),
            end_of_file=None if held is None or held.link is None else held.link.close,
            grace=grace,
        )

    def supervisor(self, jail: JailRecord) -> Supervisor | None:
        """The supervisor bound to `jail`: a `HostSupervisor` for an unsupervised jail, which
        starts a process from the record alone; for a supervised one (decision-192) a
        `LinkedSupervisor` over the link only the process that created it holds, and `None` in
        any other, which can be destroyed and nothing else."""
        if jail.supervisor is None:
            return HostSupervisor(jail)
        link = None if jail.held is None else jail.held.link
        return None if link is None else LinkedSupervisor(jail, link)

    def reserve(self, jail: JailRecord, channel: str) -> Reservation:
        """A fresh socket in `jail`'s channel directory, under the jail
        directory resolved, as the mechanisms grant it (decision-184): its
        name 16 hex characters from `secrets` and `.sock`, never reused. The
        host shares the jail's paths, so the host dials the path the process
        binds, unless the jail's processes have mount namespaces of their own, where it is the
        directory the process sees over the channel directory (decision-196)."""
        path = reserved_socket(channel_dir_of(jail), _records.new_id())
        private = jail.namespaces is not None and jail.namespaces.held
        return Reservation(
            channel=channel, bound_path=path, endpoint=socket_endpoint(path, namespaces=private)
        )

    def endpoint(self, jail: JailRecord, process: ProcessRecord) -> str | None:
        """The path to dial `process`'s socket at: the one it binds, which the host shares
        (decision-184), or the one in the directory of its own when it has a mount namespace
        (decision-196)."""
        del jail
        if process.bound_path is None:
            return None
        return socket_endpoint(process.bound_path, namespaces=process.namespaces)

    def ready(self, jail: JailRecord, process: ProcessRecord) -> bool:
        """Whether `connect` to `process`'s socket succeeds now, closed at
        once; never whether the path exists (SPEC.md section 10). `False` for
        a process with no channel and while nothing listens.

        Raises:
            EndpointRefused: what is at its socket is not its own listener
                (decision-185), or the kernel could not say who listens there
                (decision-186): only "nothing listens yet" reads `False`.
        """
        if process.bound_path is None:
            return False
        try:
            self.connect(jail, process).close()
        except OSError:
            return False
        return True

    def connect(self, jail: JailRecord, process: ProcessRecord) -> socket.socket:
        """A connected socket to `process`'s reserved socket (decision-185):
        refused before connecting when its path is a link or not a socket, and
        closed and refused after when its listener is not a process of
        `process`'s group led by its recorded leader (`brig/run/dial.py`).

        Raises:
            ValueError: `process` was started with no channel.
            EndpointRefused: the path is a link or not a socket, or the peer is
                not `process`'s own.
            OSError: nothing listens there yet.
        """
        endpoint = self.endpoint(jail, process)
        if endpoint is None:
            raise ValueError(f"process {process.id} was started with no channel to connect to")
        return dial(
            endpoint, group=process.pgid, leader_pid=process.pid, leader_stamp=process.start_time
        )


def _end_unrecorded(process: ProcessRecord, jail_dir: str, error: OSError) -> None:
    """A start whose `record.json` could not be written: its process runs
    unrecorded, so end its group now, through the ladder and its guards, and
    remove its records directory once it is gone. Says what happened on
    `error`, which the caller re-raises (decision-181)."""
    item = end_group("exec_sibling", process.pgid, process.pid, process.start_time)
    if item.outcome in (KillOutcome.ENDED, KillOutcome.ALREADY_GONE):
        with contextlib.suppress(OSError):
            shutil.rmtree(_records.process_dir(jail_dir, process.id))
        error.add_note(
            f"its record could not be written, so the process (pid {process.pid}) was "
            "ended and its records directory removed; nothing of it runs"
        )
    else:
        error.add_note(
            f"its record could not be written, and ending its process group {process.pgid} "
            f"failed ({item.detail}); end it yourself (`kill -KILL -- -{process.pgid}`)"
        )


@dataclass(frozen=True, slots=True)
class HostSupervisor:
    """Starts, signals, waits for and stops processes in one host jail.

    Holds nothing but the jail's record: each process's exit observation is
    the exit waiter's (`_waiters`) and its exit record's, never a `Popen` held
    here, so a process started through one supervisor is waited through any
    other, in this process or a later one."""

    jail: JailRecord

    def start(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        io: IoPolicy,
        channel: Reservation | None = None,
    ) -> ProcessRecord:
        """Start `argv` in the jail (decision-181): `(*wrap_prefix, *argv)`
        under its own exit wrapper, detached in a new process group, env
        `{**os.environ, **jail_env}`, stdin `/dev/null`, stdio per `io` in its
        own records directory `<jail_dir>/procs/<id>/`, made before the spawn;
        tethered when the jail is, by a watcher of its own started before the
        workload; its `record.json` written once the spawn returns, naming
        `channel`'s socket as the one it binds (decision-184).

        Raises:
            ReservationRefused: `channel` is not a socket `HostRuntime.reserve`
                would hand out for this jail, or a process the jail knows (in
                memory or under `procs/`) already binds it; raised before
                anything is made or spawned.
            ExecWrapNotAPrefix: the jail's wrap is not a pure argv prefix
                (`wrap_prefix is None`), or, where the compiled wrap is held,
                `wrap` of this argv is not the prefix followed by it; raised
                before anything is made or spawned.
            TetherClosed: the jail is tethered and its tether has ended; raised
                before anything is made or spawned.
            WorkloadSpawnFailed: the argv could not be spawned (`brig.run.WorkloadSpawnFailed`).
            OSError: the records directory or the record could not be written
                (a process whose record could not be written is ended first).
        """
        argv_t = tuple(argv)
        jail = self.jail
        wrap_prefix = jail.wrap_prefix
        if wrap_prefix is None:
            raise ExecWrapNotAPrefix(wrap_prefix, argv_t)
        spawned_argv = (*wrap_prefix, *argv_t)
        held = jail.held
        if held is not None and tuple(held.wrap(argv_t)) != spawned_argv:
            raise ExecWrapNotAPrefix(wrap_prefix, argv_t)
        tether_fd = None if held is None or held.tether is None else held.tether.fd()
        if channel is not None:
            refuse_foreign_reservation(jail, channel)

        process_id = _records.new_id()
        order = time.time_ns()
        directory = _records.make_dir(jail.jail_dir, process_id)
        stdout_path = os.path.join(directory, io.stdout_name)
        stderr_path = os.path.join(directory, io.stderr_name)
        # The creating process's env, overlaid with the jail's own, evaluated
        # fresh for every start (decision-152).
        spawn_env: dict[str, str] = {**os.environ, **jail.jail_env}
        try:
            proc = _spawn(
                spawned_argv,
                cwd=cwd,
                env=spawn_env,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                exit_file=os.path.join(directory, _records.EXIT_FILENAME),
                tether=tether_fd,
            )
        except BaseException:
            # Nothing was started (`_spawn` waits for a wrapper that could not
            # start its argv), so the directory records nothing; left, it
            # would hold the jail directory for the next `create`.
            shutil.rmtree(directory, ignore_errors=True)
            raise
        pid = proc.pid
        # decision-155: read the leader's start time now, while it is
        # certainly still the process this start just made. `UNKNOWN` when the
        # host can't read it; teardown then signals nothing for this record
        # and reports it FAILED while its group runs (decision-172).
        start_time = _identity.start_stamp(pid)
        # task-075: through `spawn_pgid`, because darwin's `getpgid()` raises
        # ESRCH for a process that has already exited; see that module.
        pgid = spawn_pgid(proc)
        # One thread owns this process's reap and records its status, and asks
        # the sensors what they make of its ending (brig/run/_waiters.py).
        _waiters.watch(proc, jail_id=jail.jail_id, sensors=() if held is None else held.sensors)
        process = ProcessRecord(
            id=process_id,
            order=order,
            pid=pid,
            pgid=pgid,
            start_time=start_time,
            argv=spawned_argv,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            channel=None if channel is None else channel.channel,
            bound_path=None if channel is None else channel.bound_path,
        )
        try:
            _records.write(jail.jail_dir, process)
        except OSError as error:
            _end_unrecorded(process, jail.jail_dir, error)
            raise
        return process

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
        """The exit status of `process`, or `None` while it still runs at the
        deadline (`timeout=None`: none). Deletes nothing: a record outlives
        its process's `wait` (decision-181).

        In the process that started it, only once its exit wrapper has exited
        and been reaped (this process's waiter record), so the process's leader
        has left when this returns (decision-182); a workload that left
        children in its group still holds the jail directory, and `create`
        rightly refuses until they are gone. Anywhere else, from the
        process's own exit record, written by its exit wrapper just before it
        exits (decision-156): that process cannot reap it, so the wrapper may
        still be leaving for a moment, and a `create` into the directory then
        refuses and says so.

        Raises:
            ExitStatusUnobservable: `process` is gone and neither source
                recorded how it ended.
            ValueError: its exit record does not hold an integer.
        """
        jail_dir = self.jail.jail_dir
        deadline = math.inf if timeout is None else time.monotonic() + timeout
        next_liveness_check = 0.0
        gone = False
        while True:
            status = _recorded_status(process, jail_dir)
            if status is not None:
                return status
            if gone:
                # Gone, and no record in either place. Give the wrapper and
                # the waiter thread a moment -- ending, writing and
                # recording are not one atomic step.
                grace = time.monotonic() + 1.0
                while time.monotonic() < grace:
                    status = _recorded_status(process, jail_dir)
                    if status is not None:
                        return status
                    time.sleep(0.02)
                where = (
                    _records.exit_path(jail_dir, process.id)
                    if _records.is_id(process.id)
                    else "no records directory"
                )
                raise ExitStatusUnobservable(
                    f"pid {process.pid} is gone and nothing recorded how it ended in jail "
                    f"{self.jail.jail_id!r}: no exit record at {where!r} and no observation "
                    "in this process"
                )
            now = time.monotonic()
            if now >= next_liveness_check:
                # Liveness costs a process-table read on every platform but
                # Linux (`brig/run/_identity.py`), so this loop asks it on a
                # slower cadence than it polls the two cheap sources above.
                gone = not _identity.identity_holds(process.pid, process.start_time)
                next_liveness_check = now + _LIVENESS_POLL_S
                continue
            if now > deadline:
                return None
            time.sleep(0.02)

    def stop(self, process: ProcessRecord) -> KillReport:
        """SPEC.md section 9's ladder against `process`'s group alone,
        verified: one item, `workload_group` for the jail's first process and
        `exec_sibling` for any other. Its record stays, as after `destroy`, so
        a later `destroy` reports it `ALREADY_GONE`."""
        first = self.jail.processes[0].id if self.jail.processes else None
        kind = "workload_group" if process.id == first else "exec_sibling"
        return KillReport(items=(end_group(kind, process.pgid, process.pid, process.start_time),))


def _chosen_status(waited: int, recorded: int | None) -> int:
    """The status to answer once this process's waiter has reaped the wrapper:
    the exit record's if the wrapper wrote one, else the waiter's. Pure.

    The record is the workload's own status; the waiter's is the wrapper's,
    which differs when the wrapper was killed after it wrote (decision-182)."""
    return waited if recorded is None else recorded


def _recorded_status(process: ProcessRecord, jail_dir: str) -> int | None:
    """How `process` ended, if anything recorded it: its exit record
    (decision-156, decision-181) once this process's waiter has reaped the
    wrapper, else this process's waiter alone (`_chosen_status`). While the
    waiter still owns the reap, nothing: the exit record is written before the
    wrapper has left, and `wait` answers once it has (decision-182).

    Raises:
        ValueError: its exit record does not hold an integer.
    """
    record = _waiters.recorded_exit(process.pid)
    if record is not None:
        return _chosen_status(record.returncode, _records.read_exit(jail_dir, process.id))
    if _waiters.is_watched(process.pid):
        return None
    return _records.read_exit(jail_dir, process.id)
