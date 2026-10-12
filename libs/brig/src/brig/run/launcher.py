"""`SubprocessLauncher`: detached, new-process-group, stdio-to-files.

SPEC.md §8:

    class Launcher(Protocol):
        name: str
        capabilities: frozenset[Capability]
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

**The launch itself is `HostRuntime.create` (decision-178, 2026-10-12).**
SPEC.md section 3 names the runtime in place of the launcher: staging, the
helpers, the exit wrapper, the tether, start-time stamps and the exit waiter
moved, unchanged, to `brig/run/host.py`, whose docstring carries this
module's notes on them. What is left here is SPEC.md section 8's door: the
capability refusal, `HostRuntime().create`, sensor stamping, and the `Handle`
the embedder holds, which keeps that runtime. `IoPolicy` lives in
`brig/run/runtime.py`, and `LaunchRefused` and `HelperFailed` in
`brig/run/host.py`; each is re-exported here, so every import of them from
this module resolves (`_derive_wrap_prefix` and `_start_helpers`, private,
are imported from `host` now).

**Sensors (decision-152, 2026-09-08).** SPEC.md §6 says "`run` is the only
layer permitted to write" a mechanism sensor's payloads. This launcher stamps
every sensor's `known_at_compile()` payloads with `ts` and this jail's
`jail_id` (`brig/run/events.py`) and puts the result on
`Handle.compile_events`; `HostRuntime.create` hands the same sensors to the
exit waiter, which stamps `classify_exit()`'s answer when the workload ends
(`Handle.exit_events()`). Neither is written anywhere.
"""

from collections.abc import Sequence

from brig.core.runtime import Capability
from brig.run.events import stamp_all
from brig.run.handle import Handle
from brig.run.host import HelperFailed as HelperFailed
from brig.run.host import HostRuntime
from brig.run.host import LaunchRefused as LaunchRefused
from brig.run.runtime import IoPolicy as IoPolicy
from brig.stack import CompiledJail


class SubprocessLauncher:
    """SPEC.md §8's `subprocess` launcher: pipes or files for stdio,
    detached, new process group. M2 ships the files half; pipes arrive
    with a future milestone if a caller ever needs streamed stdio without a
    pty."""

    name = "subprocess"
    capabilities: frozenset[Capability] = frozenset(
        {Capability.NEW_PROCESS_GROUP, Capability.DETACH}
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
        2-3. `HostRuntime().create` (decision-178): create `jail_dir`,
           clear any exit record an earlier launch left in it
           (decision-162), write `jail.staged` into it, and spawn
           `jail.wrap(argv)`, detached, new process group, stdio per `io`,
           cwd and env from the jail.
        4. Stamp every sensor's `known_at_compile()` payloads.
        5. Return a `Handle` carrying them, and the runtime it delegates to.

        `tether` (decision-167, SPEC.md section 8) is the read end of a pipe whose write end
        the caller keeps: once every write end is closed (the caller closed it, or died, however
        it died), the workload's process group is sent `SIGKILL`. The caller keeps the read end
        too, and may close it once this returns. `None` (the default): the jail lives until it
        ends or is killed, whatever happens to the process that launched it.
        """
        missing = jail.requires - self.capabilities
        if missing:
            raise LaunchRefused(missing, self.name)

        runtime = HostRuntime()
        record = runtime.create(
            jail,
            argv=argv,
            cwd=cwd,
            io=io,
            jail_id=jail_id,
            jail_dir=jail_dir,
            tether=tether,
        )
        return Handle(
            jail_id=jail_id,
            jail_dir=jail_dir,
            launcher_name=self.name,
            pid=record.first.pid,
            pgid=record.first.pgid,
            start_time=record.first.start_time,
            argv=record.first.argv,
            cwd=cwd,
            jail_env=jail.env,
            wrap_prefix=record.wrap_prefix,
            spec=jail.spec,
            report=jail.report,
            signatures=jail.signatures,
            channels={channel.name: channel for channel in jail.spec.channels},
            compile_events=stamp_all(
                (payload for sensor in jail.sensors for payload in sensor.known_at_compile()),
                jail_id,
            ),
            stdout_path=record.first.stdout_path,
            stderr_path=record.first.stderr_path,
            helper_pids=record.helper_pids,
            helper_stamps=record.helper_stamps,
            runtime=runtime,
        )
