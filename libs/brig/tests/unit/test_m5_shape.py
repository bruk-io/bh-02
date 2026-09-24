"""M5-lite shape verification: seatbelt mechanism exists exactly as specified,
no new layers, allow-table unchanged since M0, no raising stubs.

This task (task-068) pins the shape that M5-lite adds: the seatbelt mechanism.
It verifies:
1. seatbelt mechanism exists under brig/mech/
2. No new layers exist (only core, mech, stack, run, probe)
3. No observe layer exists
4. The [tool.pypeeker.brig-layers.allow] table is unchanged since M0 baseline
5. No raising stubs (NotImplementedError) in seatbelt

The three checks about `examples/` are gone: Phase 0 landed brig in the keel
workspace without the adoption kit, whose job -- wiring brig into an embedding
project -- the workspace's own sandbox executor takes over. `scripts/verify.sh`
went with it; `tools/verify.sh` at the workspace root is the one gate now.
"""

import ast
import re
import tomllib
from pathlib import Path

import pytest

#: brig landed in the keel workspace as `packages/brig` (Phase 0), so paths
#: are rooted at THIS FILE, not at the process's cwd. A cwd-relative
#: `Path("brig")` here would not fail -- it would scan nothing and pass.
_BRIG = Path(__file__).resolve().parents[2] / "src" / "brig"

#: The layer table moved with it: the workspace root pyproject owns
#: `[tool.pypeeker.brig-layers]`.
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


@pytest.mark.unit
def test_seatbelt_mechanism_exists() -> None:
    """AC #1a: seatbelt mechanism exists as a directory under brig/mech/."""
    seatbelt_dir = _BRIG / "mech" / "seatbelt"
    assert seatbelt_dir.is_dir(), "brig/mech/seatbelt directory should exist"

    # Also verify seatbelt doesn't exist as a .py file
    seatbelt_file = _BRIG / "mech" / "seatbelt.py"
    assert not seatbelt_file.exists(), "seatbelt should be a directory, not a file"


@pytest.mark.unit
def test_layer_set_is_exactly_right() -> None:
    """AC #1b: find brig -maxdepth 1 -type d matches expected set exactly.
    No new layers have been added; the set is still core, mech, stack, run, probe."""
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
    """AC #2: observe layer does not exist as directory or module file."""
    brig_dir = _BRIG

    # Check directory
    observe_dir = brig_dir / "observe"
    assert not observe_dir.exists(), "brig/observe directory should not exist"

    # Check module file
    observe_file = brig_dir / "observe.py"
    assert not observe_file.exists(), "brig/observe.py file should not exist"


@pytest.mark.unit
def test_allow_table_unchanged_since_m0() -> None:
    """AC #3: the `[tool.pypeeker.brig-layers.allow]` allow-table section is
    NOTE (decision-133, 2026-08-29): `proxy` joined the set when M6's egress
    filter landed. It is a standalone PROCESS rather than a layer in the
    flow -- it runs trusted-side, outside the jail, and its allow row is
    EMPTY, so the gate refuses any import of brig from it. The pin is
    updated rather than relaxed: a new directory under `brig/` still fails
    this test until someone writes down what it is.

    unchanged except for rows recorded as decisions. The comparison is SCOPED
    to the ALLOW TABLE only -- not to `[tool.pypeeker]` as a whole, and never
    to the whole `pyproject.toml`. Phase 0 moved the table into the keel
    workspace's root pyproject, where the surrounding keys legitimately differ
    from brig's own repo (`src`, `rules` and `plugins` now name keel's gates
    too, and `root` is the path `packages/brig/brig`). None of that is the
    layer graph, so none of it may redden this pin. The rows are what is
    pinned, and they are byte-for-byte what M0 declared.

    The baseline text is quoted here directly (the M0 allow-table as of commit
    c257ba9). Being literal means the mutation-control plant runs entirely on
    in-memory strings -- the live `pyproject.toml` on disk is never written,
    so there is nothing to restore (WORKFLOW.md's stated scratch-copy
    preference, taken to its conclusion: no copy is needed because nothing
    is mutated on disk at all).
    """

    def allow_table(text: str) -> dict[str, object]:
        """Pure function: parse TOML `text` and return the layer allow table.
        Comments and whitespace vanish under parsing, so only a real content
        change -- a row added, removed, or given a different value -- can make
        two calls to this function compare unequal."""
        section = tomllib.loads(text)["tool"]["pypeeker"]["brig-layers"]["allow"]
        assert isinstance(section, dict)
        return section

    # M0 baseline [tool.pypeeker] section (commit c257ba9)
    baseline_text = """[tool.pypeeker]
src = ["brig"]
rules = [
    "brig-layers",
    "no-import-cycles",
    "import-time-side-effects",
]
plugins = ["pypeeker_rules.layers"]

[tool.pypeeker.brig-layers]
root = "brig"
strict = true

[tool.pypeeker.brig-layers.allow]
core    = []
mech    = ["core"]
stack   = ["core", "mech"]
run     = ["core", "mech", "stack"]
observe = ["core", "run"]
probe   = ["core", "run", "observe"]
proxy   = []
"""

    working_text = _PYPROJECT.read_text()

    baseline_section = allow_table(baseline_text)
    working_section = allow_table(working_text)

    # --- baseline: the allow table, and only it, is unchanged since M0 --
    # passes with the workspace's own legitimate deltas around it present. ---
    assert working_section == baseline_section, (
        "the brig-layers allow table (layer graph) changed since M0 "
        f"baseline c257ba9:\nbaseline={baseline_section}\nworking={working_section}"
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

    planted_section = allow_table(planted_text)
    assert planted_section != baseline_section, (
        "plant-control FAILED: a real allow-table row change (mech gains "
        "'stack') did not redden the section comparison, so the "
        "baseline-equal assertion above would be vacuous -- it would report "
        "green even if the actual layer graph were altered right now."
    )

    # --- control: the unmutated working section still compares equal ---
    # (restated explicitly, paired with the plant, rather than only relying
    # on the baseline assertion earlier in this test)
    assert allow_table(working_text) == baseline_section


@pytest.mark.unit
def test_no_raising_stubs_in_seatbelt() -> None:
    """AC #4: No function or method body in brig/mech/seatbelt consists solely
    of raising NotImplementedError or a bare raise. Scan is over the parsed
    module (AST), not a text grep, so a docstring mentioning NotImplementedError
    cannot satisfy or break it (decision-026 rule 6).

    Handles both:
    - raise NotImplementedError (ast.Name form)
    - raise NotImplementedError(...) (ast.Call form)
    - bare raise outside an except handler (ast.Raise(exc=None) not in ExceptHandler)
    """
    seatbelt_dir = _BRIG / "mech" / "seatbelt"

    class RaisingStubVisitor(ast.NodeVisitor):
        """Find raising stubs: functions that only raise NotImplementedError
        or bare-raise (outside an except handler)."""

        def __init__(self) -> None:
            self.in_except_handler = False
            self.stubs_found: list[tuple[str, str]] = []

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            """Track when we're inside an except handler."""
            old_flag = self.in_except_handler
            self.in_except_handler = True
            self.generic_visit(node)
            self.in_except_handler = old_flag

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            """Check if this function is a raising stub."""
            self._check_function_body(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            """Check if this async function is a raising stub."""
            self._check_function_body(node)
            self.generic_visit(node)

        def _check_function_body(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            """Check if a function body is a raising stub."""
            if not node.body:
                return

            # Skip if there's a docstring as the first item (then check the rest)
            first_stmt_idx = 0
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                first_stmt_idx = 1

            if first_stmt_idx >= len(node.body):
                # Only docstring, no code
                return

            # Check if the remaining body is a single raise statement
            if len(node.body) == first_stmt_idx + 1:
                stmt = node.body[first_stmt_idx]
                if isinstance(stmt, ast.Raise):
                    # Check for bare raise (outside except handler)
                    if stmt.exc is None and not self.in_except_handler:
                        self.stubs_found.append((node.name, "bare raise"))
                        return

                    # Check for raise NotImplementedError (Name or Call form)
                    if isinstance(stmt.exc, ast.Name) and stmt.exc.id == "NotImplementedError":
                        self.stubs_found.append((node.name, "raise NotImplementedError"))
                        return

                    if (
                        isinstance(stmt.exc, ast.Call)
                        and isinstance(stmt.exc.func, ast.Name)
                        and stmt.exc.func.id == "NotImplementedError"
                    ):
                        self.stubs_found.append((node.name, "raise NotImplementedError(...)"))
                        return

    # Walk all .py files in seatbelt
    for py_file in seatbelt_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        visitor = RaisingStubVisitor()
        visitor.visit(tree)

        assert not visitor.stubs_found, (
            f"Found raising stubs in {py_file}: "
            f"{[(name, form) for name, form in visitor.stubs_found]}"
        )


# task-068's AC #5 and AC #6 -- `examples` present in `scripts/verify.sh`'s
# PY_TREES and in `[tool.mypy] files`, and every `brig.*` import under
# `examples/` staying on the public surface -- have no subject any more.
# Phase 0 landed brig in the keel workspace without the adoption kit: the job
# `examples/harness_adapter.py` was a template for is the workspace's own
# sandbox executor, which is written against the real ports rather than a
# mirrored shape of them. `scripts/verify.sh` went with it, replaced by
# `tools/verify.sh` at the workspace root.
#
# AC #7 (`verify.sh full` exits 0) was never an in-file assertion either: a
# test that shells out to the very script collecting it is an unbounded
# recursive spawn, not a slow test. It is evidence gathered by running the
# command, and `tools/verify.sh` is now the command.
