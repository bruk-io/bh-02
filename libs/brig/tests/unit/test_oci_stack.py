"""`oci` in composition and the container jail's record (decision-202): what `Stack.compile`
makes of it, what the matrix refuses beside it, what the jail's dict holds, and the pure decisions
`brig.runtime.oci` reads from the Docker CLI's own output.

Nothing here runs Docker. The CLI outputs below are what docker 29.8 printed (captured 2026-10-17):
an absent container prints `[]` and `error: no such object: <id>` (or the daemon's `No such
container`), status 1, and a daemon that is down prints `Cannot connect to the Docker daemon`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import brig.stack
from brig.core import (
    Axis,
    EnvPolicy,
    FloorViolation,
    FsPolicy,
    Grade,
    Graded,
    ReadModel,
    Spec,
    require,
)
from brig.core.runtime import ContainerPlan, RuntimeKind
from brig.mech import JAIL_LIFETIME, CompileCtx, Helper, Oci, Step
from brig.mech.bwrap import bwrap
from brig.mech.connect_proxy import ConnectProxy
from brig.mech.env_scrub import env_scrub
from brig.mech.rlimits import rlimits
from brig.mech.seatbelt import seatbelt
from brig.run import HostRuntime, Jail, UnknownChannel
from brig.run.jail import JAIL_VERSION
from brig.runtime.fake import FakeRuntime
from brig.runtime.oci import (
    Gone,
    NotOurs,
    OciCreateRefused,
    OciRuntime,
    Ours,
    Unknown,
    create_args,
    daemon_id_of,
    standing,
)
from brig.stack import (
    COMPATIBILITY_MATRIX,
    MATRIX_VERSION,
    REFUSED_PAIRS,
    AxisClaimConflict,
    CompatibilityRefused,
    ContainerConflict,
    Stack,
)

pytestmark = pytest.mark.unit

_CTX = CompileCtx(jail_dir="/run/brig/jail0", platform="linux", euid=1000)
_SPEC = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST))
_CID = "ab" * 32
_DAEMON = "0fd2dc3f-c5fb-43c6-9d4c-a06492e8e3a4"


# --- composition ---------------------------------------------------------------------------


def test_a_stack_of_oci_resolves_the_oci_runtime_and_carries_the_plan() -> None:
    compiled = Stack([Oci("img:1")]).compile(_SPEC, ctx=_CTX)
    assert compiled.runtime is RuntimeKind.OCI
    assert isinstance(compiled.container, ContainerPlan) and compiled.container.image == "img:1"
    assert compiled.supervisor is None
    assert compiled.mechanism_names == ("oci",)
    assert compiled.matrix_version == MATRIX_VERSION == 6


def test_the_report_grades_control_as_the_battery_proves_and_a_floor_on_it_is_met() -> None:
    compiled = Stack([Oci("img:1")]).compile(_SPEC, require(control=Grade.ENFORCED), ctx=_CTX)
    control = compiled.report.axes[Axis.CONTROL]
    assert control.grade is Grade.ENFORCED
    assert "docker rm -f" in control.detail and "docker inspect" in control.detail
    assert "test_oci_control" in control.detail
    assert compiled.report.axes[Axis.CHANNEL_EXCLUSIVITY].grade is Grade.UNENFORCED
    # Axes the mechanism claims: env is enforced, limits unclaimed for a Spec with no cpu limit.
    assert compiled.report.axes[Axis.ENV].grade is Grade.ENFORCED
    assert compiled.report.axes[Axis.LIMITS].grade is Grade.UNENFORCED


def test_a_floor_above_what_the_container_earns_is_still_refused() -> None:
    """The control grade rises as far as the battery proves and no further: `fs_read` is
    `best_effort` (the image), so `enforced` is refused at compile."""
    with pytest.raises(FloorViolation, match="fs_read"):
        Stack([Oci("img:1")]).compile(_SPEC, require(fs_read=Grade.ENFORCED), ctx=_CTX)


# --- the matrix ----------------------------------------------------------------------------

_OTHERS = {
    "env_scrub": (env_scrub, Axis.ENV),
    "rlimits": (rlimits, Axis.LIMITS),
    "bwrap": (bwrap, Axis.FS_READ),
    "seatbelt": (seatbelt, Axis.FS_READ),
    "connect_proxy": (ConnectProxy("/usr/bin/python3"), Axis.NETWORK),
}


@pytest.mark.parametrize("other", sorted(_OTHERS))
def test_no_other_mechanism_composes_beside_oci_and_the_claims_say_which_axis(other: str) -> None:
    mechanism, _ = _OTHERS[other]
    shared = Oci("img:1").axes & mechanism.axes
    assert shared, other
    for order in ([Oci("img:1"), mechanism], [mechanism, Oci("img:1")]):
        with pytest.raises(AxisClaimConflict) as caught:
            Stack(order).compile(_SPEC, ctx=_CTX)
        assert caught.value.axis in shared
        assert {caught.value.mechanism_a, caught.value.mechanism_b} == {"oci", other}


def test_the_matrix_lists_all_five_oci_pairs_as_refused_with_a_reason_and_composes_none() -> None:
    assert {pair for pair in REFUSED_PAIRS} == {frozenset({"oci", other}) for other in _OTHERS}
    assert not set(REFUSED_PAIRS) & set(COMPATIBILITY_MATRIX)
    for pair, reason in REFUSED_PAIRS.items():
        assert reason.strip(), pair
    assert "shell around a host argv" in REFUSED_PAIRS[frozenset({"oci", "env_scrub"})]
    assert "needs brig in the image" in REFUSED_PAIRS[frozenset({"oci", "rlimits"})]


@dataclass(slots=True)
class _Stub:
    """A mechanism with a name and one disjoint axis, so no claim conflicts and the matrix is
    what decides; it can declare a container plan."""

    name: str
    axes: frozenset[Axis]
    runtime: RuntimeKind | None = None
    plan: ContainerPlan | None = None

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        return Step(
            wrap=lambda argv: argv,
            env={},
            staged=(),
            helpers=(),
            requires=frozenset(),
            grades={axis: Graded(Grade.COOPERATIVE) for axis in self.axes},
            denial_signatures=(),
            container=self.plan,
        )


@pytest.mark.parametrize("other", ["env_scrub", "rlimits"])
def test_the_matrix_refuses_the_pair_with_its_reason_when_no_claim_conflicts(other: str) -> None:
    """The matrix's own refusal, reached: a stand-in named `oci` that claims an axis nobody else
    does, beside the real `env_scrub` and `rlimits`, is refused by rule 3 with the pair's reason
    (the real `oci` is refused earlier, on the axes it claims twice)."""
    stand_in = _Stub("oci", frozenset({Axis.CHANNEL_EXCLUSIVITY}))
    mechanism = _OTHERS[other][0]
    with pytest.raises(CompatibilityRefused) as caught:
        Stack([stand_in, mechanism]).compile(_SPEC, ctx=_CTX)
    assert {caught.value.mechanism_a, caught.value.mechanism_b} == {"oci", other}
    assert caught.value.reason == REFUSED_PAIRS[frozenset({"oci", other})]
    assert "refused by the compatibility matrix (v6)" in str(caught.value)
    assert caught.value.reason in str(caught.value)


def test_an_unknown_pair_is_refused_saying_so_and_with_no_reason() -> None:
    """The control for the test above: a pair the matrix knows nothing of has no reason."""
    first = _Stub("first", frozenset({Axis.CHANNEL_EXCLUSIVITY}))
    second = _Stub("second", frozenset({Axis.CONTROL}))
    with pytest.raises(CompatibilityRefused) as caught:
        Stack([first, second]).compile(_SPEC, ctx=_CTX)
    assert caught.value.reason is None
    assert "unknown pairs are refused" in str(caught.value)


def test_two_mechanisms_each_declaring_a_container_are_refused() -> None:
    plan = Oci("img:1").compile(_SPEC, _CTX).container
    assert plan is not None
    mechanisms = [
        _Stub("a", frozenset({Axis.CHANNEL_EXCLUSIVITY}), plan=plan),
        _Stub("b", frozenset({Axis.CONTROL}), plan=plan),
    ]
    matrix = {
        **COMPATIBILITY_MATRIX,
        frozenset({"a", "b"}): brig.stack.MatrixEntry(outer="a", rationale="a test pair"),
    }
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(brig.stack, "COMPATIBILITY_MATRIX", matrix)
        with pytest.raises(ContainerConflict, match="'a' and 'b' each declare a container"):
            Stack(mechanisms).compile(_SPEC, ctx=_CTX)


def test_the_host_runtime_refuses_a_container_jail_before_it_makes_anything(
    tmp_path: Path,
) -> None:
    """Law 2, and the check TASK-0079.03's review left for this task: a compiled jail of another
    kind is not made of host process groups."""
    compiled = Stack([Oci("img:1")]).compile(_SPEC, ctx=_CTX)
    jail_dir = tmp_path / "jail"
    with pytest.raises(ValueError, match="compiled for the OCI runtime, and this is the HOST"):
        HostRuntime().create(compiled, cwd="/", jail_id="x", jail_dir=str(jail_dir), tether=None)
    assert not jail_dir.exists()
    host = Stack([]).compile(Spec(), ctx=_CTX)
    assert host.runtime is RuntimeKind.HOST  # the control: a host jail is not refused for kind


# --- the record ----------------------------------------------------------------------------


def _oci_dict(**changes: object) -> dict[str, object]:
    """A jail dict of an OCI jail: a fake jail's, with the runtime and the container swapped in."""
    base = Jail.create(
        Stack([]).compile(Spec(), ctx=_CTX),
        runtime=FakeRuntime(),
        cwd="/",
        jail_id="j1",
        jail_dir="/run/brig/jail0",
    ).to_dict()
    base |= {"runtime": "OCI", "container": {"id": _CID, "daemon": _DAEMON}, "wrap_prefix": None}
    return base | changes


def _rehydrate(d: dict[str, object]) -> Jail:
    return Jail.from_dict(d, runtimes={RuntimeKind.OCI: OciRuntime()})


def test_the_dict_carries_the_container_and_round_trips_through_json() -> None:
    d = json.loads(json.dumps(_oci_dict()))
    assert d["version"] == JAIL_VERSION == 11
    jail = _rehydrate(d)
    again = json.loads(json.dumps(jail.to_dict()))
    assert again["container"] == {"id": _CID, "daemon": _DAEMON}
    assert again == d


def test_a_dict_names_no_daemon_address_and_one_that_does_is_refused() -> None:
    assert set(_oci_dict()["container"]) == {"id", "daemon"}  # type: ignore[call-overload]
    for forged in (
        {**_oci_dict(), "docker_host": "tcp://evil:2375"},
        _oci_dict(container={"id": _CID, "daemon": _DAEMON, "docker_host": "tcp://evil:2375"}),
    ):
        with pytest.raises(ValueError, match=r"unknown key\(s\)|must be null or"):
            _rehydrate(forged)


@pytest.mark.parametrize(
    "container",
    [
        {"id": "ab" * 31, "daemon": _DAEMON},  # not 64 hex
        {"id": "AB" * 32, "daemon": _DAEMON},  # uppercase
        {"id": "my-container", "daemon": _DAEMON},  # a name
        {"id": _CID[:12], "daemon": _DAEMON},  # a prefix, which could stand for another
        {"id": _CID, "daemon": ""},
        {"id": _CID, "daemon": "has space"},
        {"id": _CID, "daemon": "x\ny"},
        {"id": 5, "daemon": _DAEMON},
        {"id": _CID},
        "a-string",
    ],
)
def test_a_container_that_is_not_an_identity_brig_records_is_refused(container: object) -> None:
    with pytest.raises(ValueError, match="'container'"):
        _rehydrate(_oci_dict(container=container))


def test_a_dict_without_the_container_key_is_a_version_10_dict_and_is_refused() -> None:
    d = _oci_dict()
    del d["container"]
    with pytest.raises(ValueError, match=r"missing required key\(s\) \['container'\]"):
        _rehydrate(d)


def test_the_runtime_passed_for_oci_must_be_an_oci_runtime() -> None:
    with pytest.raises(ValueError, match="for OCI is a HOST runtime"):
        Jail.from_dict(_oci_dict(), runtimes={RuntimeKind.OCI: HostRuntime()})
    with pytest.raises(ValueError, match="no runtime was passed for OCI"):
        Jail.from_dict(_oci_dict(), runtimes={RuntimeKind.HOST: HostRuntime()})


def test_a_container_jail_has_no_start_and_no_probe_and_no_processes() -> None:
    """Absent, not raising (SPEC.md section 9): the runtime has no supervisor, so `hasattr` is
    false, and the jail holds nothing but its container."""
    jail = _rehydrate(_oci_dict())
    assert not hasattr(jail, "start") and not hasattr(jail, "probe")
    assert jail.processes() == ()
    assert jail.instance_group is None


def test_the_runtime_answers_for_a_process_with_no_channel_as_the_protocol_says() -> None:
    jail = _rehydrate(_oci_dict())
    runtime = OciRuntime()
    record = jail._record()
    assert runtime.supervisor(record) is None and runtime.tethered(record) is None
    with pytest.raises(ValueError, match="declares no channel"):
        runtime.reserve(record, "ctl")
    with pytest.raises(UnknownChannel):
        jail.channel("ctl")  # the jail declares none, so the runtime is never asked


def test_the_runtime_object_not_a_record_names_the_daemon() -> None:
    assert OciRuntime().docker_host == "unix:///var/run/docker.sock"
    assert OciRuntime(docker_host="tcp://10.0.0.1:2376").docker_host == "tcp://10.0.0.1:2376"
    assert OciRuntime().kind is RuntimeKind.OCI and OciRuntime().capabilities == frozenset()
    assert replace(OciRuntime(), docker="/opt/docker").docker == "/opt/docker"


# --- the decisions, read from the CLI's own output -----------------------------------------


def _inspected(*, found: str = _CID, running: bool = True, label: str | None = "j1") -> str:
    labels = (
        None if label is None else {"brig.jail": label, "org.opencontainers.image.version": "24"}
    )
    return json.dumps([{"Id": found, "State": {"Running": running}, "Config": {"Labels": labels}}])


def test_the_daemons_id_is_read_from_a_successful_info_and_only_then() -> None:
    assert daemon_id_of(0, f"{_DAEMON}\n", "") == _DAEMON
    assert (
        daemon_id_of(1, "", "Cannot connect to the Docker daemon at unix:///x. Is it running?")
        is None
    )
    assert daemon_id_of(0, "\n", "") is None
    assert (
        daemon_id_of(1, _DAEMON, "") is None
    )  # a failed call is not an answer, whatever it printed


@pytest.mark.parametrize(
    "stderr",
    [
        f"error: no such object: {_CID}\n",
        f"Error response from daemon: No such container: {_CID}\n",
    ],
)
def test_a_failed_inspect_that_says_no_such_container_is_gone(stderr: str) -> None:
    assert standing(1, "[]\n", stderr, container_id=_CID, jail_id="j1") == Gone()


def test_the_container_that_is_the_records_and_carries_the_label_is_ours() -> None:
    assert standing(0, _inspected(), "", container_id=_CID, jail_id="j1") == Ours(running=True)
    assert standing(0, _inspected(running=False), "", container_id=_CID, jail_id="j1") == Ours(
        running=False
    )


def test_a_container_that_is_another_jails_or_another_id_is_not_ours() -> None:
    other_label = standing(0, _inspected(label="j2"), "", container_id=_CID, jail_id="j1")
    assert isinstance(other_label, NotOurs) and "'j2'" in other_label.why
    no_label = standing(0, _inspected(label=None), "", container_id=_CID, jail_id="j1")
    assert isinstance(no_label, NotOurs) and "None" in no_label.why
    other_id = standing(0, _inspected(found="cd" * 32), "", container_id=_CID, jail_id="j1")
    assert isinstance(other_id, NotOurs) and ("cd" * 32) in other_id.why


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr"),
    [
        (1, "", "Cannot connect to the Docker daemon at unix:///x. Is the docker daemon running?"),
        (-1, "", "docker inspect timed out after 120s"),
        (1, "", "permission denied while trying to connect to the Docker daemon socket"),
        (0, "", ""),
        (0, "not json", ""),
        (0, "[]", ""),
        (0, "[{}]", ""),
        (0, json.dumps([{"Id": _CID}, {"Id": _CID}]), ""),
    ],
)
def test_anything_that_is_not_an_answer_about_this_container_is_unknown(
    returncode: int, stdout: str, stderr: str
) -> None:
    result = standing(returncode, stdout, stderr, container_id=_CID, jail_id="j1")
    assert isinstance(result, Unknown), result


def test_the_create_arguments_label_the_container_never_pull_and_carry_no_value() -> None:
    spec = Spec(
        fs=FsPolicy(read_model=ReadModel.ALLOW_LIST),
        env=EnvPolicy(allow_names=("TOKEN",), set=(("SECRET", "hunter2"),)),
    )
    plan = Oci("img:1").compile(spec, _CTX).container
    assert plan is not None
    args = create_args(plan, "my jail=1")
    assert args[:6] == ("create", "--pull", "never", "--label", "brig.jail=my jail=1", "--init")
    assert args[-3:] == ("img:1", "sleep", "infinity")
    assert not {"-e", "--env"} & set(args)
    assert not [arg for arg in args if "hunter2" in arg]


def test_a_jail_that_is_not_a_container_jail_is_refused_by_the_oci_runtime() -> None:
    """The runtime's half of the kind check: it refuses before any `docker` is run, a jail the
    `oci` mechanism did not compile (here the empty stack's, a HOST one)."""
    host = Stack([]).compile(Spec(), ctx=_CTX)
    with pytest.raises(OciCreateRefused, match="compiled for the HOST runtime"):
        OciRuntime().create(host, cwd="/", jail_id="x", jail_dir="/nonexistent/jail", tether=None)
    # ... and a container jail with helpers is refused rather than made without them.
    compiled = Stack([Oci("img:1")]).compile(_SPEC, ctx=_CTX)
    with_helper = replace(compiled, helpers=(Helper("h", ("true",), JAIL_LIFETIME),))
    with pytest.raises(OciCreateRefused, match="helpers or staged files"):
        OciRuntime().create(
            with_helper, cwd="/", jail_id="x", jail_dir="/nonexistent/jail", tether=None
        )
