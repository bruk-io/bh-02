"""`Jail` and `Process` driven through `brig.runtime.fake` (decision-181, TASK-0079.26).

Nothing is spawned, signalled or read: each answer comes from the fake, and
its log says what it was asked. The claims:

- a launch is `Jail.create` then `jail.start`, an exec sibling a second
  `start` (AC1);
- `to_dict` round-trips through `from_dict(runtimes=...)`, which takes the
  runtime from the embedder and refuses a kind it did not pass, naming it: a
  `FAKE` jail rehydrated with only `HostRuntime` passed is refused (AC3, AC6);
- `start` and `probe` are absent, not raising, on a jail whose runtime has no
  supervisor and on one created tethered in another process, and a process of
  a jail with no supervisor has no `interrupt`, `stop` or `wait` (AC3, AC7).
"""

import json

import pytest

from brig.core import Spec, unenforced_report
from brig.core.runtime import RuntimeKind, Scope
from brig.run import ExecFidelity, HostRuntime, Jail, KillOutcome, Process
from brig.run.jail import JAIL_VERSION
from brig.runtime.fake import FakeRuntime
from brig.stack import CompiledJail, Stack

pytestmark = pytest.mark.unit

_JAIL_DIR = "/nonexistent/brig-fake-jail"

#: A tether as the fake sees one: it ignores the fd, so none is opened.
_A_TETHER = 1_000_000


def _create(runtime: FakeRuntime, *, tether: int | None = None) -> Jail:
    return Jail.create(
        Stack([]).compile(Spec()),
        runtime=runtime,
        cwd="/work",
        jail_id="fake-jail",
        jail_dir=_JAIL_DIR,
        tether=tether,
    )


def _methods(runtime: FakeRuntime) -> list[str]:
    return [call.method for call in runtime.calls]


def _rehydrated(jail: Jail, runtime: FakeRuntime) -> Jail:
    """`jail` through JSON and back, as another process would hold it."""
    return Jail.from_dict(
        json.loads(json.dumps(jail.to_dict())), runtimes={RuntimeKind.FAKE: runtime}
    )


# ---------------------------------------------------------------------------
# AC1: a launch is create then start; an exec sibling a second start.
# ---------------------------------------------------------------------------


def test_a_launch_is_create_then_start_and_a_sibling_is_a_second_start() -> None:
    runtime = FakeRuntime()
    jail = _create(runtime)
    assert _methods(runtime) == ["create"]
    assert jail.processes() == ()
    assert jail.alive() is False

    first = jail.start(["sleep", "100"])
    sibling = jail.start(["true"], cwd="/elsewhere")

    starts = [call for call in runtime.calls if call.method == "start"]
    assert [call.scope for call in starts] == [Scope.PROCESS, Scope.PROCESS]
    assert isinstance(first, Process) and isinstance(sibling, Process)
    assert (first.argv, sibling.argv) == (("sleep", "100"), ("true",))
    assert first.fidelity is sibling.fidelity is ExecFidelity.PLAIN
    assert [p.id for p in jail.processes()] == [first.id, sibling.id]
    assert first.alive() and sibling.alive() and jail.alive()

    report = jail.destroy()
    assert [(item.kind, item.identity, item.outcome) for item in report.items] == [
        ("workload_group", str(first.pid), KillOutcome.ENDED),
        ("exec_sibling", str(sibling.pid), KillOutcome.ENDED),
    ]
    assert not first.alive() and not jail.alive()


def test_a_process_is_waited_signalled_and_stopped_through_the_supervisor() -> None:
    runtime = FakeRuntime(exit_status=7)
    jail = _create(runtime)
    first = jail.start(["sleep", "100"])
    sibling = jail.start(["true"])

    assert first.interrupt() is True
    assert sibling.stop().items[0].kind == "exec_sibling"
    assert first.wait(timeout=1.0) == 7
    assert [c.method for c in runtime.calls if c.scope is Scope.PROCESS][-3:] == [
        "signal:SIGINT",
        "stop",
        "wait",
    ]


def test_a_wait_that_reaches_its_deadline_is_a_timeout() -> None:
    jail = _create(FakeRuntime(exit_status=None))
    process = jail.start(["sleep", "100"])
    with pytest.raises(TimeoutError, match="still ran"):
        process.wait(timeout=0.0)


# ---------------------------------------------------------------------------
# AC2, AC3, AC6: the dict, and rehydration with the embedder's runtimes.
# ---------------------------------------------------------------------------


def test_the_dict_is_version_6_and_round_trips_with_the_runtime_passed() -> None:
    runtime = FakeRuntime()
    jail = _create(runtime)
    first = jail.start(["sleep", "100"])
    d = jail.to_dict()
    assert d["version"] == JAIL_VERSION == 6
    assert d["runtime"] == "FAKE" and d["tethered"] is False
    assert [p["id"] for p in d["processes"]] == [first.id]
    assert not {"pid", "pgid", "argv", "launcher_name"} & set(d)

    again = _rehydrated(jail, runtime)
    assert again.to_dict() == d
    assert [p.id for p in again.processes()] == [first.id]
    assert again.processes()[0].alive() is True
    assert again.destroy().items[0].outcome is KillOutcome.ENDED
    assert first.alive() is False, "the rehydrated jail did not reach the same runtime"


def test_a_fake_record_rehydrated_with_only_the_host_runtime_passed_is_refused() -> None:
    """AC6. The dict says FAKE; the embedder passed only HOST. Refused, naming
    the kind and what to pass, so a fake record can never reach HostRuntime.
    The control: the same dict with the fake passed rehydrates."""
    runtime = FakeRuntime()
    jail = _create(runtime)
    jail.start(["sleep", "100"])
    d = jail.to_dict()

    with pytest.raises(ValueError, match=r"made by the FAKE runtime.*RuntimeKind\.FAKE") as raised:
        Jail.from_dict(d, runtimes={RuntimeKind.HOST: HostRuntime()})
    assert "passed: HOST" in str(raised.value)
    assert Jail.from_dict(d, runtimes={RuntimeKind.FAKE: runtime}).jail_id == jail.jail_id


def test_a_runtime_passed_under_another_kind_is_refused() -> None:
    d = _create(FakeRuntime()).to_dict()
    with pytest.raises(ValueError, match="for FAKE is a HOST runtime"):
        Jail.from_dict(d, runtimes={RuntimeKind.FAKE: HostRuntime()})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"version": 5}, "unsupported version 5, expected 6"),
        ({"pid": 1}, r"unknown key\(s\) \['pid'\]"),
        ({"runtime": "DOCKER"}, "'DOCKER' is no runtime kind"),
        ({"tethered": "yes"}, "'tethered' must be a bool"),
        ({"processes": [{"id": "../../etc"}]}, "no id brig makes"),
    ],
)
def test_a_dict_brig_did_not_write_is_refused(change: dict[str, object], message: str) -> None:
    runtime = FakeRuntime()
    d = {**_create(runtime).to_dict(), **change}
    with pytest.raises(ValueError, match=message):
        Jail.from_dict(d, runtimes={RuntimeKind.FAKE: runtime})


def test_a_dict_missing_a_key_or_naming_a_bad_process_is_refused() -> None:
    runtime = FakeRuntime()
    jail = _create(runtime)
    jail.start(["sleep", "100"])
    d = jail.to_dict()
    without = {k: v for k, v in d.items() if k != "processes"}
    with pytest.raises(ValueError, match="missing required key"):
        Jail.from_dict(without, runtimes={RuntimeKind.FAKE: runtime})
    twice = {**d, "processes": [*d["processes"], *d["processes"]]}
    with pytest.raises(ValueError, match="share an id"):
        Jail.from_dict(twice, runtimes={RuntimeKind.FAKE: runtime})
    bad_pid = {**d, "processes": [{**d["processes"][0], "pid": 0}]}
    with pytest.raises(ValueError, match="'pid'/'pgid' must both be ints"):
        Jail.from_dict(bad_pid, runtimes={RuntimeKind.FAKE: runtime})


def test_create_refuses_a_runtime_of_another_kind_than_the_compiled_jails() -> None:
    compiled = CompiledJail(
        spec=Spec(),
        report=unenforced_report(),
        wrap=lambda argv: argv,
        env={},
        staged=(),
        helpers=(),
        requires=frozenset(),
        mechanism_names=(),
        matrix_version=1,
        runtime=RuntimeKind.FAKE,
    )
    with pytest.raises(ValueError, match="compiled for the FAKE runtime.*passed is HOST"):
        Jail.create(compiled, runtime=HostRuntime(), cwd="/", jail_id="x", jail_dir=_JAIL_DIR)


# ---------------------------------------------------------------------------
# AC3, AC7: start absent, not raising.
# ---------------------------------------------------------------------------


def test_a_jail_with_no_supervisor_has_no_start_and_its_processes_no_control() -> None:
    """The control: the same jail with a supervisor has every one of them."""
    with_supervisor = FakeRuntime()
    jail = _create(with_supervisor)
    jail.start(["sleep", "100"])
    assert hasattr(jail, "start") and hasattr(jail, "probe")
    (process,) = jail.processes()
    assert all(hasattr(process, name) for name in ("interrupt", "stop", "wait"))

    without = FakeRuntime(has_supervisor=False)
    destroy_only = Jail.from_dict(jail.to_dict(), runtimes={RuntimeKind.FAKE: without})
    assert not hasattr(destroy_only, "start")
    assert not hasattr(destroy_only, "probe")
    assert getattr(destroy_only, "start", None) is None
    (process,) = destroy_only.processes()
    for name in ("interrupt", "stop", "wait"):
        assert not hasattr(process, name), name
    assert process.alive() is False  # this fake never started it
    assert process.exit_events() == ()
    assert [item.kind for item in destroy_only.destroy().items] == ["workload_group"]
    with pytest.raises(AttributeError, match="no supervisor"):
        _ = destroy_only.start


def test_a_jail_created_tethered_has_no_start_once_rehydrated() -> None:
    """AC7. In the process that created it, a tethered jail starts (it holds
    the tether); rehydrated anywhere, the tether's fd did not cross `to_dict`,
    so `start` and `probe` are absent while its processes are still waited
    and stopped. The control: an untethered jail rehydrated the same way
    starts."""
    runtime = FakeRuntime()
    tethered = _create(runtime, tether=_A_TETHER)
    assert hasattr(tethered, "start")
    tethered.start(["sleep", "100"])
    assert tethered.to_dict()["tethered"] is True

    elsewhere = _rehydrated(tethered, runtime)
    assert not hasattr(elsewhere, "start")
    assert not hasattr(elsewhere, "probe")
    with pytest.raises(AttributeError, match="created tethered in another process"):
        _ = elsewhere.start
    (process,) = elsewhere.processes()
    assert all(hasattr(process, name) for name in ("interrupt", "stop", "wait"))

    other = FakeRuntime()
    untethered = _create(other)
    assert hasattr(_rehydrated(untethered, other), "start")


def test_a_hand_edited_dict_does_not_give_a_tethered_jail_its_start_back() -> None:
    """Review 1 of TASK-0079.26: the dict alone can't say untethered. A
    rehydrated jail starts only when its dict AND its runtime's own record
    (`Runtime.tethered`) say so; a runtime that never created the jail can't
    tell, so `start` is absent there too. The control: the honest untethered
    jail, through the runtime that created it, starts."""
    runtime = FakeRuntime()
    tethered = _create(runtime, tether=_A_TETHER)
    edited = {**tethered.to_dict(), "tethered": False}
    forged = Jail.from_dict(edited, runtimes={RuntimeKind.FAKE: runtime})
    assert not hasattr(forged, "start") and not hasattr(forged, "probe")
    with pytest.raises(AttributeError, match="runtime's own record"):
        _ = forged.start

    honest = _create(runtime)
    assert hasattr(_rehydrated(honest, runtime), "start")
    assert not hasattr(_rehydrated(honest, FakeRuntime()), "start")
