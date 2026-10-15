"""`scripts/arch-check` indexes only what the index lacks, and what pypeeker's `check` leaves out of
its own refresh still reaches the gate: `check` indexes again a file that changed and drops one
that is gone, but never adds a module to a path it has indexed, or a path, so a new module or a
new member passes silently unless the script indexes it first.

Each test builds a small gate (a `pyproject.toml` with the `init-reexport-only` rule, whose
violation is a definition in a package `__init__.py`) and runs the script's `run_gate` over it
with the workspace's own pypeeker."""

import importlib.util
import os
import shutil
import sys
import threading
import tomllib
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "arch-check"

_GATE = """\
[tool.arch-check]
src = ["members/*/src"]

[tool.pypeeker]
src = []
plugins = ["pypeeker_rules.apps"]
rules = ["init-reexport-only"]
"""
_REEXPORTS = 'from {name}.mod import ok\n\n__all__ = ["ok"]\n'
_DEFINES = "def defined_here() -> int:\n    return 1\n"  # what init-reexport-only forbids in an __init__


@pytest.fixture
def arch_check(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The script, loaded as a module, started on the workspace's own pypeeker (not through `uv run`,
    which a test run may not have, and which would look at the lock file)."""
    loader = SourceFileLoader("arch_check", str(_SCRIPT))
    spec = importlib.util.spec_from_loader("arch_check", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    monkeypatch.setattr(module, "PYPEEKER", (str(Path(sys.executable).parent / "pypeeker"),))
    return module


@pytest.fixture
def indexed_paths(arch_check: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The paths the script asks pypeeker to index, in order."""
    asked: list[str] = []
    index = arch_check.index

    def spy(gate: Path, path: str) -> None:
        asked.append(path)
        index(gate, path)

    monkeypatch.setattr(arch_check, "index", spy)
    return asked


def _member(gate: Path, name: str, init: str = "") -> Path:
    """A member `name` with a package `name` of two files; its `__init__` re-exports unless given."""
    package = gate / "members" / name / "src" / name
    package.mkdir(parents=True)
    (package / "mod.py").write_text("def ok() -> int:\n    return 1\n")
    (package / "__init__.py").write_text(init or _REEXPORTS.format(name=name))
    return package


@pytest.fixture
def gate(tmp_path: Path) -> Path:
    """A gate with one member, `a`, that breaks no rule."""
    gate = tmp_path / "gate"
    gate.mkdir()
    (gate / "pyproject.toml").write_text(_GATE)
    _member(gate, "a")
    return gate


def _run(arch_check: ModuleType, gate: Path, capfd: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """The gate's exit code and what pypeeker printed."""
    code: int = arch_check.run_gate(gate, fix=False)
    return code, capfd.readouterr().out


def test_a_clean_gate_passes_and_leaves_nothing_without_an_index(
    arch_check: ModuleType, gate: Path, capfd: pytest.CaptureFixture[str], indexed_paths: list[str]
) -> None:
    """Also the check that the script reads the index where pypeeker writes it: were that to move,
    this finds files without an entry after a run, and the script would index every path every run."""
    assert _run(arch_check, gate, capfd) == (0, "")
    assert indexed_paths == ["members/a/src"]
    entries = arch_check.indexed(gate)
    assert entries == {"members/a/src/a/__init__.py", "members/a/src/a/mod.py"}
    files = {path: arch_check.sources(gate, path) for path in arch_check.sync_src(gate)}
    assert arch_check.without_index(files, entries) == ()


def test_a_gate_whose_files_are_all_indexed_indexes_nothing_and_still_sees_a_change(
    arch_check: ModuleType, gate: Path, capfd: pytest.CaptureFixture[str], indexed_paths: list[str]
) -> None:
    """pypeeker's check indexes again a file that changed, so the script need not."""
    _run(arch_check, gate, capfd)
    indexed_paths.clear()
    assert _run(arch_check, gate, capfd) == (0, "")
    (gate / "members/a/src/a/__init__.py").write_text(_DEFINES)

    code, out = _run(arch_check, gate, capfd)

    assert code == 1
    assert "members/a/src/a/__init__.py:1: [init-reexport-only]" in out
    assert indexed_paths == []


def test_a_new_module_in_a_path_that_is_indexed_reaches_the_gate(
    arch_check: ModuleType, gate: Path, capfd: pytest.CaptureFixture[str], indexed_paths: list[str]
) -> None:
    _run(arch_check, gate, capfd)
    indexed_paths.clear()
    (gate / "members/a/src/a/sub").mkdir()
    (gate / "members/a/src/a/sub/__init__.py").write_text(_DEFINES)

    code, out = _run(arch_check, gate, capfd)

    assert code == 1
    assert "members/a/src/a/sub/__init__.py:1: [init-reexport-only]" in out
    assert indexed_paths == ["members/a/src"]


def test_a_new_member_reaches_the_gate_and_only_its_path_is_indexed(
    arch_check: ModuleType, gate: Path, capfd: pytest.CaptureFixture[str], indexed_paths: list[str]
) -> None:
    _run(arch_check, gate, capfd)
    indexed_paths.clear()
    _member(gate, "b", init=_DEFINES)

    code, out = _run(arch_check, gate, capfd)

    assert code == 1
    assert "members/b/src/b/__init__.py:1: [init-reexport-only]" in out
    assert indexed_paths == ["members/b/src"]
    assert '"members/b/src"' in (gate / "pyproject.toml").read_text()


def test_a_member_added_before_the_first_run_is_indexed_with_the_rest(
    arch_check: ModuleType, gate: Path, capfd: pytest.CaptureFixture[str], indexed_paths: list[str]
) -> None:
    """A checkout with no index at all (a fresh clone, a new worktree) is indexed whole, not skipped."""
    _member(gate, "b", init=_DEFINES)

    code, out = _run(arch_check, gate, capfd)

    assert code == 1
    assert "members/b/src/b/__init__.py:1: [init-reexport-only]" in out
    assert indexed_paths == ["members/a/src", "members/b/src"]


def test_a_file_that_cannot_be_indexed_fails_every_run_not_only_the_first(
    arch_check: ModuleType, gate: Path
) -> None:
    """A directory named like a module cannot be read; no entry is written, so each run asks again."""
    (gate / "members/a/src/a/broken.py").mkdir()

    for _ in range(2):
        with pytest.raises(SystemExit) as stopped:
            arch_check.run_gate(gate, fix=False)
        assert stopped.value.code == 1


def test_a_src_entry_that_points_nowhere_is_refused(arch_check: ModuleType, tmp_path: Path) -> None:
    """With no `[tool.arch-check]` globs the gate's `src` is taken as written, and a path with no
    files must not read as one with nothing to index."""
    (tmp_path / "pyproject.toml").write_text('[tool.pypeeker]\nsrc = ["nowhere"]\nrules = []\n')

    with pytest.raises(SystemExit) as stopped:
        arch_check.run_gate(tmp_path, fix=False)

    assert stopped.value.code != 0


def test_a_path_is_without_an_index_when_any_of_its_files_is(arch_check: ModuleType) -> None:
    files = {"a/src": ("a/src/x.py", "a/src/y.py"), "b/src": ("b/src/z.py",), "c/src": ()}

    assert arch_check.without_index(files, frozenset({"a/src/x.py", "b/src/z.py"})) == ("a/src",)
    assert arch_check.without_index(files, frozenset()) == ("a/src", "b/src")
    assert arch_check.without_index(files, frozenset({"a/src/x.py", "a/src/y.py", "b/src/z.py"})) == ()


def test_the_src_list_is_written_through_a_temporary_file_renamed_over_the_old_one(
    arch_check: ModuleType, gate: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = gate / "pyproject.toml"
    pyproject.chmod(0o640)
    renamed: list[tuple[Path, Path]] = []
    replace = os.replace

    def spy(source: Path, target: Path) -> None:
        renamed.append((Path(source), Path(target)))
        replace(source, target)

    monkeypatch.setattr(os, "replace", spy)

    arch_check.sync_src(gate)

    [(source, target)] = renamed
    assert target == pyproject and source.parent == gate and source != pyproject  # beside it: one filesystem
    assert not source.exists() and sorted(p.name for p in gate.iterdir()) == ["members", "pyproject.toml"]
    assert '"members/a/src"' in pyproject.read_text()
    assert pyproject.stat().st_mode & 0o777 == 0o640  # the mode it had


def test_a_src_list_that_has_not_changed_leaves_the_file_alone(
    arch_check: ModuleType, gate: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arch_check.sync_src(gate)
    before = (gate / "pyproject.toml").stat()

    def refuse(source: Path, target: Path) -> None:
        raise AssertionError(f"wrote {target} though nothing changed")

    monkeypatch.setattr(os, "replace", refuse)
    arch_check.sync_src(gate)

    after = (gate / "pyproject.toml").stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def test_a_write_that_fails_leaves_the_old_file_and_no_temporary_one(
    arch_check: ModuleType, gate: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = gate / "pyproject.toml"
    before = pyproject.read_text()

    def fail(source: Path, target: Path) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr(os, "replace", fail)

    with pytest.raises(OSError, match="no space left"):
        arch_check.sync_src(gate)

    assert pyproject.read_text() == before
    assert sorted(p.name for p in gate.iterdir()) == ["members", "pyproject.toml"]


def test_a_process_reading_the_file_while_the_list_changes_never_reads_part_of_it(
    arch_check: ModuleType, gate: Path
) -> None:
    """What pytest, ruff and mypy do as they start beside arch-check: read pyproject.toml, at any
    moment. Each rewrite adds or removes a member, so the list changes every time."""
    pyproject = gate / "pyproject.toml"
    torn: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                config = tomllib.loads(pyproject.read_text())
                assert config["tool"]["pypeeker"]["src"] and config["tool"]["arch-check"]["src"]
            except (tomllib.TOMLDecodeError, KeyError, AssertionError) as error:
                torn.append(f"{type(error).__name__}: {error}")

    arch_check.sync_src(gate)
    watching = threading.Thread(target=reader)
    watching.start()
    try:
        for _ in range(400):
            _member(gate, "b")
            arch_check.sync_src(gate)
            shutil.rmtree(gate / "members" / "b")
            arch_check.sync_src(gate)
    finally:
        stop.set()
        watching.join()

    assert torn == []
