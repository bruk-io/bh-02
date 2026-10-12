"""`HostRuntime`'s agent against real processes (decision-178, TASK-0079.02).

`Handle` reaches `Agent.start`, `Agent.signal` and `Agent.wait` through
`exec`, `interrupt` and `wait`, which the rest of the suite covers.
`Agent.stop`, one process's group alone, has no `Handle` method yet (step 3's
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
from brig.run.handle import Handle
from brig.run.host import HostAgent
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.run.teardown import KillOutcome
from brig.stack import CompiledJail
from tests.conftest import teardown_group, workload_argv

_jail_counter = itertools.count()


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _launch(run_id: str) -> Handle:
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
    return SubprocessLauncher().launch(
        jail,
        argv=workload_argv(run_id, "sleep 100"),
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-host-agent",
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
    handle = _launch(run_id)
    record = handle.record()
    agent = handle.runtime.agent(record)
    assert isinstance(agent, HostAgent)
    try:
        doomed = agent.start(workload_argv(run_id, "sleep 100"), cwd=handle.cwd, io=IoPolicy())
        kept = agent.start(workload_argv(run_id, "sleep 100"), cwd=handle.cwd, io=IoPolicy())
        assert _live_members(doomed.pgid), "the sibling never ran"

        report = agent.stop(doomed)

        assert [(item.kind, item.identity, item.outcome) for item in report.items] == [
            ("exec_sibling", str(doomed.pgid), KillOutcome.ENDED)
        ]
        assert _live_members(doomed.pgid) == []
        assert agent.wait(doomed, 5.0) == -signal.SIGTERM
        # The control, in the same jail: what was not stopped still runs.
        assert _live_members(kept.pgid)
        assert _live_members(handle.pgid)
        assert agent.signal(kept, signal.SIGKILL) is True
        assert agent.wait(kept, 5.0) == -signal.SIGKILL
        assert agent.wait(record.first, 0.1) is None
    finally:
        handle.kill()
        teardown_group(handle)
