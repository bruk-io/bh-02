"""The fold MCP server as a process, over stdio, on a real file."""

import json
import subprocess
import sys
from pathlib import Path

_LAB = Path(__file__).resolve().parents[2]


def test_the_server_folds_a_real_file_over_stdio(tmp_path):
    src = tmp_path / "big.py"
    src.write_text(
        "".join(f"def f{i}(x):\n" + "".join(f"    y{j} = x + {j}\n" for j in range(20)) for i in range(60))
    )
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "fold", "arguments": {"path": str(src), "budget": 300}},
        },
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "claude_code.fold_mcp"],
        cwd=_LAB,
        input="".join(json.dumps(m) + "\n" for m in messages),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    text = replies[1]["result"]["content"][0]["text"]
    assert text.startswith("[fold: code (python),") and "1\tdef f0(x):" in text
