"""`strict_linux()`: membership, composition order, and the golden report.

The linux sibling of `tests/unit/test_stack_scratch_darwin_preset.py`, and
pure for the same reason that file is: a preset is data, `Stack.compile` is
a pure function of `(spec, ctx)`, and a `CompileCtx` carrying the literal
string `"linux"` compiles the whole thing on a darwin laptop. What the
report CLAIMS is pinned here; whether the claim holds is
`tests/e2e/test_strict_linux_journey.py`'s, which skips by name where no
`bwrap` exists.

The golden report is the point of the file. `strict_linux()` is the first
stack in this library to grade `enforced` on `fs_read`, `fs_write` AND
`network` off darwin, and every one of those three is a promise keel's own
floors will refuse to run without -- so a mechanism that quietly stopped
claiming one, or a preset that quietly gained a fourth member, has to
change this file to do it.
"""

from __future__ import annotations

import pytest

from brig.core import (
    Axis,
    Channel,
    ChannelKind,
    FloorViolation,
    FsPolicy,
    Grade,
    ReadModel,
    Spec,
    require,
)
from brig.mech import CompileCtx
from brig.mech.bwrap import DEFAULT_BWRAP_PATH, ReadModelUnsupported
from brig.stack import MATRIX_VERSION, strict_linux

_JAIL_DIR = "/run/brig/strictlinux"
_WORKSPACE = "/srv/ws"
_ENDPOINT = "/run/brig/strictlinux/agent.sock"

_SPEC = Spec(
    fs=FsPolicy(
        read_model=ReadModel.ALLOW_LIST,
        # `/bin` and `/usr` are not decoration: `env_scrub` composes INSIDE
        # this jail, so its `/bin/sh -c 'exec /usr/bin/env -i ...'` wrapper
        # has to exist there. `strict_linux`'s own docstring states that as
        # a precondition of the preset; this spec is what honouring it
        # looks like.
        read_allows=("/bin", "/usr"),
        write_allows=(_WORKSPACE,),
        write_denies=("/srv/ws/.envrc",),
    ),
    channels=(Channel(name="agent", kind=ChannelKind.LISTEN, endpoint=_ENDPOINT),),
)


def _ctx() -> CompileCtx:
    paths = ("/bin", "/usr", _WORKSPACE, "/srv/ws/.envrc", _ENDPOINT)
    return CompileCtx(
        jail_dir=_JAIL_DIR,
        platform="linux",
        resolved_paths={path: path for path in paths},
        path_exists={
            "/bin": True,
            "/usr": True,
            _WORKSPACE: True,
            "/srv/ws/.envrc": False,
            _ENDPOINT: False,
        },
    )


@pytest.mark.unit
def test_the_preset_is_exactly_bwrap_rlimits_env_scrub() -> None:
    """Membership, not order -- SPEC.md §7: "a preset's list is a
    MEMBERSHIP set, never a composition order"."""
    assert {m.name for m in strict_linux().mechanisms} == {"bwrap", "rlimits", "env_scrub"}


@pytest.mark.unit
def test_it_composes_rlimits_outermost_then_bwrap_then_env_scrub() -> None:
    """Read off the composed argv, which is where the matrix's decision
    actually lands, never off the preset's own list."""
    argv = strict_linux().compile(_SPEC, ctx=_ctx()).wrap(("/bin/true",))

    assert argv.index("brig.mech.trampoline") < argv.index(DEFAULT_BWRAP_PATH)
    assert argv.index(DEFAULT_BWRAP_PATH) < argv.index("/bin/sh")
    assert argv[-1] == "/bin/true"


@pytest.mark.unit
def test_the_golden_report_grades_all_seven_axes() -> None:
    """Three `enforced` from real kernel mechanisms, `env` `enforced` from
    `env_scrub`'s SCRUB, `limits` `best_effort` because `rlimits` reaches
    cpu and nothing else, and the two axes nobody claims `unenforced` via
    the coverage fill. Any change here is a change to what an embedder is
    told, so it is a reviewed diff by construction."""
    report = strict_linux().compile(_SPEC, ctx=_ctx()).report

    assert {axis: graded.grade for axis, graded in report.axes.items()} == {
        Axis.FS_READ: Grade.ENFORCED,
        Axis.FS_WRITE: Grade.ENFORCED,
        Axis.NETWORK: Grade.ENFORCED,
        Axis.LIMITS: Grade.BEST_EFFORT,
        Axis.ENV: Grade.ENFORCED,
        Axis.CHANNEL_EXCLUSIVITY: Grade.UNENFORCED,
        Axis.CONTROL: Grade.UNENFORCED,
    }


@pytest.mark.unit
def test_it_meets_the_two_floors_an_embedder_calling_this_a_sandbox_needs() -> None:
    """`fs_read` and `fs_write` `enforced` -- the pair keel's own
    `default_floors()` requires, checked here through brig's own floors
    machinery so the preset's whole reason to exist is a passing
    assertion rather than an inference from the report above."""
    compiled = strict_linux().compile(
        _SPEC, require(fs_read=Grade.ENFORCED, fs_write=Grade.ENFORCED), ctx=_ctx()
    )

    assert compiled.mechanism_names == ("bwrap", "rlimits", "env_scrub")
    assert compiled.matrix_version == MATRIX_VERSION


@pytest.mark.unit
def test_a_floor_this_preset_cannot_meet_still_refuses() -> None:
    """The control for the test above: floors are really being evaluated,
    not merely passed in. `limits` `enforced` is what this stack honestly
    does not reach."""
    with pytest.raises(FloorViolation, match="limits"):
        strict_linux().compile(_SPEC, require(limits=Grade.ENFORCED), ctx=_ctx())


@pytest.mark.unit
def test_a_denylist_spec_is_refused_by_the_preset_rather_than_translated() -> None:
    """The precondition `strict_linux`'s docstring names, executed. An
    embedder whose Spec is denylist-shaped (keel's is, because seatbelt is
    denylist-native) gets a named refusal from the mechanism, not a jail
    built to a policy nobody wrote."""
    spec = Spec(fs=FsPolicy(read_model=ReadModel.DENY_LIST, read_denies=("/home/u/.ssh",)))

    with pytest.raises(ReadModelUnsupported):
        strict_linux().compile(spec, ctx=_ctx())
