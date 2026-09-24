"""Unit tests for `brig.mech.seatbelt.Seatbelt`: the mechanism class
task-059 adds on top of task-058's pure `render_sbpl` -- axes as pinned
data, the four named refusals, the wrap's pure-argv-prefix property (both
asserted directly AND proved by `launcher.py`'s own real
`_derive_wrap_prefix`), the load-bearing grade-detail tokens, the denial
signature in both match directions, and the compatibility-matrix rows plus
the resulting three-mechanism composition order.

All pure: no I/O, no clock, no subprocess -- `Seatbelt.compile` reads only
its own arguments (SPEC.md §6). Every `CompileCtx` here is constructed by
hand with the LITERAL string `"darwin"` for `platform`, never `sys.platform`
-- this keeps the unit tier host-independent (a non-darwin CI runner still
exercises every non-refusal branch identically); `jail_dir` values are
already-resolved `/private/tmp/...` forms so no test here trips the LEXICAL
`UnresolvedPath` guard `render_sbpl` holds against a symlinked root by
accident.
"""

from __future__ import annotations

import re

import pytest

import brig.stack
from brig.core import (
    Axis,
    Channel,
    ChannelKind,
    FsPolicy,
    Grade,
    NetworkPolicy,
    ReadModel,
    Spec,
)
from brig.mech import CompileCtx
from brig.mech.env_scrub import env_scrub
from brig.mech.rlimits import rlimits
from brig.mech.seatbelt import (
    NetworkUnsupported,
    PlatformUnsupported,
    ReadModelUnsupported,
    UnresolvedPath,
    seatbelt,
)
from brig.run.launcher import _derive_wrap_prefix
from brig.stack import Stack

_JAIL_DIR = "/private/tmp/seatbelt-unit-test"
_CTX = CompileCtx(jail_dir=_JAIL_DIR, platform="darwin")


# --------------------------------------------------------------------------
# AC #3: axes pinned as data.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_axes_is_exactly_fs_read_fs_write_network_excluding_channel_exclusivity() -> None:
    """`seatbelt.axes` is exactly `{FS_READ, FS_WRITE, NETWORK}`, and
    `Axis.CHANNEL_EXCLUSIVITY` is explicitly NOT in it (decision-118: the
    roster row's "channel binds" names work this mechanism does, not an
    axis it claims) -- so a later widening is a visible diff."""
    assert seatbelt.axes == frozenset({Axis.FS_READ, Axis.FS_WRITE, Axis.NETWORK})
    assert Axis.CHANNEL_EXCLUSIVITY not in seatbelt.axes


# --------------------------------------------------------------------------
# AC #4: the wrap is a PURE argv prefix, proved, not merely asserted.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_wrap_is_a_pure_argv_prefix_verified_by_derive_wrap_prefix() -> None:
    """Applies `Step.wrap` to a known argv and asserts the result equals
    the three-element `sandbox-exec` prefix followed by that argv
    unchanged, element by element -- AND runs the actual
    `launcher.py::_derive_wrap_prefix` verification `handle.exec`
    (task-046) depends on, so this checks the real constraint rather than
    a proxy for it."""
    step = seatbelt.compile(Spec(), _CTX)
    argv = ("/bin/echo", "hi", "there")
    result = step.wrap(argv)

    expected_prefix = ("/usr/bin/sandbox-exec", "-f", f"{_JAIL_DIR}/seatbelt.sb")
    assert result == (*expected_prefix, *argv)
    for i, token in enumerate(argv):
        assert result[len(expected_prefix) + i] == token

    derived = _derive_wrap_prefix(result, argv)
    assert derived == expected_prefix


# --------------------------------------------------------------------------
# AC #2: the four refusals, each naming its subject.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_refuses_non_darwin_platform_naming_it() -> None:
    """Case 1: `ctx.platform != 'darwin'` -- `PlatformUnsupported`, naming
    the platform string."""
    ctx = CompileCtx(jail_dir=_JAIL_DIR, platform="linux")
    with pytest.raises(PlatformUnsupported, match=re.escape("'linux'")):
        seatbelt.compile(Spec(), ctx)


@pytest.mark.unit
def test_refuses_allow_list_read_model_naming_the_model() -> None:
    """Case 2: `spec.fs.read_model is ReadModel.ALLOW_LIST` --
    `ReadModelUnsupported`, propagated UNCHANGED from `profile.render_sbpl`
    (never re-checked or re-raised by `Seatbelt.compile` itself)."""
    spec = Spec(fs=FsPolicy(read_model=ReadModel.ALLOW_LIST))
    with pytest.raises(ReadModelUnsupported, match=r"ReadModel\.ALLOW_LIST"):
        seatbelt.compile(spec, _CTX)


@pytest.mark.unit
def test_refuses_non_empty_allowed_domains_naming_the_domain() -> None:
    """Case 3: `spec.network.allowed_domains` non-empty --
    `NetworkUnsupported`, naming the offending domain."""
    spec = Spec(network=NetworkPolicy(allowed_domains=("example.com",)))
    with pytest.raises(NetworkUnsupported, match=re.escape("example.com")):
        seatbelt.compile(spec, _CTX)


@pytest.mark.unit
def test_refuses_unresolved_write_allow_naming_that_path() -> None:
    """Case 4: a path `render_sbpl` needs that `ctx.resolved_paths` does
    not carry -- `UnresolvedPath`, propagated UNCHANGED from
    `profile.render_sbpl`, naming the unresolved path. `_CTX`'s
    `resolved_paths` is the empty default, so this write_allows entry is
    unresolved by construction."""
    spec = Spec(fs=FsPolicy(write_allows=(f"{_JAIL_DIR}/workspace",)))
    with pytest.raises(UnresolvedPath, match=re.escape(f"{_JAIL_DIR}/workspace")):
        seatbelt.compile(spec, _CTX)


# --------------------------------------------------------------------------
# AC #6: grade details pinned by content.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_fs_read_grade_is_enforced_with_denylist_named_in_detail() -> None:
    step = seatbelt.compile(Spec(), _CTX)
    graded = step.grades[Axis.FS_READ]
    assert graded.grade is Grade.ENFORCED
    assert "denylist" in graded.detail


@pytest.mark.unit
def test_fs_write_grade_is_enforced_with_write_denies_named_in_detail() -> None:
    step = seatbelt.compile(Spec(), _CTX)
    graded = step.grades[Axis.FS_WRITE]
    assert graded.grade is Grade.ENFORCED
    assert "write_denies" in graded.detail


@pytest.mark.unit
def test_network_grade_with_listen_channel_names_unscoped_bind_and_file_write_confinement() -> None:
    """For a spec with a LISTEN channel, the network detail must name that
    `network-bind` is UNSCOPED by dialect necessity and that the socket
    path is confined by the `file-write*` literal rule instead."""
    endpoint = f"{_JAIL_DIR}/control.sock"
    spec = Spec(channels=(Channel(name="control", kind=ChannelKind.LISTEN, endpoint=endpoint),))
    ctx = CompileCtx(jail_dir=_JAIL_DIR, platform="darwin", resolved_paths={endpoint: endpoint})
    step = seatbelt.compile(spec, ctx)
    graded = step.grades[Axis.NETWORK]
    assert graded.grade is Grade.ENFORCED
    assert "unscoped" in graded.detail
    assert "file-write" in graded.detail


@pytest.mark.unit
def test_network_grade_without_listen_channel_does_not_claim_unscoped() -> None:
    """Control for the test above: a spec with no LISTEN channel must NOT
    claim 'unscoped' network-bind (there is none to claim) -- proving the
    assertion above is genuinely conditional, not always-true prose."""
    step = seatbelt.compile(Spec(), _CTX)
    graded = step.grades[Axis.NETWORK]
    assert graded.grade is Grade.ENFORCED
    assert "unscoped" not in graded.detail


# --------------------------------------------------------------------------
# AC #9 (plus its positive control): the denial signature in both match
# directions.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_denial_signature_matches_operation_not_permitted() -> None:
    """Positive control: matches the exact darwin sandbox denial text
    (empirically observed via `sandbox-exec`, see this task's Evidence),
    `/bin/sh: <path>: Operation not permitted`."""
    step = seatbelt.compile(Spec(), _CTX)
    assert len(step.denial_signatures) == 1
    pattern = step.denial_signatures[0]
    assert pattern.search(f"/bin/sh: {_JAIL_DIR}/outside.txt: Operation not permitted") is not None


@pytest.mark.unit
def test_denial_signature_does_not_match_generic_failures() -> None:
    """AC #9: proved in the NOT-match direction too, per the unit-tier
    rule -- the signature must not match a generic failure that merely
    happens to occur near a denial attempt."""
    step = seatbelt.compile(Spec(), _CTX)
    pattern = step.denial_signatures[0]
    assert pattern.search("bash: spin: command not found") is None
    assert pattern.search("No such file or directory") is None


# --------------------------------------------------------------------------
# Deliverable: env/helpers/requires empty, staged profile shape.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_env_helpers_requires_are_empty_and_staged_profile_shape() -> None:
    step = seatbelt.compile(Spec(), _CTX)
    assert dict(step.env) == {}
    assert step.helpers == ()
    assert step.requires == frozenset()
    assert len(step.staged) == 1
    staged = step.staged[0]
    assert staged.relpath == "seatbelt.sb"
    assert staged.mode == 0o600
    assert staged.content.startswith("(version 1)\n")


# --------------------------------------------------------------------------
# AC #7: both matrix rows, non-empty rationale, and the composed order for
# the three-mechanism stack -- read off Stack.compile's own composition.
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_matrix_has_rlimits_seatbelt_row_rlimits_outermost_with_nonempty_rationale() -> None:
    matrix = dict(brig.stack.COMPATIBILITY_MATRIX)
    entry = matrix[frozenset({"rlimits", "seatbelt"})]
    assert entry.rationale.strip() != ""
    assert entry.outer == "rlimits"
    assert "seatbelt" in entry.rationale


@pytest.mark.unit
def test_matrix_has_seatbelt_env_scrub_row_seatbelt_outermost_with_nonempty_rationale() -> None:
    matrix = dict(brig.stack.COMPATIBILITY_MATRIX)
    entry = matrix[frozenset({"seatbelt", "env_scrub"})]
    assert entry.rationale.strip() != ""
    assert entry.outer == "seatbelt"
    assert "env_scrub" in entry.rationale


@pytest.mark.unit
def test_matrix_key_set_is_exactly_the_pairs_across_every_mechanism() -> None:
    """The whole-matrix cardinality claim `tests/unit/test_stack_compile.py`
    used to pin (`len(matrix) == 1`, task-037) moved HERE rather than being
    dropped when task-059 added two more rows -- that file's own version is
    narrowed to look up its own `{env_scrub, rlimits}` pair (see this
    task's forced-edit notes), so the "no row can silently appear or
    vanish" property needs a home. This is STRICTLY MORE falsifiable than
    the old `len == 1` ever was: it pins the exact KEY SET, not just a
    count, so a row added, dropped, or swapped for a wrong pair all fail
    here, in a file this task owns outright.

    task-080/decision-135 adds connect_proxy's three rows, completing the
    square across all four mechanisms that now exist -- a forced edit of the
    same kind task-059 made, and exactly the reviewer-facing diff this pin
    exists to produce. decision-159 adds bwrap's four for the same reason,
    two of which record a pairing no stack can compose (both mechanisms
    claim `network`, so the claim step refuses first) -- an unreachable
    pair still needs a row, because `Stack.compile` refuses an UNKNOWN pair
    and the two words are not the same claim."""
    assert set(brig.stack.COMPATIBILITY_MATRIX) == {
        frozenset({"env_scrub", "rlimits"}),
        frozenset({"rlimits", "seatbelt"}),
        frozenset({"seatbelt", "env_scrub"}),
        frozenset({"connect_proxy", "env_scrub"}),
        frozenset({"connect_proxy", "seatbelt"}),
        frozenset({"connect_proxy", "rlimits"}),
        frozenset({"bwrap", "rlimits"}),
        frozenset({"bwrap", "env_scrub"}),
        frozenset({"bwrap", "seatbelt"}),
        frozenset({"bwrap", "connect_proxy"}),
    }


@pytest.mark.unit
def test_three_mechanism_stack_composes_rlimits_outermost_then_seatbelt_then_env_scrub() -> None:
    """The composed order for the three-mechanism stack is `rlimits`
    outermost, then `seatbelt`, then `env_scrub` -- read off
    `Stack.compile`'s own composition, never off the list order `Stack()`
    was constructed with. Constructed here in a SCRAMBLED order
    deliberately (`env_scrub`, `seatbelt`, `rlimits`), so a bug that fell
    back to list order would be caught, not accidentally hidden."""
    jail_dir = "/private/tmp/seatbelt-stack-order"
    ctx = CompileCtx(jail_dir=jail_dir, platform="darwin")
    stack = Stack([env_scrub, seatbelt, rlimits])
    compiled = stack.compile(Spec(), ctx=ctx)
    result = compiled.wrap(("/bin/true",))

    trampoline_idx = result.index("brig.mech.trampoline")
    sandbox_idx = result.index("/usr/bin/sandbox-exec")
    shell_idx = result.index("/bin/sh")
    assert trampoline_idx < sandbox_idx < shell_idx
    assert result[-1] == "/bin/true"
