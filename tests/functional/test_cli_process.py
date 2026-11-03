"""The CLI with files and pipes: what it reads, what it saves, and a reader that stops early."""

import subprocess
import sys
from pathlib import Path

from compressors.cli import main

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


def test_the_cli_reads_a_file_and_writes_the_pretty_copy(tmp_path, capsys):
    xml = tmp_path / "page.xml"
    xml.write_text("<a>" + "".join(f'<b id="{i}"><c/><c/><c/><c/></b>' for i in range(300)) + "</a>")
    pretty = tmp_path / "pretty.xml"
    assert main([str(xml), "--budget", "300", "--save", str(pretty)]) == 0
    assert "[fold: xml" in capsys.readouterr().out
    assert len(pretty.read_text().splitlines()) > 300
    assert main([str(tmp_path / "missing.txt")]) == 1
