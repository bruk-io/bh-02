"""A jail's `JAIL_LIFETIME` helpers end with the process that created it (TASK-0079.29,
decision-199).

SPEC.md section 8. A helper (the egress proxy is one) runs on the host, in a group of its own,
outside the jail's namespaces: so what ends a jail's processes when nobody is left to call
`destroy` (the tether's watcher, decision-167) did not reach it, and a creator that died with
`SIGKILL` left its helpers running, orphaned to PID 1. decision-199: a helper is tethered to
the creator as the jail's processes are.

The claims, each against the empty stack (what is under test is the runtime's plumbing, which
every stack shares), each with its control in the same test:

1. A creator killed with `SIGKILL` takes a tethered jail's helper with it; a second creator
   that lives keeps its own helper (the claim is the creator's death, not a general sweep).
2. Closing the tether without `destroy` ends the helper as it ends the processes.
3. `destroy` of a jail whose helper is running ends it and reports it, and leaves its group
   empty (the pid the jail records is still what ends it).
4. A tether that has already ended refuses the create before any helper starts, where a
   watcher on it would end the helper at once.
5. An untethered, unsupervised jail's helper outlives its creator, as its processes do, and a
   `Jail` rehydrated in another process still ends it by the pid and start stamp it recorded:
   nothing here ties the jail to its creator, and the ruling does not claim to.
"""

from __future__ import annotations

import itertools
import json
import os
import signal
import subprocess
import sys
import time

import pytest

from brig.core import Spec, unenforced_report
from brig.mech import Helper, HelperLifetime
from brig.run import HostRuntime, Jail, RuntimeKind
from brig.run._tether import TetherClosed
from brig.run.teardown import KillOutcome
from brig.stack import CompiledJail
from tests.conftest import launch, workload_argv
from tests.supervised_jail import running_with, unique_sleep

pytestmark = pytest.mark.integration

_jail_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root with this file's own infix (`th`), so no other integration file's
    numbering collides with it (see `test_tether.py`'s `_new_jail_dir`)."""
    return f"/tmp/bg{os.getpid()}th{next(_jail_counter)}"


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail(helper_argv: list[str]) -> CompiledJail:
    return CompiledJail(
        spec=Spec(),
        report=unenforced_report(),
        wrap=_identity_wrap,
        env={},
        staged=(),
        helpers=(
            Helper(name="beacon", argv=tuple(helper_argv), lifetime=HelperLifetime.JAIL_LIFETIME),
        ),
        requires=frozenset(),
        mechanism_names=(),
        matrix_version=1,
    )


def _group_lives(pgid: int) -> bool:
    """Whether a live (not zombie) process is in group `pgid`, read with `/bin/ps` and never
    through the module under test. `killpg(pgid, 0)` would count a killed helper this process
    has not yet reaped, which is gone for every purpose here."""
    table = subprocess.run(
        ["/bin/ps", "-Ao", "pgid=,stat="], capture_output=True, text=True, check=True
    ).stdout
    return any(
        fields[0] == str(pgid) and not fields[1].startswith("Z")
        for fields in (line.split() for line in table.splitlines())
        if len(fields) == 2
    )


def _gone_within(pgid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _group_lives(pgid):
            return True
        time.sleep(0.05)
    return not _group_lives(pgid)


# The creating process: creates a jail with one `JAIL_LIFETIME` helper, tethered or not, prints
# the jail's dict, and waits to be killed. It makes the tether's pipe itself, so the write end is
# held by this process alone: the kernel closes it when the process dies, `SIGKILL` included.
_CREATOR = """
import json, os, sys, time
from brig.core import Spec, unenforced_report
from brig.mech import Helper, HelperLifetime
from brig.run import HostRuntime, Jail
from brig.stack import CompiledJail

jail_dir, tethered, helper_argv = sys.argv[1], sys.argv[2] == "1", sys.argv[3:]
compiled = CompiledJail(
    spec=Spec(), report=unenforced_report(), wrap=lambda argv: argv, env={}, staged=(),
    helpers=(Helper(name="beacon", argv=tuple(helper_argv), lifetime=HelperLifetime.JAIL_LIFETIME),),
    requires=frozenset(), mechanism_names=(), matrix_version=1,
)
read_end, write_end = os.pipe()
jail = Jail.create(
    compiled, runtime=HostRuntime(), cwd=jail_dir, jail_id="creator", jail_dir=jail_dir,
    **({"tether": read_end} if tethered else {}),
)
os.close(read_end)
print(json.dumps(jail.to_dict()), flush=True)
time.sleep(600)
"""


def _creator(run_id: str, *, tethered: bool) -> tuple[subprocess.Popen[str], dict[str, object]]:
    """Start `_CREATOR`; it and the dict of the jail it made, whose helper is running."""
    jail_dir = _new_jail_dir()
    os.makedirs(jail_dir, exist_ok=True)
    creator = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _CREATOR,
            jail_dir,
            "1" if tethered else "0",
            *workload_argv(run_id, "sleep 100"),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert creator.stdout is not None
    made = json.loads(creator.stdout.readline())
    (helper_pgid,) = made["helper_pids"]
    assert _group_lives(helper_pgid)
    return creator, made


def _killed(creator: subprocess.Popen[str]) -> None:
    creator.send_signal(signal.SIGKILL)
    creator.wait(10)


def test_a_tethered_jails_helper_ends_when_its_creator_is_killed(run_id: str) -> None:
    dying, dead = _creator(run_id, tethered=True)
    living, alive = _creator(run_id, tethered=True)
    (dead_pgid,) = dead["helper_pids"]  # type: ignore[misc]
    (alive_pgid,) = alive["helper_pids"]  # type: ignore[misc]
    try:
        _killed(dying)
        assert _gone_within(dead_pgid, 10.0), f"helper {dead_pgid} outlived its SIGKILLed creator"
        # The control: the other creator lives, so its helper does too. It was the creator's
        # death that ended the first, not a sweep of every helper.
        assert _group_lives(alive_pgid)
        _killed(living)
        assert _gone_within(alive_pgid, 10.0)
    finally:
        for creator, pgid in ((dying, dead_pgid), (living, alive_pgid)):
            creator.kill()
            creator.wait(10)
            if _group_lives(pgid):
                os.killpg(pgid, signal.SIGKILL)


def test_closing_the_tether_ends_the_helper_as_it_ends_the_processes(run_id: str) -> None:
    jail_dir = _new_jail_dir()
    read_end, write_end = os.pipe()
    try:
        jail, process = launch(
            _compiled_jail(workload_argv(run_id, "sleep 100")),
            argv=workload_argv(run_id, "sleep 100"),
            cwd=jail_dir,
            jail_id="closing",
            jail_dir=jail_dir,
            tether=read_end,
        )
    finally:
        os.close(read_end)
    (helper_pgid,) = jail.to_dict()["helper_pids"]
    try:
        assert _group_lives(helper_pgid)
        assert _group_lives(process._record.pgid)
        os.close(write_end)
        write_end = -1
        assert _gone_within(process._record.pgid, 10.0), "the tether did not end the process"
        assert _gone_within(helper_pgid, 10.0), f"helper {helper_pgid} outlived the tether"
    finally:
        if write_end != -1:
            os.close(write_end)
        jail.destroy()


def test_destroy_ends_a_tethered_jails_helper_and_leaves_its_group_empty(run_id: str) -> None:
    jail_dir = _new_jail_dir()
    read_end, write_end = os.pipe()
    try:
        jail, _ = launch(
            _compiled_jail(workload_argv(run_id, "sleep 100")),
            argv=workload_argv(run_id, "sleep 100"),
            cwd=jail_dir,
            jail_id="destroyed",
            jail_dir=jail_dir,
            tether=read_end,
        )
    finally:
        os.close(read_end)
    (helper_pgid,) = jail.to_dict()["helper_pids"]
    try:
        assert _group_lives(helper_pgid)  # the control: it ran until `destroy`
        report = jail.destroy()
    finally:
        os.close(write_end)
    (item,) = [item for item in report.items if item.kind == "helper"]
    assert item.identity == str(helper_pgid)
    assert item.outcome is KillOutcome.ENDED, report
    assert not _group_lives(helper_pgid), "the helper's group still has a member after destroy"


def test_a_tether_that_has_ended_refuses_the_create_before_a_helper_starts() -> None:
    marker, sleep = unique_sleep()
    jail_dir = _new_jail_dir()
    read_end, write_end = os.pipe()
    os.close(write_end)  # every write end is closed: the tether has ended
    try:
        with pytest.raises(TetherClosed, match="tether has ended"):
            Jail.create(
                _compiled_jail(sleep),
                runtime=HostRuntime(),
                cwd="/",
                jail_id="ended",
                jail_dir=jail_dir,
                tether=read_end,
            )
        time.sleep(0.5)
        assert running_with(marker) == []
    finally:
        os.close(read_end)
        for pid in running_with(marker):
            os.kill(pid, signal.SIGKILL)


def test_an_untethered_jails_helper_outlives_its_creator_and_a_rehydrated_jail_ends_it(
    run_id: str,
) -> None:
    """The boundary the ruling states: nothing ties an untethered, unsupervised jail's processes
    to its creator, and so nothing ties its helpers. Whoever holds its dict ends it."""
    creator, made = _creator(run_id, tethered=False)
    (helper_pgid,) = made["helper_pids"]  # type: ignore[misc]
    try:
        _killed(creator)
        time.sleep(1.0)
        assert _group_lives(helper_pgid)
        rehydrated = Jail.from_dict(made, runtimes={RuntimeKind.HOST: HostRuntime()})
        report = rehydrated.destroy()
        (item,) = [item for item in report.items if item.kind == "helper"]
        assert item.outcome is KillOutcome.ENDED, report
        assert _gone_within(helper_pgid, 10.0)
    finally:
        creator.kill()
        creator.wait(10)
        if _group_lives(helper_pgid):
            os.killpg(helper_pgid, signal.SIGKILL)
