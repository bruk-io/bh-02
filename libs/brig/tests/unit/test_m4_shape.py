"""M4 shape verification: probe layer exists exactly as specified, no observe,
allow-table unchanged since M0, no raising stubs, no import-time side effects.

This task (task-055) pins the shape that M4 adds: the probe layer and its
position in the layer DAG. It verifies:
1. Exactly the right layers exist (core, mech, probe, run, stack)
2. No observe layer exists
3. The [tool.pypeeker...] allow-table SECTION (not the whole pyproject.toml)
   is unchanged since M0 baseline (c257ba9) -- narrowed under task-071 /
   decision-128, amending task-055's original whole-file pin
4. The probe row in the allow-table is correct
5. No raising stubs (NotImplementedError) in probe
6. No __main__ trap in probe
7. Probe imports only from allowed layers

Phase 0 landed brig in the keel workspace as `packages/brig`. Two checks that
drove the architecture gate as a SUBPROCESS from inside a test are gone with
that move -- they wrote to the source tree and to the one `.pypeeker` index
`tools/verify.sh` reads. See the notes at each site.
"""

import ast
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

#: brig landed in the keel workspace as `packages/brig` (Phase 0), so the
#: paths this file pins are rooted at THIS FILE rather than at the process's
#: cwd, which is now the workspace root and no longer brig's own repo root.
#: A cwd-relative `Path("brig")` here would not fail -- it would silently scan
#: nothing and pass, which is the failure mode every check below exists to
#: prevent.
_BRIG = Path(__file__).resolve().parents[2] / "src" / "brig"

#: The layer table moved with it: the workspace root pyproject owns
#: `[tool.pypeeker.brig-layers]`, alongside keel's own import table.
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _allow_of(section: dict[str, object]) -> dict[str, object]:
    """The `brig-layers.allow` table out of a parsed `tool.pypeeker`."""
    layers = section["brig-layers"]
    assert isinstance(layers, dict)
    allow = layers["allow"]
    assert isinstance(allow, dict)
    return allow


@pytest.mark.unit
def test_layer_set_is_exactly_right() -> None:
    """AC #1: find brig -maxdepth 1 -type d matches expected set exactly."""
    brig_dir = _BRIG
    expected_layers = {"core", "mech", "probe", "proxy", "run", "stack"}

    # Get actual layers (directories, excluding __pycache__)
    actual = {d.name for d in brig_dir.iterdir() if d.is_dir() and d.name != "__pycache__"}

    assert actual == expected_layers, (
        f"Layer set mismatch. Expected {sorted(expected_layers)}, got {sorted(actual)}"
    )

    # Also verify no layer exists as a .py file (AC #1's file-form check)
    for layer_name in expected_layers:
        layer_file = brig_dir / f"{layer_name}.py"
        assert not layer_file.exists(), f"Layer {layer_name} should be a directory, not a file"


@pytest.mark.unit
def test_no_observe_layer() -> None:
    """AC #2: observe layer does not exist as directory or module file,
    and 'brig.observe' string does not appear in any .py file."""
    brig_dir = _BRIG

    # Check directory
    observe_dir = brig_dir / "observe"
    assert not observe_dir.exists(), "brig/observe directory should not exist"

    # Check module file
    observe_file = brig_dir / "observe.py"
    assert not observe_file.exists(), "brig/observe.py file should not exist"

    # Check for 'brig.observe' string in all Python files
    for py_file in brig_dir.rglob("*.py"):
        content = py_file.read_text()
        assert "brig.observe" not in content, f"Found 'brig.observe' in {py_file}"


@pytest.mark.unit
def test_allow_table_unchanged_since_m0() -> None:
    """AC #3 (narrowed under decision-128 / task-071, amending task-055's
    over-broad pin per decision-078): the `[tool.pypeeker.brig-layers.allow]`
    table -- the layer DAG from SPEC.md section 13 -- is unchanged since the
    M0 baseline commit c257ba9. The comparison is SCOPED to that table only,
    never the whole `pyproject.toml`, which in the keel workspace also carries
    keel's own gates and has no business reddening this pin.

    The baseline used to be read with `git show c257ba9:packages/brig/...`.
    That commit does not exist in this repository: Phase 0 landed brig through
    `git subtree split`, which rewrites every commit, so the old sha resolves
    to nothing and the check would have failed loudly (never silently) here.
    The baseline is quoted instead, exactly as `test_m5_shape.py` already
    quotes its own -- the value it pins is the M0 table, not the mechanism
    that fetched it.

    Being a pure function of text means the mutation-control plant below runs
    entirely on in-memory strings -- the live `pyproject.toml` on disk is never
    written, so there is nothing to restore.
    """

    def allow_table(text: str) -> dict[str, object]:
        """Pure function: parse TOML `text` and return the layer allow table.
        Comments and whitespace vanish under parsing, so only a real content
        change -- a row added, removed, or given a different value -- can make
        two calls compare unequal."""
        return _allow_of(tomllib.loads(text)["tool"]["pypeeker"])

    #: The M0 allow table (commit c257ba9 in brig's own repository), verbatim.
    BASELINE: dict[str, object] = {
        "core": [],
        "mech": ["core"],
        "stack": ["core", "mech"],
        "run": ["core", "mech", "stack"],
        "observe": ["core", "run"],
        "probe": ["core", "run", "observe"],
    }

    working_text = _PYPROJECT.read_text()

    # --- baseline: the allow table, and only it, differs from M0 by DECLARED
    # rows and nothing else.
    #
    # `SANCTIONED_ROWS` is what keeps this a pin rather than a rubber stamp:
    # the working table is folded back to the M0 shape by removing exactly
    # these rows, and anything else -- a new undeclared layer, a widened
    # existing row -- still fails. Adding a row here is the deliberate act
    # of recording a layer, and every entry names its decision. ---
    SANCTIONED_ROWS: dict[str, list[str]] = {
        # decision-133: the egress filter is a standalone process, not a
        # layer in the flow. The EMPTY value is the point: it may import
        # nothing from brig. A non-empty `proxy` row fails this test.
        "proxy": [],
    }
    working = allow_table(working_text)
    folded = {key: value for key, value in working.items() if key not in SANCTIONED_ROWS}
    for row, value in SANCTIONED_ROWS.items():
        assert working.get(row) == value, (
            f"sanctioned row {row!r} is present but no longer {value!r}: "
            f"{working.get(row)!r}. Widening a declared row is "
            "a layer-graph change like any other -- record it, do not edit it in."
        )
    assert folded == BASELINE, (
        "the brig-layers allow table (layer graph) changed since M0 "
        f"baseline c257ba9 in ways not listed in SANCTIONED_ROWS:\n"
        f"baseline={BASELINE}\nworking(folded)={folded}"
    )

    # --- plant-control: prove the equality above is actually meaningful ---
    # A REAL allow-table row change (mech gains "stack"), not a whitespace
    # edit to a section header -- a whitespace-only plant would vanish under
    # this tomllib-parsed comparator and prove nothing. Planted purely in
    # memory: mutates the in-memory `working_text` string only, so the file
    # on disk is never touched and no restore step is needed.
    mech_row = re.compile(r'^mech\s*=\s*\["core"\]\s*$', re.MULTILINE)
    assert mech_row.search(working_text), (
        "plant target (the 'mech' allow-table row) not found in "
        "pyproject.toml; AC #3's mutation-check cannot run"
    )
    planted_text = mech_row.sub('mech = ["core", "stack"]', working_text, count=1)
    assert planted_text != working_text

    assert allow_table(planted_text) != BASELINE, (
        "plant-control FAILED: a real allow-table row change (mech gains "
        "'stack') did not redden the section comparison, so the "
        "baseline-equal assertion above would be vacuous -- it would report "
        "green even if the actual layer graph were altered right now."
    )

    # --- control: the unmutated working table, folded, still compares
    # equal --- (restated explicitly, paired with the plant, rather than
    # only relying on the baseline assertion earlier in this test)
    assert {
        key: value for key, value in allow_table(working_text).items() if key not in SANCTIONED_ROWS
    } == BASELINE


@pytest.mark.unit
def test_probe_row_in_allow_table() -> None:
    """AC #4: [tool.pypeeker.brig-layers.allow] probe row equals
    ['core', 'run', 'observe'] exactly."""
    with open(_PYPROJECT, "rb") as f:
        config = tomllib.load(f)

    allow_table = config["tool"]["pypeeker"]["brig-layers"]["allow"]
    expected_probe = ["core", "run", "observe"]

    assert "probe" in allow_table, "probe key missing from allow table"
    actual_probe = allow_table["probe"]

    assert actual_probe == expected_probe, (
        f"probe row mismatch. Expected {expected_probe}, got {actual_probe}"
    )


@pytest.mark.unit
def test_no_raising_stubs_in_probe() -> None:
    """AC #5: No function or method body in brig/probe consists solely of
    a raise NotImplementedError. Also check grep output for the string."""
    probe_dir = _BRIG / "probe"

    # AST-based check: look for bodies that only raise NotImplementedError
    for py_file in probe_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and len(node.body) == 1
                and isinstance(node.body[0], ast.Raise)
                and isinstance(node.body[0].exc, ast.Name)
                and node.body[0].exc.id == "NotImplementedError"
            ):
                pytest.fail(f"Found raising stub in {py_file}: {node.name}")

    # Also grep for the literal string (AC #5 requirement). The path is
    # absolute: a cwd-relative "brig/" would make grep exit 2 for a missing
    # directory, which is also non-zero, and this assertion would pass while
    # scanning nothing.
    result = subprocess.run(
        ["/usr/bin/grep", "-rn", "NotImplementedError", str(_BRIG)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, (
        f"grep over {_BRIG} exited {result.returncode} "
        f"(1 means 'searched, found nothing'): {result.stdout}{result.stderr}"
    )


@pytest.mark.unit
def test_no_main_trap_in_probe() -> None:
    """AC #6: no `if __name__` guard anywhere under brig/probe.

    AC #6's other half -- `pypeeker check --strict` exits 0 -- is no longer
    asserted from inside a test. It used to shell out to `pypeeker index brig`
    here, which in the keel workspace would both fail (there is no `brig/` at
    the workspace root) and, worse, rewrite the single `.pypeeker` index that
    `tools/verify.sh` checks moments later. The workspace's own verify.sh runs
    `pypeeker index packages && pypeeker check --strict` as its last two
    steps, over this tree and every other; that is where the claim lives now.
    """
    for py_file in (_BRIG / "probe").rglob("*.py"):
        content = py_file.read_text()
        assert "if __name__" not in content, f"Found 'if __name__' in {py_file}"


@pytest.mark.unit
def test_probe_imports_only_allowed_layers() -> None:
    """AC #7: probe/**.py only imports from core, run, probe (not mech, stack)."""
    probe_dir = _BRIG / "probe"
    allowed = {"core", "run", "probe"}
    disallowed = {"mech", "stack"}

    for py_file in probe_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text())

        for node in ast.walk(tree):
            # Handle: from brig.<layer> import ...
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("brig."):
                layer = node.module.split(".", 1)[1].split(".", 1)[0]

                assert layer not in disallowed, (
                    f"{py_file} imports from disallowed layer: brig.{layer}"
                )
                assert layer in allowed, f"{py_file} imports from undeclared layer: brig.{layer}"


# AC #8's mutation check -- plant `from brig.stack import Stack` in
# `brig/probe/verdict.py`, watch both `pypeeker check --strict` and the import
# scan above go red, restore, three times over -- is no longer a test in this
# file. It wrote to the source tree and re-ran `pypeeker index` mid-suite, so
# under the keel workspace it would corrupt the one shared index that
# `tools/verify.sh` checks, and it shelled out to `uv run pytest tests/...`
# with brig's own repo root assumed as cwd. The plant is a thing you DO, with
# the tree quiet, and Phase 0 re-ran it in this workspace: a cross-layer
# import inside brig makes `pypeeker check --strict` exit non-zero on the
# `brig-layers` rule, and reverting it makes it green again.
