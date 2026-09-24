"""The `bh-02` command with the ui and the model patched to fakes: what it prints, and when."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from bh_02 import main


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    yield tmp_path


def _patch(composition: Callable[..., Path]) -> Path:
    return composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
    )


def test_trace_goes_to_a_file_because_the_app_owns_the_terminal(
    composition: Callable[..., Path], state: Path
) -> None:
    trace = state / "trace.log"
    result = CliRunner().invoke(
        main, ["--no-jail", "--patch", str(_patch(composition)), "--trace", str(trace)]
    )
    assert result.exit_code == 0, result.output
    lines = trace.read_text().splitlines()
    assert any(line.startswith("active chat#") for line in lines)
    assert any(line.startswith("unbind loop by loop#") for line in lines)  # the unwind is traced too
    assert "active chat#" not in result.output  # nothing of it on the terminal
    assert result.stderr.startswith("session ") and "bh-02 --resume" in result.stderr  # said after the run


def test_there_is_no_one_shot_command() -> None:
    result = CliRunner().invoke(main, ["ask", "hi"])
    assert result.exit_code == 2 and "No such command 'ask'" in result.stderr


def test_a_composition_that_cannot_start_is_one_line_and_exit_code_1(
    composition: Callable[..., Path], state: Path
) -> None:
    patch = composition('[[plugin]]\nid = "loop"\ndisabled = true\n[[plugin]]\nid = "ui"\ndisabled = true\n')
    result = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert result.exit_code == 1
    assert "error: could not start" in result.stderr
    assert "bh-02 --resume" not in result.stderr  # nothing to resume: the run never started
    assert "no sessions" in CliRunner().invoke(main, ["sessions"]).stderr  # and none is listed


def test_a_resumed_session_that_cannot_start_is_kept(composition: Callable[..., Path], state: Path) -> None:
    ran = CliRunner().invoke(main, ["--no-jail", "--patch", str(_patch(composition))])
    assert ran.exit_code == 0, ran.output
    patch = composition('[[plugin]]\nid = "loop"\ndisabled = true\n[[plugin]]\nid = "ui"\ndisabled = true\n')
    result = CliRunner().invoke(main, ["--resume", "--patch", str(patch)])
    assert result.exit_code == 1 and "error: could not start" in result.stderr
    assert "bh-02 --resume" in result.stderr  # it is still there to continue
    assert CliRunner().invoke(main, ["sessions"]).stdout.count("\n") == 1


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("[[plugin]\n", "Expected ']]' at the end of an array declaration"),
        ('[[plugin]]\nid = "loop"\nfoo = 1\n', "row 'loop' has unknown fields ['foo']"),
        (
            '[[plugin]]\nuse = "x:y"\n',
            'a [[plugin]] row (use = "x:y") has no \'id\'; add id = "..." naming it',
        ),
        ('[plugin]\nid = "loop"\n', "'plugin' is one table ([plugin], single brackets); write each row as a"),
        ('plugin = ["a"]\n', "'plugin' is an array of values (plugin = [...]); write each row as a"),
        ("plugin = 3\n", "'plugin' is a number (3); write each row as a [[plugin]] table"),
        ('[[plugin]]\nid = "loop"\nuse = 3\n', "row 'loop': 'use' is a number (3); it must be a string"),
        (
            '[[plugin]]\nid = "loop"\nconfig = "x"\n',
            "row 'loop': 'config' is a string (\"x\"); it must be a table",
        ),
    ],
)
def test_a_patch_that_cannot_be_read_is_one_line_exit_code_1_and_no_session(
    state: Path, text: str, why: str
) -> None:
    patch = state / "mine.toml"
    patch.write_text(text)
    result = CliRunner().invoke(main, ["--patch", str(patch)])
    assert result.exit_code == 1
    assert result.stderr.startswith(f"error: {patch}: {why}")  # the path once, then cordis's reason
    assert result.stderr.endswith("; fix the file or drop it\n") and result.stderr.count("\n") == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "no sessions" in CliRunner().invoke(main, ["sessions"]).stderr  # none left behind


def test_a_resumed_session_whose_layer_is_broken_says_which_file(
    composition: Callable[..., Path], state: Path
) -> None:
    runner = CliRunner()
    assert runner.invoke(main, ["--no-jail", "--patch", str(_patch(composition))]).exit_code == 0
    (layer,) = (state / "state").glob("bh-02/sessions/*/session.toml")
    layer.write_text("not toml at all\n")
    result = runner.invoke(main, ["--resume"])
    assert result.exit_code == 1 and "Traceback" not in result.output
    assert f"error: {layer}: " in result.stderr and "; fix the file or drop it" in result.stderr


def test_resuming_with_a_model_when_the_session_s_layer_is_broken_says_which_file(
    composition: Callable[..., Path], state: Path
) -> None:
    runner = CliRunner()
    assert runner.invoke(main, ["--no-jail", "--patch", str(_patch(composition))]).exit_code == 0
    (layer,) = (state / "state").glob("bh-02/sessions/*/session.toml")
    layer.write_text("[[plugin]\n")
    result = runner.invoke(main, ["--resume", "--model", "haiku"])
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert result.stderr.startswith(f"error: {layer}: ") and "; fix the file or drop it" in result.stderr
    assert layer.read_text() == "[[plugin]\n"  # left for the person to fix, not rewritten


def test_a_bare_resume_with_no_sessions_says_there_are_none_yet(state: Path) -> None:
    result = CliRunner().invoke(main, ["--resume"])
    assert result.exit_code == 2
    assert "no sessions in this directory yet; run bh-02 to start one" in result.stderr
    assert "''" not in result.stderr
    named = CliRunner().invoke(main, ["--resume", "nope"])
    assert "no session 'nope' in this directory" in named.stderr


def test_the_exit_line_names_the_session_unless_a_bare_resume_would_find_it(
    composition: Callable[..., Path], state: Path
) -> None:
    runner = CliRunner()
    first = runner.invoke(main, ["--no-jail", "--patch", str(_patch(composition))])
    assert first.exit_code == 0 and first.stderr.rstrip().endswith("(uv run bh-02 --resume to continue it)")
    older = first.stderr.split()[1]
    assert runner.invoke(main, ["--no-jail", "--patch", str(_patch(composition))]).exit_code == 0
    again = runner.invoke(main, ["--resume", older, "--patch", str(_patch(composition))])
    assert again.exit_code == 0, again.output
    assert again.stderr.rstrip().endswith(f"(uv run bh-02 --resume {older} to continue it)")  # not the newest


def _broken_record(state: Path, name: str = "20260101-000000-dead") -> Path:
    """A session directory whose meta.json is not JSON (a crash mid-write, a bad hand edit)."""
    record = state / "state" / "bh-02" / "sessions" / name
    record.mkdir(parents=True)
    (record / "meta.json").write_text('{"id": "20260101-000000-dead", "cwd": ')
    return record


def test_sessions_skips_a_broken_record_and_names_it_on_stderr(
    composition: Callable[..., Path], state: Path
) -> None:
    record = _broken_record(state)
    runner = CliRunner()
    alone = runner.invoke(main, ["sessions"])
    assert alone.exit_code == 0 and alone.stdout == "" and "no sessions" not in alone.stderr
    assert alone.stderr.startswith(f"warning: skipped session record {record / 'meta.json'} can't be read")
    assert "(not JSON: Expecting value" in alone.stderr
    assert alone.stderr.endswith(f"); fix it or remove {record}\n") and alone.stderr.count("\n") == 1
    ran = runner.invoke(main, ["--no-jail", "--patch", str(_patch(composition))])
    assert ran.exit_code == 0, ran.output  # a run's exit line lists the sessions too
    listing = runner.invoke(main, ["sessions"])
    assert listing.exit_code == 0 and len(listing.stdout.splitlines()) == 1
    assert listing.stderr.count("warning: skipped") == 1


def test_resume_skips_a_broken_record_and_says_why_when_it_is_named(
    composition: Callable[..., Path], state: Path
) -> None:
    record = _broken_record(state)
    runner = CliRunner()
    bare = runner.invoke(main, ["--resume"])
    assert bare.exit_code == 2 and "no sessions in this directory yet" in bare.stderr
    named = runner.invoke(main, ["--resume", "dead"])
    assert named.exit_code == 2 and "Traceback" not in named.output
    assert f"can't resume {record.name}: session record {record / 'meta.json'}" in named.stderr
    assert f"fix it or remove {record}" in named.stderr
    assert runner.invoke(main, ["--no-jail", "--patch", str(_patch(composition))]).exit_code == 0
    resumed = runner.invoke(main, ["--resume", "--patch", str(_patch(composition))])
    assert resumed.exit_code == 0, resumed.output  # the newest readable one
