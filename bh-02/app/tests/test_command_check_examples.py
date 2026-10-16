"""`bh-02 check-examples`: the python plugin's example rule as a command for a person, a pre-commit
hook and CI. No session and no model; it exits 1 on a finding, 0 on none and 2 when it can't check."""

import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from bh_02 import main
from python_cordis_plugin.startup_check import RUFF_FLAGS

_CLEAN = 'def run(cmd):\n    """Run CMD.\n\n    >>> run("ls")\n    """\n'
_FOUND = (
    'def run(cmd):\n    """Run CMD."""\n\n\ndef go():\n    """Go.\n\n    Use::\n\n        go()\n    """\n'
)


def _command(*args: str) -> subprocess.CompletedProcess[str]:
    """The command as CI runs it: a process of its own, so its output is what a terminal would show."""
    return subprocess.run([sys.executable, "-m", "bh_02", *args], capture_output=True, text=True, check=False)


def test_it_exits_0_on_a_file_with_no_findings(tmp_path: Path) -> None:
    file = tmp_path / "startup.py"
    file.write_text(_CLEAN)
    ran = _command("check-examples", str(file))
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "", "")


def test_it_exits_1_on_a_finding_and_says_which_function_breaks_what(tmp_path: Path) -> None:
    file = tmp_path / "startup.py"
    file.write_text(_FOUND)
    ran = _command("check-examples", str(file))
    assert ran.returncode == 1
    (line,) = ran.stdout.splitlines()
    assert line.startswith(f"{file}:1: example run: no example: add a doctest block")


def test_it_checks_every_file_it_is_given_as_a_pre_commit_hook_passes_them(tmp_path: Path) -> None:
    clean, found = tmp_path / "clean.py", tmp_path / "found.py"
    clean.write_text(_CLEAN)
    found.write_text(_FOUND)
    ran = _command("check-examples", str(clean), str(found))
    assert ran.returncode == 1 and ran.stdout.startswith(f"{found}:1: example run:")


def test_it_is_a_usage_error_with_no_file_or_one_that_is_not_there(tmp_path: Path) -> None:
    for args in ((), (str(tmp_path / "nowhere.py"),), (str(tmp_path),)):
        ran = _command("check-examples", *args)
        assert (
            ran.returncode == 2 and ran.stdout == "" and "check-examples [OPTIONS] FILES..." in ran.stderr
        ), args


def test_it_is_exit_code_2_for_a_file_that_is_not_python(tmp_path: Path) -> None:
    file = tmp_path / "startup.py"
    file.write_text("def f(:\n")
    ran = _command("check-examples", str(file))
    assert ran.returncode == 2 and f"{file}: could not be checked (SyntaxError" in ran.stderr


def test_it_runs_none_of_the_file_s_code(tmp_path: Path) -> None:
    mark = tmp_path / "ran"
    file = tmp_path / "startup.py"
    file.write_text(f"open({str(mark)!r}, 'w').write('x')\nraise SystemExit(5)\n" + _CLEAN)
    ran = _command("check-examples", str(file))
    assert ran.returncode == 0 and not mark.exists()


def test_it_finds_the_plugin_s_file_without_importing_the_plugin(tmp_path: Path) -> None:
    """The app does not import a plugin (`plugin-layering`), and importing this one imports cordis:
    the command finds `startup_check.py` by the plugin's name and runs it by path, as a jail does."""
    file = tmp_path / "startup.py"
    file.write_text(_FOUND)
    script = (
        "import sys\n"
        "from click.testing import CliRunner\n"
        "from bh_02 import main\n"
        f"result = CliRunner().invoke(main, ['check-examples', {str(file)!r}])\n"
        "print(result.exit_code, 'python_cordis_plugin' in sys.modules)\n"
    )
    ran = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert ran.stdout.splitlines()[-1] == "1 False", ran.stderr


def test_the_command_is_listed_beside_the_others_and_needs_no_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    listed = CliRunner().invoke(main, ["--help"])
    assert "check-examples" in listed.output
    file = tmp_path / "startup.py"
    file.write_text(_CLEAN)
    assert CliRunner().invoke(main, ["check-examples", str(file)]).exit_code == 0
    assert not (tmp_path / "state").exists()  # no session was made


def test_the_help_gives_the_ruff_line_the_session_s_check_runs() -> None:
    """The line for CI and a pre-commit hook is the program's own flags, not a copy that drifts."""
    helped = " ".join(CliRunner().invoke(main, ["check-examples", "--help"]).output.split())
    assert f"`ruff check {' '.join(RUFF_FLAGS)} FILE`" in helped
