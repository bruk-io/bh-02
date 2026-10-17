"""A stack's runtime: one kind per jail, and the two axes it grades.

SPEC.md sections 6 and 7, decision-179 (decision-0001's migration step 2,
TASK-0079.03). A mechanism names the one `RuntimeKind` it needs
(`Mechanism.runtime`); `Stack.compile` resolves exactly one (`HOST` when none
names one), refuses two different ones (law 2), carries it on
`CompiledJail.runtime`, and grades `control` and `channel_exclusivity` from
that kind's static grades, so a floor on either is checked at compile.

The grades follow the control battery (decision-201, TASK-0079.08), which
retired TASK-0079.03 AC3's pin that no stack reports either axis above
`unenforced` (WORKFLOW.md decision-041, rule 4) and replaced it with the
positive: `control` is `enforced` for the stacks whose jail has a supervisor,
the one jail type the battery was run against (`tests/e2e/test_control_battery.py`),
and `unenforced` for every other; `channel_exclusivity` is `unenforced` for all.
"""

import itertools
import sys
from dataclasses import dataclass
from enum import Enum

import pytest

from brig.core import (
    AXES,
    Axis,
    Channel,
    ChannelKind,
    FloorViolation,
    FsPolicy,
    Grade,
    Graded,
    ReadModel,
    Spec,
    require,
)
from brig.core.runtime import RUNTIME_AXES, RuntimeKind, runtime_grades
from brig.mech import CompileCtx, Mechanism, Step
from brig.mech.bwrap import bwrap
from brig.mech.connect_proxy import ConnectProxy
from brig.mech.env_scrub import env_scrub
from brig.mech.rlimits import rlimits
from brig.mech.seatbelt import Seatbelt, seatbelt
from brig.stack import (
    CompiledJail,
    RuntimeConflict,
    Stack,
    confined_egress_darwin,
    degraded,
    scratch_darwin,
    strict_linux,
)

#: Every mechanism instance brig ships, in each configuration it ships in.
_SHIPPED: tuple[Mechanism, ...] = (
    bwrap,
    ConnectProxy(sys.executable),
    env_scrub,
    rlimits,
    seatbelt,
    Seatbelt(cedes_network=True),
)

_JAIL_DIR = "/run/brig/stackruntime"

#: A spec bwrap accepts (allowlist reads, the two images env_scrub's wrap
#: execs), and its linux context; the same shape strict_linux's own test uses.
_LINUX_SPEC = Spec(
    fs=FsPolicy(
        read_model=ReadModel.ALLOW_LIST,
        read_allows=("/bin", "/usr"),
        write_allows=("/srv/ws",),
    ),
    channels=(Channel(name="ctl", kind=ChannelKind.LISTEN),),
)
_LINUX_CTX = CompileCtx(
    jail_dir=_JAIL_DIR,
    platform="linux",
    resolved_paths={p: p for p in ("/bin", "/usr", "/srv/ws")},
    path_exists={"/bin": True, "/usr": True, "/srv/ws": True},
)
_DARWIN_CTX = CompileCtx(jail_dir="/private/tmp/test", platform="darwin")


def _identity(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv


@dataclass(slots=True)
class _Named:
    """A test mechanism that names a runtime. `name` and `axes` are a real
    mechanism's, so the pair is one the compatibility matrix lists and the
    runtime rule is what is under test, not rule 3."""

    name: str
    axes: frozenset[Axis]
    runtime: object

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        del spec, ctx
        return Step(
            wrap=_identity,
            env={},
            staged=(),
            helpers=(),
            requires=frozenset(),
            grades={},
            denial_signatures=(),
        )


class _Elsewhere(Enum):
    """A runtime kind brig doesn't have, standing for the second kind a
    container runtime brings (decision-0001 step 5). `RuntimeKind` holds
    only what brig can produce, so the refusal is proven with this."""

    OCI = "OCI"


# --------------------------------------------------------------------------
# AC1: a mechanism names its runtime; exactly one per stack.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_bwrap_and_seatbelt_need_the_host_runtime_and_the_rest_name_none() -> None:
    assert {m.name: m.runtime for m in _SHIPPED} == {
        "bwrap": RuntimeKind.HOST,
        "connect_proxy": None,
        "env_scrub": None,
        "rlimits": None,
        "seatbelt": RuntimeKind.HOST,
    }
    assert Seatbelt(cedes_network=True).runtime is RuntimeKind.HOST


@pytest.mark.unit
def test_a_stack_naming_no_runtime_resolves_host() -> None:
    assert Stack([]).compile(Spec()).runtime is RuntimeKind.HOST
    assert degraded().compile(Spec()).runtime is RuntimeKind.HOST


@pytest.mark.unit
def test_a_stack_resolves_the_kind_its_mechanisms_name() -> None:
    assert strict_linux().compile(_LINUX_SPEC, ctx=_LINUX_CTX).runtime is RuntimeKind.HOST
    assert scratch_darwin().compile(Spec(), ctx=_DARWIN_CTX).runtime is RuntimeKind.HOST


@pytest.mark.unit
def test_two_mechanisms_naming_different_runtimes_are_refused() -> None:
    """Law 2: a jail runs in one runtime, so a stack naming two is refused,
    naming both mechanisms and both kinds. Control, same test: the same
    pair naming one kind compiles."""
    scrub = _Named("env_scrub", frozenset({Axis.ENV}), RuntimeKind.HOST)
    limits = _Named("rlimits", frozenset({Axis.LIMITS}), _Elsewhere.OCI)

    with pytest.raises(RuntimeConflict) as exc_info:
        Stack([scrub, limits]).compile(Spec())

    err = exc_info.value
    assert (err.mechanism_a, err.runtime_a) == ("env_scrub", RuntimeKind.HOST)
    assert (err.mechanism_b, err.runtime_b) == ("rlimits", _Elsewhere.OCI)
    message = str(err)
    assert "'env_scrub'" in message and "'rlimits'" in message
    assert "HOST" in message and "OCI" in message
    assert "exactly one runtime" in message

    limits.runtime = RuntimeKind.HOST
    assert Stack([scrub, limits]).compile(Spec()).runtime is RuntimeKind.HOST
    limits.runtime = None
    assert Stack([scrub, limits]).compile(Spec()).runtime is RuntimeKind.HOST


# --------------------------------------------------------------------------
# AC2: the kind travels on the compiled jail and grades its two axes.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_the_runtime_axes_are_control_and_channel_exclusivity() -> None:
    assert frozenset({Axis.CONTROL, Axis.CHANNEL_EXCLUSIVITY}) == RUNTIME_AXES
    for kind in RuntimeKind:
        for supervised in (False, True):
            assert frozenset(runtime_grades(kind, supervised=supervised)) == RUNTIME_AXES


@pytest.mark.unit
def test_control_and_channel_exclusivity_come_from_the_kinds_static_grades() -> None:
    """The report's two runtime axes are the resolved kind's grades for the
    jail type (supervised or not, decision-201), detail and all: the empty
    coverage fill (detail `""`) would fail this, which is what tells the two
    sources apart where both grade `unenforced`."""
    for compiled in (
        Stack([]).compile(Spec()),
        degraded().compile(Spec()),
        strict_linux().compile(_LINUX_SPEC, ctx=_LINUX_CTX),
    ):
        expected = runtime_grades(compiled.runtime, supervised=compiled.supervisor is not None)
        for axis in RUNTIME_AXES:
            assert compiled.report.axes[axis] == expected[axis]
            assert "HOST runtime" in compiled.report.axes[axis].detail


@pytest.mark.unit
def test_a_floor_on_control_the_jail_type_cannot_meet_is_refused_at_compile() -> None:
    """`require(control=...)` above what the control battery proves for the
    jail type refuses at compile, with a note naming the runtime and what to
    do: a jail with no supervisor (the empty stack, a preset without bwrap)
    grades `control` `unenforced`. Control: the same floor on a supervised
    bwrap jail, which the battery was run against, compiles."""
    floors = require(control=Grade.COOPERATIVE)
    for unsupervised in (Stack([]), degraded()):
        with pytest.raises(FloorViolation) as exc_info:
            unsupervised.compile(Spec(), floors)
        assert [s.axis for s in exc_info.value.shortfalls] == [Axis.CONTROL]
        notes = getattr(exc_info.value, "__notes__", [])
        assert len(notes) == 1
        assert "graded by the jail's runtime" in notes[0]
        assert "HOST grades control unenforced" in notes[0]
        assert "lower it" in notes[0]

    compiled = strict_linux().compile(_LINUX_SPEC, require(control=Grade.ENFORCED), ctx=_LINUX_CTX)
    assert compiled.report.axes[Axis.CONTROL].grade is Grade.ENFORCED


@pytest.mark.unit
def test_a_floor_on_channel_exclusivity_no_jail_type_meets_is_refused_at_compile() -> None:
    """Nothing establishes channel exclusivity yet, so the floor is refused
    for every stack, bwrap's included. Control: `unenforced` compiles."""
    floors = require(channel_exclusivity=Grade.COOPERATIVE)
    for stack, spec, ctx in (
        (strict_linux(), _LINUX_SPEC, _LINUX_CTX),
        (degraded(), Spec(), None),
    ):
        with pytest.raises(FloorViolation) as exc_info:
            stack.compile(spec, floors, ctx=ctx)
        assert [s.axis for s in exc_info.value.shortfalls] == [Axis.CHANNEL_EXCLUSIVITY]
        notes = getattr(exc_info.value, "__notes__", [])
        assert len(notes) == 1
        assert "HOST grades channel_exclusivity unenforced" in notes[0]

    strict_linux().compile(
        _LINUX_SPEC, require(channel_exclusivity=Grade.UNENFORCED), ctx=_LINUX_CTX
    )


@pytest.mark.unit
def test_a_floor_a_mechanism_misses_carries_no_runtime_note() -> None:
    with pytest.raises(FloorViolation) as exc_info:
        degraded().compile(Spec(), require(fs_read=Grade.ENFORCED))
    assert getattr(exc_info.value, "__notes__", []) == []


@pytest.mark.unit
def test_a_mechanism_declaring_a_runtime_axis_still_overlays_it() -> None:
    """SPEC.md section 7 (decision-179): a mechanism's claim overlays the
    runtime's grade, as on any axis; none ships (pinned below), and whether
    one may is the first such mechanism's ruling. Then no runtime note."""

    @dataclass(slots=True)
    class ClaimsControl:
        name: str = "claims-control"
        axes: frozenset[Axis] = frozenset({Axis.CONTROL})
        runtime: RuntimeKind | None = None

        def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
            del spec, ctx
            return Step(
                wrap=_identity,
                env={},
                staged=(),
                helpers=(),
                requires=frozenset(),
                grades={Axis.CONTROL: Graded(Grade.UNENFORCED, "the mechanism's own")},
                denial_signatures=(),
            )

    compiled = Stack([ClaimsControl()]).compile(Spec())
    assert compiled.report.axes[Axis.CONTROL] == Graded(Grade.UNENFORCED, "the mechanism's own")
    with pytest.raises(FloorViolation) as exc_info:
        Stack([ClaimsControl()]).compile(Spec(), require(control=Grade.COOPERATIVE))
    assert getattr(exc_info.value, "__notes__", []) == []


# --------------------------------------------------------------------------
# AC3, as decision-201 retired it: control rises only as far as the battery proves.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_control_is_graded_by_the_jail_type_and_only_a_supervised_host_jail_rises() -> None:
    """The control battery (`tests/e2e/test_control_battery.py`) was run
    against a supervised bwrap jail: its `destroy` ended every planted
    survivor, so `HOST` grades `control` `enforced` for it. It was not run
    against any other jail type (Seatbelt needs macOS), so those stay
    `unenforced` and say they are unproven, not failed. `channel_exclusivity`
    nothing has proved for any."""
    supervised = runtime_grades(RuntimeKind.HOST, supervised=True)
    unsupervised = runtime_grades(RuntimeKind.HOST, supervised=False)
    assert supervised[Axis.CONTROL].grade is Grade.ENFORCED
    assert "decision-201" in supervised[Axis.CONTROL].detail
    assert "jail scope" in supervised[Axis.CONTROL].detail
    assert unsupervised[Axis.CONTROL].grade is Grade.UNENFORCED
    assert "unproven, not failed" in unsupervised[Axis.CONTROL].detail
    assert supervised[Axis.CHANNEL_EXCLUSIVITY].grade is Grade.UNENFORCED
    assert unsupervised[Axis.CHANNEL_EXCLUSIVITY].grade is Grade.UNENFORCED
    for flag in (False, True):
        for axis, graded in runtime_grades(RuntimeKind.FAKE, supervised=flag).items():
            assert graded.grade is Grade.UNENFORCED, (flag, axis)


@pytest.mark.unit
def test_no_shipped_mechanism_declares_a_runtime_axis() -> None:
    for mechanism in _SHIPPED:
        assert not (mechanism.axes & RUNTIME_AXES), mechanism.name


def _every_compiling_stack() -> list[tuple[str, CompiledJail]]:
    """Every preset, and every stack drawn from the shipped mechanisms that
    compiles on linux or darwin; a stack the claims, matrix, platform or
    read model refuses is a refusal, not a report, and is skipped."""
    compiled: list[tuple[str, CompiledJail]] = [
        ("[]", Stack([]).compile(Spec())),
        ("degraded", degraded().compile(Spec())),
        ("strict_linux", strict_linux().compile(_LINUX_SPEC, ctx=_LINUX_CTX)),
        ("scratch_darwin", scratch_darwin().compile(Spec(), ctx=_DARWIN_CTX)),
        (
            "confined_egress_darwin",
            confined_egress_darwin(sys.executable).compile(Spec(), ctx=_DARWIN_CTX),
        ),
    ]
    for size in range(1, len(_SHIPPED) + 1):
        for members in itertools.combinations(_SHIPPED, size):
            if len({m.name for m in members}) < size:
                continue
            for spec, ctx in ((_LINUX_SPEC, _LINUX_CTX), (Spec(), _DARWIN_CTX)):
                try:
                    jail = Stack(members).compile(spec, ctx=ctx)
                except ValueError:
                    continue
                compiled.append(("+".join(m.name for m in members), jail))
    return compiled


@pytest.mark.unit
def test_every_stack_reports_control_by_its_jail_type_and_channel_exclusivity_unenforced() -> None:
    """The positive that replaces TASK-0079.03 AC3's pin over the same
    stacks: `control` is `enforced` exactly where the compiled jail has a
    supervisor (bwrap's, the jail type the battery was run against), and
    `unenforced` for the other thirty-odd, Seatbelt's included;
    `channel_exclusivity` is `unenforced` for every one."""
    compiled = _every_compiling_stack()
    names = {name for name, _ in compiled}
    assert {"strict_linux", "scratch_darwin", "bwrap+env_scrub+rlimits"} <= names
    # The count, so a stack that starts raising ValueError can't leave the pin
    # unseen; a new mechanism or preset changes it on purpose.
    assert len(compiled) == 35, sorted(names)
    supervised = {name for name, jail in compiled if jail.supervisor is not None}
    assert {"strict_linux", "bwrap+env_scrub+rlimits"} <= supervised
    assert all("bwrap" in name or name == "strict_linux" for name in supervised), supervised
    assert supervised != names
    for name, jail in compiled:
        assert set(jail.report.axes) == set(AXES)
        want = Grade.ENFORCED if name in supervised else Grade.UNENFORCED
        assert jail.report.axes[Axis.CONTROL].grade is want, name
        assert jail.report.axes[Axis.CHANNEL_EXCLUSIVITY].grade is Grade.UNENFORCED, name
