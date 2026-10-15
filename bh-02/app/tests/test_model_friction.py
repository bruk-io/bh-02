"""`scripts/model-friction` over transcripts on disk: its startup-file signal counts a model that
wrote the project's startup file (`.bh-02/startup.py`)."""

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
    """A model that writes `.bh-02/startup.py` is keeping its helpers."""
    code = "from pathlib import Path\nPath('.bh-02/startup.py').write_text('def sh(): pass')"
    assert _startup_findings(tmp_path, [code]) == [" ".join(code.split())]


def test_reading_a_startup_file_or_writing_another_is_not_counted(tmp_path: Path) -> None:
    codes = [
        "print(open('.bh-02/startup.py').read())",
        "from pathlib import Path\nPath('.bh-02/notes.py').write_text('x')",
    ]
    assert _startup_findings(tmp_path, codes) == []
