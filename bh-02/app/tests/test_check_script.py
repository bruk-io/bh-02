"""`scripts/check` runs its steps at the same time and reports each one as it always has: the
step's name, everything it wrote, `ok` or `FAILED: name`, in the order of the plan, with a
non-zero exit if any step failed."""

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest
from click.testing import CliRunner

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check"


@pytest.fixture
def check() -> ModuleType:
    """The script, loaded as a module."""
    loader = SourceFileLoader("check_script", str(_SCRIPT))
    spec = importlib.util.spec_from_loader("check_script", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _python(code: str) -> tuple[str, ...]:
    return (sys.executable, "-c", code)


def _rendezvous(mine: Path, other: Path) -> tuple[str, ...]:
    """A command that ends 0 only if the one given `other` is running while it is: each writes its
    own file, then waits for the other's."""
    return _python(
        "import sys, time\n"
        "from pathlib import Path\n"
        f"mine, other = Path({str(mine)!r}), Path({str(other)!r})\n"
        "mine.touch()\n"
        "deadline = time.monotonic() + 30\n"
        "while not other.exists():\n"
        "    if time.monotonic() > deadline:\n"
        "        sys.exit(1)\n"
        "    time.sleep(0.01)\n"
    )


def _run_main(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, steps: tuple[object, ...]
) -> tuple[int, str]:
    """`main` over the given steps: its exit code and what it printed."""
    monkeypatch.setattr(check, "plan", lambda *_: steps)
    result = CliRunner().invoke(check.main, [])
    return result.exit_code, result.output


def test_the_plan_is_the_steps_in_their_order_for_the_workspace(check: ModuleType) -> None:
    steps = check.plan(None, False, True, True, False)

    assert [step.name for step in steps] == ["format", "lint", "types", "tests", "gates", "docs", "tokens"]
    by_name = {step.name: step for step in steps}
    assert by_name["format"].argv[-1] == "."
    assert by_name["lint"].argv[-2:] == ("--no-fix", ".")
    assert by_name["tests"].argv[-6:] == ("pytest", "-q", "-n", check.TEST_WORKERS, "--dist", "loadgroup")
    assert by_name["gates"].argv[-1] == "--no-fix"
    assert isinstance(by_name["tokens"], check.Skipped)


def test_the_plan_for_a_member_scopes_ruff_pytest_and_mypy_and_can_leave_out_gates_and_docs(
    check: ModuleType,
) -> None:
    steps = check.plan(Path("libs/host-paths"), True, False, False, True)

    by_name = {step.name: step for step in steps}
    assert list(by_name) == ["format", "lint", "types", "tests", "tokens"]
    assert by_name["format"].argv[-1] == "libs/host-paths"
    assert by_name["lint"].argv[-1] == "libs/host-paths"
    assert by_name["types"].argv[-1] == "libs/host-paths/src"
    assert by_name["tests"].argv[-5:] == ("-n", check.TEST_WORKERS, "--dist", "loadgroup", "libs/host-paths")
    assert isinstance(by_name["tokens"], check.Step)


def test_a_member_with_no_src_leaves_mypy_to_check_what_it_checks_everywhere(check: ModuleType) -> None:
    steps = check.plan(Path("examples/warden"), False, False, False, False)

    assert {step.name: step for step in steps}["types"].argv == ("uv", "run", "--quiet", "mypy")


def test_steps_run_at_the_same_time(check: ModuleType, tmp_path: Path) -> None:
    """Each waits for a file the other writes, so both end 0 only if they overlapped."""
    steps = (
        check.Step("one", _rendezvous(tmp_path / "one", tmp_path / "two")),
        check.Step("two", _rendezvous(tmp_path / "two", tmp_path / "one")),
    )

    assert [outcome.ok for outcome in check.outcomes(steps)] == [True, True]


def test_each_step_prints_whole_in_plan_order_whichever_ends_first(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The first step only ends once the second has, and still prints first, its stdout and stderr
    in the order it wrote them."""
    gate = tmp_path / "second-ended"
    first = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "deadline = time.monotonic() + 30\n"
        f"while not Path({str(gate)!r}).exists():\n"
        "    if time.monotonic() > deadline:\n"
        "        sys.exit(1)\n"
        "    time.sleep(0.01)\n"
        "print('first: out', flush=True)\n"
        "print('first: err', file=sys.stderr, flush=True)\n"
        "print('first: out again', flush=True)\n"
    )
    second = f"from pathlib import Path\nprint('second: out')\nPath({str(gate)!r}).touch()\n"
    steps = (check.Step("one", _python(first)), check.Step("two", _python(second)))

    code, output = _run_main(check, monkeypatch, steps)

    assert code == 0
    assert output.splitlines() == [
        "== one",
        "first: out",
        "first: err",
        "first: out again",
        "   ok",
        "== two",
        "second: out",
        "   ok",
    ]


def test_a_failed_step_is_named_the_others_still_report_and_the_exit_is_non_zero(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    steps = (
        check.Step("fine", _python("print('all good')")),
        check.Step("broken", _python("import sys; print('what failed'); sys.exit(3)")),
        check.Skipped("later", "nothing to do here"),
        check.Step("after", _python("print('still runs')")),
    )

    code, output = _run_main(check, monkeypatch, steps)

    assert code == 1
    assert output.splitlines() == [
        "== fine",
        "all good",
        "   ok",
        "== broken",
        "what failed",
        "   FAILED: broken",
        "== later",
        "   skipped: nothing to do here",
        "== after",
        "still runs",
        "   ok",
    ]


def test_a_step_that_cannot_start_has_failed_and_says_which_command(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, output = _run_main(check, monkeypatch, (check.Step("lost", ("/no/such/command", "--flag")),))

    assert code == 1
    assert "lost: could not start /no/such/command" in output
    assert output.rstrip().endswith("FAILED: lost")


def test_a_run_of_steps_that_all_pass_and_skips_exits_zero(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    steps = (check.Step("fine", _python("pass")), check.Skipped("later", "not here"))

    assert _run_main(check, monkeypatch, steps)[0] == 0
