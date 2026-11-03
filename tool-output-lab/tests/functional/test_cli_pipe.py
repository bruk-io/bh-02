"""The CLI as a process: a reader that closes the pipe early is not an error (review R22)."""

import subprocess
import sys
from pathlib import Path

_LAB = Path(__file__).resolve().parents[2]


def test_a_reader_that_stops_early_leaves_exit_status_0_and_nothing_on_stderr(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("".join(f"2026-11-03T10:00:{i % 60:02d}Z INFO line {i} {'x' * 80}\n" for i in range(3000)))
    proc = subprocess.Popen(  # a budget it fits in: all ~350 KB is printed, past the pipe's buffer
        [sys.executable, "-m", "compressors.cli", str(log), "--budget", "200000"],
        cwd=_LAB,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    assert proc.stdout.readline().startswith(b"2026-11-03T10:00:00Z")
    proc.stdout.close()  # what `| head -1` does
    stderr = proc.stderr.read()
    assert proc.wait(timeout=30) == 0 and stderr == b""
