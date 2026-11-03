"""Layer 2's job list: building it reads the task registry, which reads real files on this host."""

import json

from evals.l2 import file_tools, select


def test_jobs_pair_every_task_with_its_channels_conditions():
    jobs = select(["json"], ["spot"], ["M"], None)
    assert {c for _, c in jobs} == {"native", "fold", "fold-inline", "fold-all"}
    jobs = select(["python"], ["locate"], ["L"], None)
    assert {c for _, c in jobs} == {"native", "fold-tool", "noshell", "noshell-fold"} and all(
        t.path for t, _ in jobs
    )


def test_each_file_condition_gets_its_tools_and_only_noshell_fold_gets_the_fold_server(tmp_path):
    for c in ("native", "fold-tool", "noshell", "noshell-fold"):
        (tmp_path / c).mkdir()
    flags = {c: file_tools(c, tmp_path / c) for c in ("native", "fold-tool", "noshell", "noshell-fold")}
    for c, f in flags.items():
        tools = f[f.index("--allowedTools") + 1]
        assert ("Bash" in tools) == (c in ("native", "fold-tool"))
        assert "Edit" not in tools  # read tasks name real files: never edits
        assert "--strict-mcp-config" in f and ("--mcp-config" in f) == (c == "noshell-fold")
        assert ("mcp__fold__fold" in tools) == (c == "noshell-fold")
    assert flags["noshell"][flags["noshell"].index("--disallowedTools") + 1] == "Bash"
    assert (tmp_path / "fold-tool" / "CLAUDE.md").is_file() and not (
        tmp_path / "native" / "CLAUDE.md"
    ).exists()
    server = json.loads((tmp_path / "noshell-fold" / "mcp.json").read_text())["mcpServers"]["fold"]
    assert "claude_code.fold_mcp" in server["args"][-1]
