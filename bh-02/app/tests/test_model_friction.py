"""`scripts/model-friction` over transcripts on disk: its startup-file signal counts a model that
wrote the project's startup file (`.bh-02/startup.py`), and its reuse signal counts work done again
that a variable already held."""

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "model-friction"


def _startup_findings(sessions: Path, codes: Sequence[str]) -> list[str]:
    """Run the script over one session whose model made a `python` call with each of `codes`,
    and return the codes it counted as writing a startup file."""
    session = sessions / "session-1"
    session.mkdir(parents=True)
    calls = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": f"c{n}", "name": "python", "input": {"code": code}}],
        }
        for n, code in enumerate(codes)
    ]
    (session / "transcript.jsonl").write_text("".join(json.dumps(call) + "\n" for call in calls))
    ran = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sessions", str(sessions), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    found = [json.loads(line) for line in ran.stdout.splitlines()]
    return [f["detail"] for f in found if f["signal"] == "startup_file"]


def test_a_session_whose_model_wrote_its_startup_file_is_counted(tmp_path: Path) -> None:
    """A model that writes `.bh-02/startup.py` is keeping functions for later sessions."""
    code = "from pathlib import Path\nPath('.bh-02/startup.py').write_text('def sh(): pass')"
    assert _startup_findings(tmp_path, [code]) == [" ".join(code.split())]


def test_reading_a_startup_file_or_writing_another_is_not_counted(tmp_path: Path) -> None:
    codes = [
        "print(open('.bh-02/startup.py').read())",
        "from pathlib import Path\nPath('.bh-02/notes.py').write_text('x')",
    ]
    assert _startup_findings(tmp_path, codes) == []


def _reuse_findings(sessions: Path, inputs: Sequence[tuple[str, str]], runs: Sequence[str] = ()) -> list[str]:
    """Run the script over one session whose model ran each of `inputs` (code, result) as a python
    call, a minute apart from 10:00, with a run of bh-02 starting at each of `runs`; return the
    details of its reuse misses."""
    session = sessions / "session-1"
    session.mkdir(parents=True)
    lines = []
    for n, (code, result) in enumerate(inputs):
        call = {"id": f"c{n}", "name": "python", "input": {"code": code}}
        lines.append({"role": "assistant", "content": "", "tool_calls": [call]})
        at = f"2026-10-29T10:{n:02}:00.000Z"
        lines.append(
            {"role": "tool", "content": result, "call_id": f"c{n}", "asides": [], "call": {"at": at}}
        )
    (session / "transcript.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
    starts = ["2026-10-29T09:59:00.000Z", *runs]
    (session / "rows.jsonl").write_text(
        "".join(json.dumps({"at": at, "kind": "run"}) + "\n" for at in starts)
    )
    ran = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sessions", str(sessions), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    found = [json.loads(line) for line in ran.stdout.splitlines()]
    return [f["detail"] for f in found if f["signal"] == "reuse_miss"]


_SEARCH = "hits = [p for p in Path('.').rglob('*.py') if 'retries' in p.read_text()]"
_PROGRAM = "files = subprocess.run(['git', 'ls-files'], capture_output=True, text=True).stdout"
_READ = "text = Path('a.py').read_text()"


def test_a_search_kept_and_run_again_is_a_reuse_miss(tmp_path: Path) -> None:
    """The same work, kept in the same name again, is a miss that says so."""
    found = _reuse_findings(tmp_path, [(_SEARCH, "3"), ("print(len(hits))", "3"), (_SEARCH, "")])
    assert len(found) == 1 and found[0].startswith("input 3, kept again in `hits`")


def test_a_program_kept_and_run_again_under_another_name_is_a_reuse_miss(tmp_path: Path) -> None:
    again = "listed = subprocess.run(['git', 'ls-files'], capture_output=True, text=True).stdout"
    found = _reuse_findings(tmp_path, [(_PROGRAM, ""), (again, "")])
    assert len(found) == 1 and "held by `files`, kept again as `listed`" in found[0]


def test_a_file_read_again_unchanged_is_a_reuse_miss(tmp_path: Path) -> None:
    found = _reuse_findings(tmp_path, [(_READ, ""), ("print(Path('a.py').read_text().count('x'))", "2")])
    assert len(found) == 1 and "held by `text`, computed again" in found[0]


def test_work_done_again_in_a_new_repl_is_not_a_reuse_miss(tmp_path: Path) -> None:
    """After the REPL was started again, or bh-02 was resumed, the variable is gone: doing the work
    again is right."""
    restarted = "(the REPL was started again; what earlier inputs defined is gone)\n"
    assert _reuse_findings(tmp_path / "restart", [(_SEARCH, ""), (_SEARCH, restarted)]) == []
    resumed = ["2026-10-29T10:00:30.000Z"]
    assert _reuse_findings(tmp_path / "resume", [(_SEARCH, ""), (_SEARCH, "")], resumed) == []


def test_work_done_again_after_something_could_change_it_is_not_a_reuse_miss(tmp_path: Path) -> None:
    """A file written, a program that may change files, a name the work reads bound again, the
    variable bound to something else: each makes the work worth doing again."""
    between = [
        "Path('a.py').write_text('x = 1')",
        "subprocess.run(['git', 'checkout', 'main'], capture_output=True)",
        "text = ''",
    ]
    for n, middle in enumerate(between):
        assert _reuse_findings(tmp_path / str(n), [(_READ, ""), (middle, ""), (_READ, "")]) == [], middle
    read = "name = 'a.py'\ntext = Path(name).read_text()"
    assert _reuse_findings(tmp_path / "rebound", [(read, ""), (read, "")]) == []


def test_work_not_kept_or_kept_by_an_input_that_failed_is_not_a_reuse_miss(tmp_path: Path) -> None:
    """Only what a variable holds can be reused: printed work, or work in an input that raised, was
    never kept."""
    shown = "print(Path('a.py').read_text())"
    assert _reuse_findings(tmp_path / "shown", [(shown, ""), (shown, "")]) == []
    failed = "Traceback (most recent call last):\n  ...\nKeyError: 'x'"
    assert _reuse_findings(tmp_path / "failed", [(_READ + "\nd['x']", failed), (_READ, "")]) == []


def test_a_read_only_program_between_does_not_hide_a_reuse_miss(tmp_path: Path) -> None:
    status = "print(subprocess.run(['git', 'status'], capture_output=True, text=True).stdout)"
    assert len(_reuse_findings(tmp_path, [(_READ, ""), (status, ""), (_READ, "")])) == 1
