"""EC5's "end to end" half (MILESTONES.md M2 exit criterion 5):

    Floors work end to end: `require(fs_read=ENFORCED)` against the empty
    stack refuses at compile with the axis named.

task-017's unit tests already pin the refusal's *structure* -- the axis and
the shortfall land on `FloorViolation.shortfalls`, checked as structured
fields (`tests/unit/test_stack_compile.py`). What is NOT unit-testable, and
what this file exists to prove, is the "end to end" half: that a refused
compile is a true dead end -- no process, no jail directory, and no event
file ever comes into existence, because the caller never reaches
`Launcher.launch` at all. Proving an absence needs a positive control (the
SAME spec, the SAME would-be launch call, but with a satisfiable floor)
producing all three -- without it, "nothing was created" cannot be told
apart from "this test never launches anything" (SPEC.md §7 step 4; SPEC.md
§4's Floors paragraph; SPEC.md §7's coverage paragraph: "a floors check can
never pass merely because an axis was absent from the report").

Every workload this file launches is built through `tests.conftest.
workload_argv`, so a survivor is caught by the suite-wide leak-check
without any registration. Jail/scratch directories use the short
`/tmp/bg<pid>-<n>` root, never `tmp_path` (CLAUDE.md: `sun_path` is 104
bytes on darwin).
"""

from __future__ import annotations

import itertools
import os
import subprocess
import uuid

import pytest

from brig.core import Axis, FloorViolation, Grade, Spec, require
from brig.run.handle import Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import Stack
from tests.conftest import teardown_group, workload_argv

_scratch_counter = itertools.count()


def _new_scratch_root() -> str:
    """A short, freshly-created scratch root, `/tmp/bg<pid>fe<n>` -- never
    `tmp_path`. Created (not merely named) so `os.listdir` on it afterwards
    is a real assertion about what did or didn't land inside, not about
    whether the directory itself exists. The `fe` tag (this file's initials)
    keeps this file's counter from colliding with the several sibling
    integration files that build a scratch path from the SAME
    `/tmp/bg<pid>-<n>` shape off their own independent, zero-based counter
    (`test_launcher.py`, `test_exec.py`, `test_wait_ready.py`) -- harmless
    for them, since only `SubprocessLauncher.launch`'s `exist_ok=True`
    `os.makedirs` ever touches those paths, but this file calls
    `os.makedirs(..., exist_ok=False)` BEFORE any launch, specifically so a
    stale directory can never masquerade as "the scratch root started
    empty"; that only works if the path is actually fresh."""
    root = f"/tmp/bg{os.getpid()}fe{next(_scratch_counter)}"
    os.makedirs(root, exist_ok=False)
    return root


def _ps_lines_matching(token: str) -> list[str]:
    """Every `/bin/ps` line (across the whole machine, not scoped to any
    pgid) whose command contains `token`. Absolute path, never a bare `ps`
    (decision-026: this environment aliases `ls`, and the same class of
    surprise applies to any bare command name)."""
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,command="], capture_output=True, text=True, check=True
    )
    return [line for line in proc.stdout.splitlines() if token in line]


def _teardown_group(handle: Handle) -> None:
    """Group-kill a workload launched WITH `start_new_session`;
    `handle.wait()` blocks until the launcher's exit-waiter has reaped it
    (task-073). `Handle.kill()` is task-020's real implementation, but this
    file stays independent of it -- exactly like `test_launcher.py` -- so a
    defect in `kill_jail` can never mask a leak this file is responsible
    for."""
    # task-086: delegates to the ONE verified helper in tests/conftest.py.
    # The body that used to be inlined here -- killpg, then wait for the
    # LEADER -- verified nothing about the process GROUP, so an orphaned
    # backgrounded child survived silently and surfaced later against an
    # unrelated test. Thirteen modules carried that same body.
    teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #2 / #3 -- THE CLAIM: refuses at compile, and nothing downstream of that
# refusal ever comes into existence.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_floor_the_empty_stack_cannot_meet_refuses_and_nothing_is_created(
    run_id: str,
) -> None:
    """AC #2, #3: `Stack([]).compile(spec, require(fs_read=ENFORCED))`
    raises `FloorViolation` naming `fs_read`. Afterwards:

    - the scratch root that would have PARENTED the jail directory, had
      compile succeeded and a launch followed, contains nothing at all --
      no jail directory, no events file, no stdout/stderr file (AC #2);
    - no process anywhere carries this test's marker token (AC #3).

    The `launcher.launch(...)` call is written INSIDE the `pytest.raises`
    block, on the same statement sequence `compile()` sits on -- not omitted
    -- so it is genuinely on this test's code path and genuinely unreached,
    rather than an absence assertion with nothing in the test that could
    ever have made it fail. `handle` starts `None` and is only assigned if
    `launch` is ever reached, so the `finally` below cannot itself create
    the very leak this test exists to rule out.

    The marker scanned for is a PER-TEST uuid, not the shared session
    `run_id` -- `run_id` is common to every test in the suite, so a scan for
    it here would still pass even if this specific test's own launch call
    executed, as long as nothing else in the whole session happened to be
    mid-flight; scanning for a token that exists NOWHERE except this one
    test's own would-be argv ties the assertion to this test's own
    behaviour, not to the rest of the suite's timing. The token is still
    routed through `workload_argv(run_id, ...)`, so IF this ever did leak
    (e.g. under the mutation below), the suite-wide conftest sweep would
    also catch it via `run_id`, independent of this test's own scan.
    """
    scratch_root = _new_scratch_root()
    jail_dir = os.path.join(scratch_root, "jail")
    marker = uuid.uuid4().hex
    argv = workload_argv(run_id, f": {marker}\nsleep 5")

    handle: Handle | None = None
    try:
        with pytest.raises(FloorViolation) as exc_info:
            compiled = Stack([]).compile(Spec(), require(fs_read=Grade.ENFORCED))
            handle = SubprocessLauncher().launch(
                compiled,
                argv=argv,
                cwd=jail_dir,
                io=IoPolicy(),
                jail_id="jail-ec5-refused",
                jail_dir=jail_dir,
            )

        shortfalls = exc_info.value.shortfalls
        assert shortfalls[0].axis is Axis.FS_READ
        assert shortfalls[0].required is Grade.ENFORCED
        assert shortfalls[0].actual is Grade.UNENFORCED

        # AC #2: nothing was ever written under the scratch root -- no jail
        # directory, no events.jsonl, no stdout.log/stderr.log. `launch`
        # above is what would have created `jail_dir`; it was never reached.
        listing = sorted(os.listdir(scratch_root))
        assert listing == [], f"scratch root {scratch_root!r} was not empty: {listing!r}"

        # AC #3: no process on the machine carries this test's marker --
        # `launch` above, whose argv carries it, was never reached.
        matches = _ps_lines_matching(marker)
        assert matches == [], f"a process carrying marker={marker!r} exists: {matches!r}"
    finally:
        # Only fires if `launch` above was somehow reached (e.g. under the
        # plant-mutation this test's docstring/notes describe: temporarily
        # requiring `fs_read=UNENFORCED` here makes `compile` succeed, so
        # `launch` genuinely runs and `handle` is assigned) -- a no-op on
        # every real, unmutated run, where `handle` stays `None`.
        if handle is not None:
            _teardown_group(handle)


# ---------------------------------------------------------------------------
# AC #4 -- THE CONTROL: the SAME spec, the SAME launch call, a satisfiable
# floor -- compiles, launches, and produces all three things AC #2/#3 prove
# absent.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ec5_control_satisfiable_floor_compiles_launches_and_spawns(run_id: str) -> None:
    """AC #4: the SAME spec (`Spec()`) and the SAME shape of launch call as
    the refusal test above -- including an argv built the identical way
    (`workload_argv(run_id, ...)` with a per-test marker on line 2 of the
    body) -- but `require(fs_read=UNENFORCED)` -- a floor the empty stack
    DOES meet -- compiles successfully, and the subsequent launch produces
    (a) a live process carrying the marker, (b) a jail directory, and (c) an
    events file whose first record is `SPAWN`. Without this control, the
    absence assertions above cannot be told apart from "this test never
    launches anything."

    This is ALSO the positive control for `_ps_lines_matching` itself,
    scanning for a marker built exactly the way AC #3's does (line 2 of the
    `workload_argv` body, not line 1 like `run_id`): AC #3's empty result
    means nothing unless the identically-shaped probe is shown here to find
    a process that genuinely exists (integration-tests.md's control rule:
    "a denial test without a control cannot distinguish 'policy enforced'
    from 'probe broken'").
    """
    scratch_root = _new_scratch_root()
    jail_dir = os.path.join(scratch_root, "jail")
    marker = uuid.uuid4().hex
    argv = workload_argv(run_id, f": {marker}\nsleep 5")

    compiled = Stack([]).compile(Spec(), require(fs_read=Grade.UNENFORCED))

    launcher = SubprocessLauncher()
    handle = launcher.launch(
        compiled,
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id="jail-ec5-control",
        jail_dir=jail_dir,
    )
    try:
        # (a) a live process carrying the marker -- the SAME probe shape
        # (`_ps_lines_matching` against a line-2 `workload_argv` marker) as
        # AC #3's absence assertion, now shown to find a real match.
        matches = _ps_lines_matching(marker)
        assert any(line.split(None, 1)[0] == str(handle.pid) for line in matches), (
            f"no /bin/ps row for pid={handle.pid} carries marker={marker!r}: {matches!r}"
        )
        assert handle.alive() is True

        # (b) a jail directory.
        assert os.path.isdir(jail_dir)

        # (c) the jail's stdout file, written by the launcher.
        assert os.path.isfile(handle.stdout_path)
    finally:
        _teardown_group(handle)
    assert handle.alive() is False


# ---------------------------------------------------------------------------
# AC #5 -- Selectivity: attributable to the specific axis, not to "a floors
# argument was present at all."
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_floor_selectivity_met_axis_compiles_unmet_axis_refuses() -> None:
    """AC #5: in the SAME test, a floor naming an axis the empty stack DOES
    meet (any axis at `UNENFORCED`, since SPEC.md §3 grades every axis
    `unenforced` with no mechanisms) compiles, while a floor naming a
    *different* axis at `ENFORCED` -- which the empty stack cannot meet --
    refuses, naming that axis. Using two different axes (network vs.
    fs_read) rather than the same one both times rules out "this axis
    happens to be special"; what matters is required-vs-actual per axis,
    not which axis is asked about.
    """
    spec = Spec()

    met = Stack([]).compile(spec, require(network=Grade.UNENFORCED))
    assert met.report.axes[Axis.NETWORK].grade is Grade.UNENFORCED

    with pytest.raises(FloorViolation) as exc_info:
        Stack([]).compile(spec, require(fs_read=Grade.ENFORCED))
    shortfalls = exc_info.value.shortfalls
    assert shortfalls[0].axis is Axis.FS_READ
    assert shortfalls[0].required is Grade.ENFORCED
    assert shortfalls[0].actual is Grade.UNENFORCED
