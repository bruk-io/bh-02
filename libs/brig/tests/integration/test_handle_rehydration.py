"""`Handle` rehydrated from `to_dict()` in a genuinely SEPARATE interpreter
kills the workload the original launched (task-023).

MILESTONES.md M2 exit criterion 1, verbatim -- this file IS that criterion:

    Launch `python -c` workload; handle round-trips through
    `to_dict`/`from_dict` in a *separate process* and `kill()` from the
    rehydrated handle ends it.

SPEC.md §9, the failure class this exists to close:

    The handle is the fix for two documented failure classes in prior art:
    kill paths that lose a container's identity when a relay pid dies
    (identity lives in the serialized handle, not in a live process's
    argv) ...

`.claude/rules/system-tests.md` names "handle rehydration in a genuinely
separate process, then teardown" as a cross-cutting invariant of the system
tier; M2 has no presets and no probe engine, so it lands here at the
integration tier as the seam test it is (handle -> teardown, exactly the
seam `.claude/rules/integration-tests.md` scopes a test to).

Routing test rule 2, decisively: "the workload is gone after the helper ran"
is also true if the workload simply exited on its own, or if the helper's
own process-exit reaped it -- worthless without a control that isolates the
rehydrated `kill()` as the cause. THE CONTROL below supplies that: the same
helper, rehydrating the same way, reporting `alive=True`, but never calling
`kill()` -- the tree is still alive afterward.

The actual cross-process boundary is `tests/integration/
_rehydrate_and_kill_helper.py`, run via `subprocess.run([sys.executable,
_HELPER, json_path, ...])` -- a genuinely separate interpreter, not
`Handle.from_dict(handle.to_dict())` called in-process (that in-process
round trip is `test_launcher.py`'s AC #8, explicitly out of scope here; see
that test's docstring: "the separate-process proof is task-023's, not
claimed here").

**The serialized dict is the helper's SOLE input** (task's Deliverable,
verbatim): no pid on the command line, no environment carrying the pgid, no
shared object -- `_HELPER`'s argv for THE CLAIM below is exactly
`[sys.executable, _HELPER, json_path]`, nothing else. THE CONTROL's argv
adds one further token, `--no-kill` -- a behavior-mode switch, not identity
data (see `_rehydrate_and_kill_helper.py`'s own docstring); no pid or pgid
ever reaches the helper by any route other than the JSON file, in EITHER
invocation.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

import pytest

from brig.core import Channel, ChannelKind, EnforcementReport, Spec, unenforced_report
from brig.run.handle import HANDLE_VERSION, Handle
from brig.run.launcher import IoPolicy, SubprocessLauncher
from brig.stack import CompiledJail
from tests.conftest import workload_argv

_HELPER = str(pathlib.Path(__file__).parent / "_rehydrate_and_kill_helper.py")
_HELPER_TIMEOUT_S = 30.0

_jail_counter = itertools.count()


def _new_jail_dir() -> str:
    """A short scratch root, `/tmp/bg<pid>rh<n>` -- never `tmp_path`
    (CLAUDE.md: `sun_path` is 104 bytes on darwin). The `rh` (rehydration)
    infix keeps this file's jail-dir sequence out of the shared,
    order-dependent `/tmp/bg<pid>-<n>` namespace `test_kill_group.py`'s
    docstring documents colliding across integration files that share one
    pytest process."""
    return f"/tmp/bg{os.getpid()}rh{next(_jail_counter)}"


def _identity_wrap(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


def _compiled_jail(
    *, spec: Spec | None = None, report: EnforcementReport | None = None
) -> CompiledJail:
    """The empty stack's shape (SPEC.md §3) by default -- mechanism-free,
    every axis unenforced, no requires -- overridable via `spec`/`report`
    for the non-vacuity closer below (mirrors `test_launcher.py`'s
    `_compiled_jail`, same reason: an empty-stack `Spec` has no channels
    and `unenforced_report()`'s `detail` is `""` on every axis, which would
    make a dict-equality round-trip check pass even if `channels`/`detail`
    decoding were broken)."""
    return CompiledJail(
        spec=spec if spec is not None else Spec(),
        report=report if report is not None else unenforced_report(),
        wrap=_identity_wrap,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        mechanism_names=(),
        matrix_version=1,
    )


def _launch(
    argv: list[str],
    *,
    jail_id: str = "jail-rehydration",
    spec: Spec | None = None,
    report: EnforcementReport | None = None,
) -> Handle:
    jail_dir = _new_jail_dir()
    launcher = SubprocessLauncher()
    return launcher.launch(
        _compiled_jail(spec=spec, report=report),
        argv=argv,
        cwd=jail_dir,
        io=IoPolicy(),
        jail_id=jail_id,
        jail_dir=jail_dir,
    )


def _ps_rows() -> list[tuple[int, int, int]]:
    """(pid, ppid, pgid) for every process visible right now (alias-proof
    `/bin/ps`, decision-026 -- never a bare `ps`)."""
    proc = subprocess.run(
        ["/bin/ps", "-Ao", "pid=,ppid=,pgid="],
        capture_output=True,
        text=True,
        check=True,
    )
    rows: list[tuple[int, int, int]] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return rows


def _ps_has_row_for(pid: int) -> bool:
    proc = subprocess.run(["/bin/ps", "-p", str(pid)], capture_output=True, text=True)
    data_lines = [line for line in proc.stdout.strip().splitlines()[1:] if line.strip()]
    return proc.returncode == 0 and bool(data_lines)


def _positive_pre_assertion(handle: Handle) -> tuple[int, int, int]:
    """Before any rehydration/kill: prove the tree is real -- a second pid
    exists beyond the workload leader, it differs from the leader pid, and
    both report the same pgid. Returns (leader_pid, child_pid, pgid),
    captured BEFORE the helper ever runs (AC #5: "both captured before the
    helper ran")."""
    rows = _ps_rows()
    children = [pid for pid, ppid, _pgid in rows if ppid == handle.pid]
    assert children, (
        f"expected the workload leader (pid={handle.pid}) to have a live "
        f"child before rehydration; full ps rows: {rows}"
    )
    child_pid = children[0]
    assert child_pid != handle.pid

    leader_rows = [r for r in rows if r[0] == handle.pid]
    child_rows = [r for r in rows if r[0] == child_pid]
    assert leader_rows and child_rows
    leader_pgid = leader_rows[0][2]
    child_pgid = child_rows[0][2]
    assert leader_pgid == child_pgid
    assert leader_pgid == handle.pgid

    print(
        f"PRE-ASSERTION: leader_pid={handle.pid} child_pid={child_pid} "
        f"pgid={leader_pgid} (handle.pgid={handle.pgid})"
    )
    return handle.pid, child_pid, leader_pgid


def _run_helper(json_path: str, *extra_args: str) -> dict[str, object]:
    """Run `_HELPER` as a genuinely separate interpreter (`sys.executable`,
    not this process), and parse its single JSON line of stdout."""
    argv = [sys.executable, _HELPER, json_path, *extra_args]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=_HELPER_TIMEOUT_S,
    )
    print(f"HELPER ARGV: {argv}")
    print(f"HELPER stdout: {proc.stdout!r}")
    print(f"HELPER stderr: {proc.stderr!r}")
    assert proc.returncode == 0, (
        f"helper {argv} exited {proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, f"helper {argv} printed no output"
    return dict(json.loads(lines[-1]))


# ---------------------------------------------------------------------------
# AC #2 / #3 / #4 / #5 / #7 -- THE CLAIM: rehydrated kill() ends the tree.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_rehydrated_handle_in_a_separate_process_kills_the_workload_tree(run_id: str) -> None:
    """AC #2, #3, #4, #5, #7 -- the exit criterion, literally.

    A marked, child-spawning workload (`bash -c 'sleep 100 & wait'`-shaped,
    via task-013's `workload_argv`) is launched in THIS process. Its
    handle's `to_dict()` is written to a JSON file under the scratch root
    -- the only thing that crosses the process boundary. A genuinely
    separate interpreter (`sys.executable`, AC #2) reads that file,
    rehydrates via `Handle.from_dict`, and calls `kill()`. Back here: every
    pid captured before the helper ran is gone (AC #5), the rehydrated
    handle's own `to_dict()` matches the original exactly (AC #4), and the
    parsed `KillReport` names the original pgid and `ENDED` (AC #7)."""
    argv = workload_argv(run_id, "sleep 100")
    handle = _launch(argv)
    leader_pid, child_pid, pgid = _positive_pre_assertion(handle)

    original_dict = handle.to_dict()
    json_path = os.path.join(handle.jail_dir, "handle.json")
    with open(json_path, "w") as f:
        json.dump(original_dict, f)

    # AC #3: the helper's argv carries only the JSON path -- no pid, no
    # pgid, nothing else. `_run_helper` with no `extra_args` is exactly
    # `[sys.executable, _HELPER, json_path]`.
    result = _run_helper(json_path)

    # AC #2: a genuinely separate process -- its own pid differs from this
    # test process's, and it was launched via `sys.executable`, not an
    # in-process `Handle.from_dict(handle.to_dict())` call. No in-process
    # from_dict is being passed off as the rehydration anywhere in this
    # test: `Handle.from_dict` is imported here only for type context on
    # `Handle`, and is never called by this process.
    helper_pid = result["pid"]
    assert isinstance(helper_pid, int)
    assert helper_pid != os.getpid(), (
        "helper pid must differ from the test process's own pid -- "
        "otherwise this is not a separate-process rehydration"
    )
    print(f"CLAIM: test pid={os.getpid()} helper pid={helper_pid}")

    # AC #4: full dict equality, not key-subset -- the rehydrated handle's
    # own to_dict(), produced entirely inside the separate process, matches
    # the dict written to disk before the process boundary was crossed.
    assert result["to_dict"] == original_dict

    # AC #5, THE CLAIM: every pid captured in the pre-assertion -- leader
    # and child both -- is gone after the helper exits.
    for pid in (leader_pid, child_pid):
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        assert not _ps_has_row_for(pid), f"pid {pid} still has a /bin/ps -p row after kill()"

    # AC #7: the rehydrated KillReport is real -- asserted on the parsed
    # JSON's structured fields, not on the presence of the word "ended".
    kill_report = result["kill_report"]
    assert isinstance(kill_report, dict)
    items = kill_report["items"]
    assert isinstance(items, list)
    workload_items = [item for item in items if item["kind"] == "workload_group"]
    assert len(workload_items) == 1
    item = workload_items[0]
    assert item["identity"] == str(pgid)
    assert item["identity"] == str(handle.pgid)
    assert item["outcome"] == "ENDED"
    print(f"KillReport (AC #7): {kill_report}")


# ---------------------------------------------------------------------------
# AC #6 -- THE CONTROL: rehydrate + report alive, but do NOT kill.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_control_rehydrated_handle_without_kill_leaves_the_tree_alive(run_id: str) -> None:
    """AC #6, THE CONTROL. A second run of the SAME helper
    (`_rehydrate_and_kill_helper.py`), in `--no-kill` mode: it rehydrates
    the handle and reports `alive()`, but never calls `kill()`. The
    workload tree is still alive after the helper exits -- this is what
    attributes THE CLAIM's tree death to the rehydrated `kill()` call
    itself, rather than to the helper process merely running and exiting,
    or to elapsed wall-clock time. Cleanup is via `os.killpg` (test-local,
    deliberate) so this file's own control leak does not trip the suite's
    leak-check."""
    argv = workload_argv(run_id, "sleep 100")
    handle = _launch(argv, jail_id="jail-rehydration-control")
    leader_pid, child_pid, pgid = _positive_pre_assertion(handle)

    original_dict = handle.to_dict()
    json_path = os.path.join(handle.jail_dir, "handle.json")
    with open(json_path, "w") as f:
        json.dump(original_dict, f)

    try:
        # Same helper, `--no-kill` mode: rehydrate + report alive(), never
        # call kill(). Still a genuinely separate process (sys.executable).
        result = _run_helper(json_path, "--no-kill")

        helper_pid = result["pid"]
        assert isinstance(helper_pid, int)
        assert helper_pid != os.getpid()
        assert result["alive"] is True
        assert result["to_dict"] == original_dict

        # THE CONTROL's assertion: both pids are still genuinely alive
        # (not merely zombie entries) after the helper -- that never called
        # kill() -- has already exited.
        for pid in (leader_pid, child_pid):
            os.kill(pid, 0)  # does not raise -- still alive
        deadline = time.monotonic() + 2.0
        state = ""
        while time.monotonic() < deadline:
            proc = subprocess.run(
                ["/bin/ps", "-o", "state=", "-p", str(child_pid)],
                capture_output=True,
                text=True,
            )
            state = proc.stdout.strip()
            if state:
                break
            time.sleep(0.02)
        print(f"CONTROL: child_pid={child_pid} state after no-kill helper: {state!r}")
        assert state, f"expected child pid {child_pid} to still be present in /bin/ps"
        assert not state.startswith("Z"), f"child pid {child_pid} is a zombie: {state!r}"
    finally:
        # Clean up what THE CONTROL deliberately leaves alive -- via the
        # group, never leaving a leaked child for the suite's leak-check to
        # catch as an actual bug.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL)
        handle.wait(timeout=20.0)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and _ps_has_row_for(child_pid):
            time.sleep(0.02)


# ---------------------------------------------------------------------------
# AC #4 non-vacuity closer -- a channel and a non-empty detail actually
# survive the cross-process round trip, not just `{} == {}` / `"" == ""`.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_rehydrated_round_trip_carries_a_channel_and_a_non_empty_detail(run_id: str) -> None:
    """Non-vacuity closer for AC #4, same reasoning as
    `test_launcher.py`'s own `test_launch_writes_staged_files_and_
    handle_round_trips_channels_and_detail`: every other test in THIS file
    uses the empty-stack defaults (`Spec()` / `unenforced_report()`), whose
    `channels` serializes to `[]` and whose every axis `detail` is `""` --
    a `from_dict` that silently dropped `channels` entirely, or dropped
    every `detail` string, would STILL produce a dict equal to the
    original there, so AC #4's dict-equality assertion never actually
    exercises `Channel`/`ChannelKind` decoding or a non-empty `detail`
    across the process boundary. This test gives the jail one real channel
    and a named `detail`, runs the SAME cross-process helper (`--no-kill`
    mode -- this test is about serialization fidelity, not teardown, so it
    reuses THE CONTROL's mode rather than tearing the workload down), and
    asserts full dict equality on a dict that is not vacuously equal to
    itself by construction."""
    channel = Channel(name="ctl", kind=ChannelKind.LISTEN, endpoint="ctl.sock")
    spec = Spec(channels=(channel,))
    report = unenforced_report("m2: no mechanisms enforce anything yet")

    argv = workload_argv(run_id, "sleep 100")
    handle = _launch(argv, jail_id="jail-rehydration-nonvacuous", spec=spec, report=report)
    _leader_pid, child_pid, pgid = _positive_pre_assertion(handle)

    # The channel and the non-empty detail are on the live handle before
    # any serialization -- so a later equality failure can be pinned to
    # the round trip specifically, not to construction.
    assert handle.channels["ctl"] == channel
    assert all(
        graded.detail == "m2: no mechanisms enforce anything yet"
        for graded in handle.report.axes.values()
    )

    original_dict = handle.to_dict()
    assert original_dict["channels"] != []
    assert original_dict["report"]["fs_read"]["detail"] == "m2: no mechanisms enforce anything yet"
    json_path = os.path.join(handle.jail_dir, "handle.json")
    with open(json_path, "w") as f:
        json.dump(original_dict, f)

    try:
        result = _run_helper(json_path, "--no-kill")
        assert result["pid"] != os.getpid()
        assert result["alive"] is True

        # AC #4, made non-vacuous: full dict equality on a dict that
        # actually carries a channel and a non-empty detail.
        assert result["to_dict"] == original_dict
        rehydrated_channels = result["to_dict"]["channels"]
        assert rehydrated_channels == [{"name": "ctl", "kind": "listen", "endpoint": "ctl.sock"}]
        rehydrated_report = result["to_dict"]["report"]
        assert rehydrated_report["fs_read"]["detail"] == "m2: no mechanisms enforce anything yet"
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL)
        handle.wait(timeout=20.0)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and _ps_has_row_for(child_pid):
            time.sleep(0.02)


# ---------------------------------------------------------------------------
# AC #6 (task-046) -- a version-1 dict refuses, naming both the rejected
# version and the current one, with a control proving the refusal is about
# the VERSION.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_handle_from_dict_refuses_version_one(run_id: str) -> None:
    """AC #6 (task-046). A dict claiming `version: 1` -- otherwise a
    genuine, freshly-serialized handle dict, with only the version field
    rolled back -- refuses, its message naming BOTH the rejected version
    (1) and the current one, never only one of the two (SPEC.md §5's
    posture, applied to `Handle`: "There is no migration framework and no
    tolerated extra field").

    THE CONTROL, in the same test: the UNMODIFIED current-version dict
    rehydrates fine,
    and the rehydrated handle's `wrap_prefix` equals the live handle's --
    proving the refusal above is about the version field specifically, not
    `from_dict` being broken outright (which would make "refuses on
    version 1" vacuous -- true of every input, not just a stale version).
    """
    argv = workload_argv(run_id, "sleep 5")
    handle = _launch(argv, jail_id="jail-rehydration-version")
    try:
        d = handle.to_dict()
        assert d["version"] == HANDLE_VERSION == 5

        stale = dict(d)
        stale["version"] = 1
        with pytest.raises(ValueError) as exc_info:
            Handle.from_dict(stale)
        message = str(exc_info.value)
        assert "unsupported version 1" in message, (
            f"refusal message does not name the rejected version 1: {message!r}"
        )
        assert f"expected {HANDLE_VERSION}" in message, (
            f"refusal message does not name the expected version {HANDLE_VERSION}: {message!r}"
        )

        # THE CONTROL: same dict, version untouched -- rehydrates cleanly,
        # and its wrap_prefix (task-046's own new field) survives the
        # round trip intact.
        rehydrated = Handle.from_dict(d)
        assert rehydrated == handle
        assert rehydrated.wrap_prefix == handle.wrap_prefix
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(handle.pgid, signal.SIGKILL)
        handle.wait(timeout=20.0)
