"""Layer 2's job list: building it reads the task registry, which reads real files on this host."""

import json
import os
import subprocess

from evals.l2 import bash_channel, file_tools, select
from evals.tasks import bash_prompt, tasks


def test_jobs_pair_every_task_with_its_channels_conditions():
    jobs = select(["json"], ["spot"], ["M"], None)
    assert {c for _, c in jobs} == {
        "native",
        "fold",
        "fold-inline",
        "fold-all",
        "bash-native",
        "fold-bash",
        "fold-bash-all",
    }
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


def test_only_an_edit_task_may_edit(tmp_path):
    for c in ("native", "noshell-fold"):
        (tmp_path / c).mkdir()
        flags = file_tools(c, tmp_path / c, edit=True)
        assert "Edit" in flags[flags.index("--allowedTools") + 1].split(",")


def test_the_bash_channel_prints_the_payload_from_a_command_that_names_no_task(tmp_path):
    t = next(x for x in tasks() if x.task_id == "log-M-spot-at50")
    flags = bash_channel(t, "fold-bash", tmp_path, tmp_path / "hook.jsonl")
    script = (tmp_path / "get_logs").read_text()
    assert "claude_code.fixture_cmd" in script and t.task_id not in script
    hook = json.loads((tmp_path / "settings.json").read_text())["hooks"]["PostToolUse"][0]
    assert hook["matcher"] == "Bash" and "TOOL_OUTPUT_LAB_MODE=inline" in hook["hooks"][0]["command"]
    assert flags[flags.index("--allowedTools") + 1] == "Bash,Read,Grep"
    bash_channel(t, "bash-native", tmp_path, tmp_path / "hook.jsonl")
    assert json.loads((tmp_path / "settings.json").read_text()) == {}
    env = {**os.environ, "TOOL_OUTPUT_LAB_TASK": t.task_id}
    out = subprocess.run(
        ["./get_logs"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120, check=True
    )
    assert out.stdout == t.payload()
    assert bash_prompt(t).startswith(
        "Run `./get_logs` in the current directory; it prints the recent log lines"
    )
    assert bash_prompt(t).endswith(t.question) and "get_logs tool" not in bash_prompt(t)


def test_the_view_and_knobs_reach_the_hook_the_shim_and_the_fold_server(tmp_path):
    from compressors.config import DEFAULT, with_sets

    config = with_sets(DEFAULT, ["schema.rare=0.15"])
    t = next(x for x in tasks() if x.task_id == "log-M-spot-at50")
    bash_channel(t, "fold-bash", tmp_path, tmp_path / "hook.jsonl", "schema", config)
    command = json.loads((tmp_path / "settings.json").read_text())["hooks"]["PostToolUse"][0]["hooks"][0][
        "command"
    ]
    assert "TOOL_OUTPUT_LAB_VIEW=schema" in command and "TOOL_OUTPUT_LAB_SET=schema.rare=0.15" in command
    for c in ("fold-tool", "noshell-fold"):
        (tmp_path / c).mkdir()
        file_tools(c, tmp_path / c, view="schema", config=config)
    assert "--view schema --set schema.rare=0.15" in (tmp_path / "fold-tool" / "bin" / "lab-fold").read_text()
    server = json.loads((tmp_path / "noshell-fold" / "mcp.json").read_text())["mcpServers"]["fold"]
    assert server["env"] == {"TOOL_OUTPUT_LAB_VIEW": "schema", "TOOL_OUTPUT_LAB_SET": "schema.rare=0.15"}
