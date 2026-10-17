"""What the bwrap mechanism says its jail's PID 1 is and requires (decision-190, TASK-0079.06).

`Bwrap.compile` is pure, so all of it is checked here with no jail and no `bwrap` binary: it hands
the runtime a `SupervisorPlan` naming the interpreter, refuses a `Spec` that does not mount that
interpreter or that names a path at or above where the supervisor's program is bound, and
`Stack.compile` carries the one plan into `CompiledJail.supervisor`, refusing two. The whole
argv is pinned in `test_bwrap_compile.py`'s goldens; what runs in a real jail is
`tests/e2e/test_supervised_jail.py`'s.

Every refusal has its control in the same test: the nearest `Spec` that is not refused.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import brig.stack
from brig.core import Axis, FsPolicy, Grade, Graded, ReadModel, Spec
from brig.core.runtime import SUPERVISOR_SOURCE_PATH, RuntimeKind, SupervisorPlan
from brig.mech import CompileCtx, Step
from brig.mech.bwrap import (
    DEFAULT_INTERPRETER,
    Bwrap,
    InterpreterNotMounted,
    SupervisorSourceCovered,
    render_bwrap_prefix,
)
from brig.stack import Stack, SupervisorConflict, strict_linux

pytestmark = pytest.mark.unit

_JAIL_DIR = "/run/brig/jailsv"


def _ctx(*paths: str) -> CompileCtx:
    return CompileCtx(
        jail_dir=_JAIL_DIR,
        platform="linux",
        resolved_paths={p: p for p in paths},
        path_exists={p: True for p in paths},
    )


def _spec(*read_allows: str, write_allows: tuple[str, ...] = ()) -> Spec:
    return Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST, read_allows=read_allows, write_allows=write_allows
        )
    )


def test_the_default_plan_names_the_system_interpreter_and_a_stack_carries_it() -> None:
    spec = _spec("/usr")
    step = Bwrap().compile(spec, _ctx("/usr"))
    assert (
        step.supervisor == SupervisorPlan(DEFAULT_INTERPRETER) == SupervisorPlan("/usr/bin/python3")
    )
    compiled = strict_linux().compile(spec, ctx=_ctx("/usr"))
    assert compiled.supervisor == SupervisorPlan("/usr/bin/python3")
    # Nothing declares one, so nothing is supervised.
    assert Stack([]).compile(spec).supervisor is None


def test_a_spec_that_does_not_mount_the_interpreter_is_refused_naming_what_to_change() -> None:
    spec = _spec("/bin")
    with pytest.raises(InterpreterNotMounted) as raised:
        Bwrap().compile(spec, _ctx("/bin"))
    message = str(raised.value)
    assert "'/usr/bin/python3'" in message and "/bin" in message
    assert "Bwrap(interpreter=" in message and "strict_linux(python=" in message
    # The control: the same Spec under the interpreter it does mount.
    assert Bwrap(interpreter="/bin/python3").compile(spec, _ctx("/bin")).supervisor is not None
    assert strict_linux("/bin/python3").compile(
        spec, ctx=_ctx("/bin")
    ).supervisor == SupervisorPlan("/bin/python3")


@pytest.mark.parametrize(
    ("root", "mounted"),
    [
        ("/usr", True),
        ("/usr/bin", True),
        ("/usr/bin/python3", True),  # the interpreter's own path is a root
        ("/usr/bin/pyth", False),  # a string prefix is not a parent directory
        ("/usr/bin/python3x", False),
        ("/us", False),
        ("/opt", False),
    ],
)
def test_mounted_is_a_directory_relation_not_a_string_prefix(root: str, mounted: bool) -> None:
    spec = _spec(root)
    if mounted:
        assert Bwrap().compile(spec, _ctx(root)).supervisor is not None
    else:
        with pytest.raises(InterpreterNotMounted):
            Bwrap().compile(spec, _ctx(root))


def test_a_writable_root_that_holds_the_interpreter_mounts_it_too() -> None:
    spec = _spec("/etc", write_allows=("/usr",))
    assert Bwrap().compile(spec, _ctx("/etc", "/usr")).supervisor is not None


@pytest.mark.parametrize("named", ["/", SUPERVISOR_SOURCE_PATH])
def test_a_spec_naming_the_root_or_the_programs_own_path_is_refused(named: str) -> None:
    spec = _spec("/usr", write_allows=(named,))
    with pytest.raises(SupervisorSourceCovered) as raised:
        Bwrap().compile(spec, _ctx("/usr", named))
    assert repr(named) in str(raised.value) and SUPERVISOR_SOURCE_PATH in str(raised.value)
    # The control: a directory beside it is fine.
    beside = _spec("/usr", write_allows=("/srv/ws",))
    assert Bwrap().compile(beside, _ctx("/usr", "/srv/ws")).supervisor is not None


def test_an_interpreter_that_is_not_an_absolute_path_is_refused_when_the_mechanism_is_made() -> (
    None
):
    with pytest.raises(ValueError, match="absolute path"):
        Bwrap(interpreter="python3")
    with pytest.raises(ValueError, match="absolute path"):
        strict_linux("python3")


def test_the_render_requires_the_interpreter_as_a_keyword() -> None:
    spec = _spec("/usr")
    with pytest.raises(TypeError, match="interpreter"):
        render_bwrap_prefix(  # type: ignore[call-arg]
            spec,
            resolved={"/usr": "/usr"},
            path_exists={"/usr": True},
            jail_dir=_JAIL_DIR,
        )
    prefix = render_bwrap_prefix(
        spec,
        resolved={"/usr": "/usr"},
        path_exists={"/usr": True},
        jail_dir=_JAIL_DIR,
        interpreter="/usr/bin/python3",
    )
    assert prefix[:3] == ("/usr/bin/bwrap", "--unshare-all", "--as-pid-1")
    assert prefix[-5:] == ("--remount-ro", "/dev", "--remount-ro", "/", "--")


def test_the_supervisors_program_is_the_last_mount_before_the_root_goes_read_only() -> None:
    """Stage 7a, by position: after every other mount, so none stacks over it, and before the
    root is made read-only."""
    spec = _spec("/usr", write_allows=("/srv/ws",))
    argv = Bwrap().compile(spec, _ctx("/usr", "/srv/ws")).wrap(("sv",))
    at = argv.index("--ro-bind-data")
    assert argv[at - 2 : at] == ("--perms", "0444")
    assert argv[at + 1 : at + 3] == ("0", SUPERVISOR_SOURCE_PATH)
    assert argv[at + 3 :] == ("--remount-ro", "/dev", "--remount-ro", "/", "--", "sv")
    mounts = [i for i, token in enumerate(argv) if token in ("--ro-bind", "--bind", "--tmpfs")]
    assert max(mounts) < at


@dataclass(slots=True)
class _Declares:
    """A mechanism that declares a supervisor, to put two in one stack."""

    name: str
    axes: frozenset[Axis]
    runtime: RuntimeKind | None = RuntimeKind.HOST

    def compile(self, spec: Spec, ctx: CompileCtx) -> Step:
        del spec, ctx
        return Step(
            wrap=lambda argv: argv,
            env={},
            staged=(),
            helpers=(),
            requires=frozenset(),
            grades={axis: Graded(Grade.ENFORCED) for axis in self.axes},
            denial_signatures=(),
            supervisor=SupervisorPlan("/usr/bin/python3"),
        )


def test_two_mechanisms_declaring_a_supervisor_are_refused_and_one_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        brig.stack,
        "COMPATIBILITY_MATRIX",
        {
            frozenset({"first", "second"}): brig.stack.MatrixEntry(
                outer="first", rationale="test-seeded: one PID 1"
            )
        },
    )
    first = _Declares("first", frozenset({Axis.FS_READ}))
    second = _Declares("second", frozenset({Axis.NETWORK}))
    with pytest.raises(SupervisorConflict) as raised:
        Stack([first, second]).compile(Spec())
    assert (raised.value.mechanism_a, raised.value.mechanism_b) == ("first", "second")
    assert "one PID 1" in str(raised.value)
    # The control: either alone declares its plan and compiles.
    assert Stack([first]).compile(Spec()).supervisor == SupervisorPlan("/usr/bin/python3")
