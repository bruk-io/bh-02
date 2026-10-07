"""`SubprocessLauncher`: detached, new-process-group, stdio-to-files.

SPEC.md §8:

    class Launcher(Protocol):
        name: str
        capabilities: frozenset[LaunchFeature]
        def launch(self, jail: CompiledJail, *, argv, cwd, io: IoPolicy) -> Handle: ...

    - `subprocess` -- pipes or files for stdio, detached, new process group.

    A launcher refuses a `CompiledJail` whose `requires` exceed its
    `capabilities`. Refusal names the missing feature.

`launch`'s literal SPEC signature (`jail`, `argv`, `cwd`, `io`) does not
carry a jail identity or a scratch directory -- SPEC.md §7's `CompiledJail`
doesn't have one either, and something has to mint the identity a `Handle`
and its stamped sensor records are keyed by. This module adds `jail_id` and
`jail_dir` as two more required keyword-only parameters, after the ones
SPEC.md §8 names verbatim, following `Stack.compile`'s own precedent
(task-017 added `ctx: CompileCtx | None` the same way) of extending a
schematic SPEC signature rather than fabricating a place inside one of its
named types to hide a workaround.

**`IoPolicy`** (ambiguity A8 in the M2 plan): SPEC.md §8 names the type in
`Launcher.launch`'s signature and never defines it. M2 ships the minimum
that MILESTONES.md's scope bullet asks for -- "stdio to files" -- as two
configurable filenames, written under `jail_dir`; stdin is always
`/dev/null` in M2, not configurable (pipes and ring buffers are the pty
launcher's, M8).

**`SubprocessLauncher.capabilities` is deliberately `{NEW_PROCESS_GROUP,
DETACH}` -- not `PTY`.** The pty launcher is M8; claiming a capability this
launcher cannot deliver is exactly the grading dishonesty SPEC.md law 1
forbids.

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

**`signatures` (task-047).** `jail.signatures` -- the `SignatureBook`
`Stack.compile` already assembled -- is passed through to `Handle` UNCHANGED;
this launcher neither builds nor inspects it. Nothing here needs to: the
book is compile-time data, not something a launch derives.

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

**Sensors, and the file that is no longer written (decision-152,
2026-09-08).** SPEC.md §6 says "`run` is the only layer permitted to write"
a mechanism sensor's payloads, and until now nothing in `run` called
`known_at_compile()` or `classify_exit()` at all -- the spec said so out
loud, because a sentence claiming a call site that did not exist would have
been specifying from the design. This launcher is that call site. It stamps
every sensor's `known_at_compile()` payloads with `ts` and this jail's
`jail_id` (`brig/run/events.py`) and puts the result on
`Handle.compile_events`; it hands the same sensors to the exit waiter, which
stamps `classify_exit()`'s answer when the workload ends
(`Handle.exit_events()`). Neither is written anywhere: the embedder owns a
log, and brig hands it records rather than keeping a second, worse one. The
per-jail `events.jsonl` file, its `EventLog` appender, and `SPAWN`/`EXEC`/
`EXEC_END`/`KILL`/`EXIT` lifecycle records are all deleted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from brig.mech import HelperLifetime, LaunchFeature
from brig.run import _exit_status, _identity, _waiters
from brig.run._spawn_pgid import spawn_pgid
from brig.run.events import stamp_all
from brig.run.handle import Handle
from brig.stack import CompiledJail


@dataclass(frozen=True, slots=True)
class IoPolicy:
    """M2's only io policy: stdout/stderr to files under the jail
    directory (filenames configurable; content mode is not), stdin from
    `/dev/null` (fixed, not configurable in M2)."""

    stdout_name: str = "stdout.log"
    stderr_name: str = "stderr.log"


#: How long a LAUNCH_SCOPED helper may take to finish. It is a preparation
#: step, not work: the ceiling exists to turn "declared with the wrong
#: lifetime" from a silent hang into a named failure, not to bound honest
#: slowness, so it is generous.
_LAUNCH_SCOPED_TIMEOUT_S: Final = 120.0


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

    def __init__(self, missing: frozenset[LaunchFeature], launcher_name: str) -> None:
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


class SubprocessLauncher:
    """SPEC.md §8's `subprocess` launcher: pipes or files for stdio,
    detached, new process group. M2 ships the files half; pipes arrive
    with a future milestone if a caller ever needs streamed stdio without a
    pty."""

    name = "subprocess"
    capabilities: frozenset[LaunchFeature] = frozenset(
        {LaunchFeature.NEW_PROCESS_GROUP, LaunchFeature.DETACH}
    )

    def launch(
        self,
        jail: CompiledJail,
        *,
        argv: Sequence[str],
        cwd: str,
        io: IoPolicy,
        jail_id: str,
        jail_dir: str,
        tether: int | None = None,
    ) -> Handle:
        """SPEC.md §8's five steps, in order:

        1. Refuse if `jail.requires - capabilities` is non-empty, naming
           the missing feature(s) via `LaunchRefused.missing`.
        2. Create `jail_dir`, clear any exit record an earlier launch
           left in it (decision-162), and write `jail.staged` into it.
        3. Spawn `jail.wrap(argv)`, detached, new process group, stdio per
           `io`, cwd and env from the jail.
        4. Stamp every sensor's `known_at_compile()` payloads.
        5. Return a `Handle` carrying them.

        `tether` (decision-167, SPEC.md section 8) is the read end of a pipe whose write end
        the caller keeps: once every write end is closed (the caller closed it, or died, however
        it died), the workload's process group is sent `SIGKILL`. The caller keeps the read end
        too, and may close it once this returns. `None` (the default): the jail lives until it
        ends or is killed, whatever happens to the process that launched it.
        """
        missing = jail.requires - self.capabilities
        if missing:
            raise LaunchRefused(missing, self.name)

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
        # jail. `_identity.UNKNOWN` when the read lost the race with a
        # workload that had already ended, which degrades to the pid-only
        # behaviour that preceded it -- never to a wrong answer.
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

        return Handle(
            jail_id=jail_id,
            jail_dir=jail_dir,
            launcher_name=self.name,
            pid=pid,
            pgid=pgid,
            start_time=start_time,
            argv=wrapped_argv,
            cwd=cwd,
            jail_env=jail.env,
            wrap_prefix=wrap_prefix,
            spec=jail.spec,
            report=jail.report,
            signatures=jail.signatures,
            channels={channel.name: channel for channel in jail.spec.channels},
            compile_events=stamp_all(
                (payload for sensor in jail.sensors for payload in sensor.known_at_compile()),
                jail_id,
            ),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            helper_pids=helper_pids,
            helper_stamps=helper_stamps,
        )
