"""Tests for fs-write and fs-read batteries.

SPEC.md §5 (write_denies threat), §12 (every battery includes positive
controls), MILESTONES.md M5-lite scope's "battery target-resolution fix"
(`doc-016` §7 deviation 4 / §9 ask 1): probe targets resolve against the
HOST's view at battery construction, never through the jail's own
environment.

Three stacked defects, three distinct pins, per task-062's own Deliverable
table:

1. **`"$HOME"` expansion.** Pinned two ways below: BY ABSENCE (no argv
   element of either battery contains `${` or a bare `$HOME`) and BY
   CONSTRUCTION (the caller-supplied string actually appears in the argv
   that used to be built from `$HOME`).
2. **`write_outside_workspace` targeted `/`, a read-only volume regardless
   of any jail.** Pinned by the SAFETY test: every write-shaped probe's
   target begins with the caller-supplied `outside_writable` root or with
   the workspace -- never the real home, asserted over the WHOLE probe
   tuple so a later-added probe is caught too.
3. **`read_aws_credentials` targeted a file that may not exist.** Pinned by
   the REFUSAL tests: both read-side constructors refuse a missing or
   empty target rather than defaulting.

`brig/probe/batteries/fs.py`'s own module docstring names the convention
every test below leans on: a probe's `argv[-1]` is always its resolved
target path, substituted positionally as `"$0"`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from brig.core.grades import Axis
from brig.core.probes import ProbeShape
from brig.core.spec import FsPolicy, Spec
from brig.probe.batteries.fs import fs_read_battery, fs_write_battery

_FS_BATTERY_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "brig" / "probe" / "batteries" / "fs.py"
)

#: AC #7's forbidden set -- resolution is the CALLER's job, never this
#: module's. Membership, not set equality (unlike
#: `test_core_events_purity.py`'s closed-vocabulary pin): fs.py is free to
#: import other pure stdlib (it already imports `__future__`), the four
#: names below are the ones that would let it read the host itself.
_FORBIDDEN_IMPURE_MODULES = frozenset({"os", "os.path", "pathlib", "subprocess"})


def _top_level_imported_modules(source: str) -> set[str]:
    """Same walker as `test_core_events_purity.py`'s own -- only
    `tree.body` (module-level statements), so a hypothetical function-local
    import would be a different claim entirely."""
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _make_spec(workspace: str = "/tmp/ws") -> Spec:
    return Spec(fs=FsPolicy(write_allows=(workspace,)))


@pytest.mark.unit
def test_both_batteries_construct_against_a_spec_with_a_workspace() -> None:
    """fs_write_battery and fs_read_battery each construct given the new
    required host-resolved targets. Each carries exactly one CONTROL probe,
    and the probe counts are unchanged by the target-resolution fix (four
    write probes, three read probes -- only their TARGETS moved)."""
    spec = _make_spec()

    write_batt = fs_write_battery(spec, outside_writable="/tmp/ow")
    assert write_batt.name == "fs_write"
    assert write_batt.axis is Axis.FS_WRITE
    control_probes = [p for p in write_batt.probes if p.shape is ProbeShape.CONTROL]
    assert len(control_probes) == 1
    assert len(write_batt.probes) == 4

    read_batt = fs_read_battery(
        spec, credential_canary="/tmp/cc/credentials", ssh_directory_canary="/tmp/cc/ssh"
    )
    assert read_batt.name == "fs_read"
    assert read_batt.axis is Axis.FS_READ
    control_probes = [p for p in read_batt.probes if p.shape is ProbeShape.CONTROL]
    assert len(control_probes) == 1
    assert len(read_batt.probes) == 3


@pytest.mark.unit
def test_neither_battery_constructs_without_a_workspace() -> None:
    """Both factories raise ValueError against a Spec whose fs.write_allows
    is empty, even when every required target keyword is supplied. Each
    message names the axis and 'write_allows'."""
    spec = Spec(fs=FsPolicy(write_allows=()))

    with pytest.raises(ValueError) as exc_info:
        fs_write_battery(spec, outside_writable="/tmp/ow")
    assert "fs_write" in str(exc_info.value)
    assert "write_allows" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        fs_read_battery(
            spec, credential_canary="/tmp/cc/credentials", ssh_directory_canary="/tmp/cc/ssh"
        )
    assert "fs_read" in str(exc_info.value)
    assert "write_allows" in str(exc_info.value)


@pytest.mark.unit
def test_every_probe_name_and_shape_matches_the_table() -> None:
    """The batteries' (name, shape) pairs, in order, match the two tables
    quoted in the task's Deliverable, written as literal tuples in this
    test. The target-resolution fix changes TARGETS, never names or
    shapes -- a reordering or renamed probe still turns this red."""
    spec = _make_spec()

    write_batt = fs_write_battery(spec, outside_writable="/tmp/ow")
    write_expected = (
        ("write_inside_workspace", ProbeShape.CONTROL),
        ("write_outside_workspace", ProbeShape.DENIAL),
        ("write_into_home_ssh", ProbeShape.DENIAL),
        ("write_into_git_hooks_carveout", ProbeShape.DENIAL),
    )
    write_actual = tuple((p.name, p.shape) for p in write_batt.probes)
    assert write_actual == write_expected

    read_batt = fs_read_battery(
        spec, credential_canary="/tmp/cc/credentials", ssh_directory_canary="/tmp/cc/ssh"
    )
    read_expected = (
        ("read_a_workspace_file", ProbeShape.CONTROL),
        ("read_home_ssh_directory", ProbeShape.DENIAL),
        ("read_aws_credentials", ProbeShape.DENIAL),
    )
    read_actual = tuple((p.name, p.shape) for p in read_batt.probes)
    assert read_actual == read_expected


@pytest.mark.unit
def test_the_workspace_is_interpolated_from_the_spec() -> None:
    """For Spec(fs=FsPolicy(write_allows=('/tmp/ws-alpha',))) the control
    probe's argv contains the literal '/tmp/ws-alpha'. For
    write_allows=('/tmp/ws-beta',) it contains '/tmp/ws-beta' and NOT
    '/tmp/ws-alpha'. The second half catches a hard-coded path."""
    spec_alpha = _make_spec("/tmp/ws-alpha")
    batt_alpha = fs_write_battery(spec_alpha, outside_writable="/tmp/ow")
    control_alpha = next(p for p in batt_alpha.probes if p.shape is ProbeShape.CONTROL)
    assert "/tmp/ws-alpha" in control_alpha.argv
    assert "/tmp/ws-beta" not in control_alpha.argv

    spec_beta = _make_spec("/tmp/ws-beta")
    batt_beta = fs_write_battery(spec_beta, outside_writable="/tmp/ow")
    control_beta = next(p for p in batt_beta.probes if p.shape is ProbeShape.CONTROL)
    assert "/tmp/ws-beta" in control_beta.argv
    assert "/tmp/ws-alpha" not in control_beta.argv


@pytest.mark.unit
def test_the_denial_probes_target_paths_outside_the_workspace() -> None:
    """For each DENIAL probe, its argv contains no occurrence of the
    workspace root as a bare write target. The git-hooks carve-out probe is
    named as the deliberate exception and asserted separately, because
    SPEC.md section 5's write_denies threat is precisely a denied path
    INSIDE the workspace. Read denial probes target their canaries, not
    the workspace at all."""
    spec = _make_spec()

    write_batt = fs_write_battery(spec, outside_writable="/tmp/ow")
    denial_probes = [p for p in write_batt.probes if p.shape is ProbeShape.DENIAL]

    git_hooks_probe = next(p for p in denial_probes if p.name == "write_into_git_hooks_carveout")
    assert "/tmp/ws" in " ".join(git_hooks_probe.argv)  # targets inside workspace (.git/hooks)

    other_denial_probes = [p for p in denial_probes if p.name != "write_into_git_hooks_carveout"]
    for probe in other_denial_probes:
        assert "/tmp/ws" not in " ".join(probe.argv)

    read_batt = fs_read_battery(
        spec, credential_canary="/tmp/cc/credentials", ssh_directory_canary="/tmp/cc/ssh"
    )
    for probe in (p for p in read_batt.probes if p.shape is ProbeShape.DENIAL):
        assert "/tmp/ws" not in " ".join(probe.argv)


# ---------------------------------------------------------------------------
# AC #2 -- DEFECT 1 (the `"$HOME"` expansion), pinned by absence and by
# construction.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_probe_argv_contains_dollar_brace_or_bare_dollar_home() -> None:
    """DEFECT 1, pinned by ABSENCE: no argv element of any probe returned
    by either battery contains the two characters '${' or the literal text
    '$HOME'. This is a whole-battery sweep (both write and read probes,
    CONTROL included) so a probe's target reintroducing shell-variable
    expansion anywhere in this module turns it red."""
    spec = _make_spec()
    write_batt = fs_write_battery(spec, outside_writable="/tmp/ow")
    read_batt = fs_read_battery(
        spec, credential_canary="/tmp/cc/credentials", ssh_directory_canary="/tmp/cc/ssh"
    )

    for battery in (write_batt, read_batt):
        for probe in battery.probes:
            for element in probe.argv:
                assert "${" not in element, (
                    f"{battery.name}/{probe.name}: argv element {element!r} contains '${{'"
                )
                assert "$HOME" not in element, (
                    f"{battery.name}/{probe.name}: argv element {element!r} contains '$HOME'"
                )


@pytest.mark.unit
def test_the_resolved_target_appears_literally_in_the_denial_probes_argv() -> None:
    """DEFECT 1, pinned by CONSTRUCTION: the exact string the caller passed
    in for `outside_writable` / `credential_canary` / `ssh_directory_canary`
    appears literally as `probe.argv[-1]` (the module's own documented
    convention) on every probe whose target it is meant to be -- proving
    the target actually came from the caller's string, not from a
    re-derived or hard-coded one."""
    spec = _make_spec()
    outside_writable = "/tmp/ow-distinctive-42"
    credential_canary = "/tmp/cc-distinctive-43/credentials"
    ssh_directory_canary = "/tmp/cc-distinctive-44/ssh"

    write_batt = fs_write_battery(spec, outside_writable=outside_writable)
    for name in ("write_outside_workspace", "write_into_home_ssh"):
        probe = next(p for p in write_batt.probes if p.name == name)
        assert probe.argv[-1] == outside_writable

    read_batt = fs_read_battery(
        spec,
        credential_canary=credential_canary,
        ssh_directory_canary=ssh_directory_canary,
    )
    aws_probe = next(p for p in read_batt.probes if p.name == "read_aws_credentials")
    assert aws_probe.argv[-1] == credential_canary
    ssh_probe = next(p for p in read_batt.probes if p.name == "read_home_ssh_directory")
    assert ssh_probe.argv[-1] == ssh_directory_canary


# ---------------------------------------------------------------------------
# AC #5 -- SAFETY: every write-shaped probe's target is confined to the
# caller-owned scratch root or the workspace, over the WHOLE probe tuple.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_every_write_probe_target_begins_with_outside_writable_or_the_workspace() -> None:
    """Load-bearing, not hygiene (task-062 AC #5): iterates `write_batt.probes`
    itself, not a hand-picked subset of probe names, so a probe added to
    `fs_write_battery` later without following the module's own
    `argv[-1]`-is-the-target convention is caught by THIS test the moment
    it targets something outside both roots -- it does not need its own
    name added here first."""
    workspace = "/tmp/ws-safety"
    outside_writable = "/tmp/ow-safety"
    spec = _make_spec(workspace)
    write_batt = fs_write_battery(spec, outside_writable=outside_writable)

    for probe in write_batt.probes:
        target = probe.argv[-1]
        assert target.startswith(outside_writable) or target.startswith(workspace), (
            f"{probe.name}: target {target!r} is neither under outside_writable "
            f"({outside_writable!r}) nor the workspace ({workspace!r}) -- a write "
            "probe may never target a path under the real home"
        )


# ---------------------------------------------------------------------------
# AC #8 -- both constructors REFUSE rather than default a missing target.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fs_write_battery_refuses_a_missing_or_empty_outside_writable() -> None:
    spec = _make_spec()

    with pytest.raises(TypeError):
        fs_write_battery(spec)  # type: ignore[call-arg]

    with pytest.raises(ValueError) as exc_info:
        fs_write_battery(spec, outside_writable="")
    assert "outside_writable" in str(exc_info.value)


@pytest.mark.unit
def test_fs_read_battery_refuses_a_missing_or_empty_target() -> None:
    spec = _make_spec()

    with pytest.raises(TypeError):
        fs_read_battery(spec)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        fs_read_battery(spec, credential_canary="/tmp/cc")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        fs_read_battery(spec, ssh_directory_canary="/tmp/ssh")  # type: ignore[call-arg]

    with pytest.raises(ValueError) as exc_info:
        fs_read_battery(spec, credential_canary="", ssh_directory_canary="/tmp/ssh")
    assert "credential_canary" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        fs_read_battery(spec, credential_canary="/tmp/cc", ssh_directory_canary="")
    assert "ssh_directory_canary" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AC #7 -- PURITY.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fs_battery_module_imports_none_of_the_impure_modules() -> None:
    """AC #7: an AST test over brig/probe/batteries/fs.py -- parsed, not
    imported, so a plant is caught even though the plant itself would
    import cleanly -- asserts its top-level import set contains NONE of
    `os`, `os.path`, `pathlib`, `subprocess`. Membership, not set equality:
    resolving a target is the CALLER's job; this module stays pure and
    testable at the unit tier precisely because it never reaches for the
    machine itself."""
    actual = _top_level_imported_modules(_FS_BATTERY_PATH.read_text())
    forbidden_present = actual & _FORBIDDEN_IMPURE_MODULES
    assert forbidden_present == set(), (
        f"brig/probe/batteries/fs.py imports impure module(s) {forbidden_present!r} -- "
        "target resolution belongs to the caller, never this module"
    )
