"""`HostRuntime`'s supervisor against real processes (decision-178, TASK-0079.02).

`Jail` reaches `Supervisor.start`, `Supervisor.signal` and `Supervisor.wait` through
`exec`, `interrupt` and `wait`, which the rest of the suite covers.
`Supervisor.stop`, one process's group alone, has no `Jail` method yet (step 3's
`Process.stop`), so it is driven here directly, and checked with `/bin/ps`,
never through the module under test: the stopped sibling's group is gone, and
in the same jail, the control, the first process and a second sibling still
run.
"""

import itertools
import os
import signal
import subprocess

import pytest

from brig.core import Spec, unenforced_report
from brig.run import IoPolicy, Jail, Process
from brig.run.host import HostSupervisor
from brig.run.teardown import KillOutcome
from brig.stack import CompiledJail
from tests.conftest import launch, teardown_group, workload_argv

_jail_counter = itertools.count()


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _launch(run_id: str) -> tuple[Jail, Process]:
    jail_dir = f"/tmp/bg{os.getpid()}ha{next(_jail_counter)}"
    jail = CompiledJail(
        spec=Spec(),
        report=unenforced_report(),
        wrap=_identity_wrap,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        mechanism_names=(),
        matrix_version=1,
    )
    return launch(
        jail,
        argv=workload_argv(run_id, "sleep 100"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-host-supervisor",
        jail_dir=jail_dir,
    )


def _live_members(pgid: int) -> list[int]:
    """Non-zombie pids in `pgid`, from `/bin/ps` (alias-proof, decision-026)."""
    table = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,pgid=,stat="], capture_output=True, text=True, check=True
    ).stdout
    return [
        int(pid)
        for pid, group, state in (line.split() for line in table.splitlines() if line.strip())
        if int(group) == pgid and not state.startswith("Z")
    ]


@pytest.mark.integration
def test_stop_ends_one_siblings_group_and_leaves_the_rest(run_id: str) -> None:
    jail, process = _launch(run_id)
    record = jail._record()
    supervisor = jail._runtime.supervisor(record)
    assert isinstance(supervisor, HostSupervisor)
    try:
        doomed = supervisor.start(
            workload_argv(run_id, "sleep 100"), cwd=jail._base.cwd, io=IoPolicy()
        )
        kept = supervisor.start(
            workload_argv(run_id, "sleep 100"), cwd=jail._base.cwd, io=IoPolicy()
        )
        assert _live_members(doomed.pgid), "the sibling never ran"

        report = supervisor.stop(doomed)

        assert [(item.kind, item.identity, item.outcome) for item in report.items] == [
            ("exec_sibling", str(doomed.pgid), KillOutcome.ENDED)
        ]
        assert _live_members(doomed.pgid) == []
        assert supervisor.wait(doomed, 5.0) == -signal.SIGTERM
        # The control, in the same jail: what was not stopped still runs.
        assert _live_members(kept.pgid)
        assert _live_members(process._record.pgid)
        assert supervisor.signal(kept, signal.SIGKILL) is True
        assert supervisor.wait(kept, 5.0) == -signal.SIGKILL
        assert supervisor.wait(record.processes[0], 0.1) is None
    finally:
        jail.destroy()
        teardown_group(process)
