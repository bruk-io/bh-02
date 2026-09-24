"""The command line end to end. `warden` runs until Ctrl-C, so these drive it through
compositions that fail fast (a bad --patch) rather than blocking on `invoke`."""

from collections.abc import Callable
from pathlib import Path

from click.testing import CliRunner

from warden import main


def _broken(patch: Callable[[str], Path]) -> list[str]:
    layer = patch(
        '[[plugin]]\nid = "example"\n'
        'config = { name = "example", command = ["/no/such/warden-test-binary"] }\n'
    )
    return ["--patch", str(layer)]


def test_a_failing_composition_exits_non_zero_and_reports_why(patch: Callable[[str], Path]) -> None:
    result = CliRunner().invoke(main, _broken(patch))
    assert result.exit_code == 1
    assert "error: could not start" in result.stderr


def test_trace_prints_every_row_s_lifecycle_to_stderr(patch: Callable[[str], Path]) -> None:
    result = CliRunner().invoke(main, ["--trace", *_broken(patch)])
    assert result.exit_code == 1
    assert "example#" in result.stderr
