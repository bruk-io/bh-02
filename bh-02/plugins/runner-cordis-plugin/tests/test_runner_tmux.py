"""`TMUX` and `TMUX_PANE` reach no program the runner starts: not under the confined runner (its
environment is an allowlist) and not under the unconfined one (`--no-jail`, which passes the rest
of bh-02's environment). Nor does the Claude Code token (`CLAUDE_CODE_OAUTH_TOKEN`, which the
person exports for a claude-code endpoint's `key`): it goes to the Claude Code CLI alone. A model's
provider key in bh-02's environment reaches no confined program, and does reach an unconfined one:
`--no-jail` scrubs only Claude's and tmux's variables. A program that lists its environment is
started in each, from a process that has them set (stand-in values: never a real credential)."""

import asyncio
import json
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from runner_cordis_plugin import BrigConfig, BrigJail, Unjailed

# Listens on argv[1], so the runner sees it up; writes its environment's names to argv[2].
_LISTEN_AND_LIST = """
import json, os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
with open(sys.argv[2], "w") as out:
    json.dump({"TMUX": os.environ.get("TMUX"), "TMUX_PANE": os.environ.get("TMUX_PANE"),
               "PATH": os.environ.get("PATH") is not None, "names": sorted(os.environ)}, out)
while True:
    time.sleep(0.1)
"""


@dataclass(frozen=True)
class _Host:
    paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    auto_memory: str = ""


@pytest.fixture(autouse=True)
def _keys_exported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "stand-in-token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "stand-in-key")


@pytest.fixture(autouse=True)
def _inside_tmux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-0/default,123,0")
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setenv("XDG_STATE_HOME", tempfile.mkdtemp(prefix="bh-s-", dir="/tmp"))


async def _environment_of(start: Callable[[list[str], str, str], Awaitable[Any]], project: Path) -> Any:
    """The environment a program the runner starts sees."""
    endpoint = str(Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"), "k.sock"))
    seen = project / "env.json"
    argv = [sys.executable, "-I", "-c", _LISTEN_AND_LIST, endpoint, str(seen)]
    started = await start(argv, str(project), endpoint)
    try:
        for _ in range(200):
            if seen.exists() and seen.read_text().endswith("}"):
                break
            await asyncio.sleep(0.05)
        return json.loads(seen.read_text())
    finally:
        await started.stop()


async def test_the_unconfined_runner_starts_programs_without_tmux_s_variables(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    async def start(argv: list[str], cwd: str, endpoint: str) -> Any:
        return await Unjailed().start(argv, cwd=cwd, endpoint=endpoint)

    seen = await _environment_of(start, project)
    assert seen["TMUX"] is None and seen["TMUX_PANE"] is None
    assert seen["PATH"]  # the rest of bh-02's environment still passes


async def test_the_unconfined_runner_keeps_the_claude_token_out_and_passes_provider_keys(
    tmp_path: Path,
) -> None:
    """`--no-jail`: the model's code can read a provider key in bh-02's environment (the docs
    say so), but never the Claude Code token, which only the CLI child gets."""
    project = tmp_path / "project"
    project.mkdir()

    async def start(argv: list[str], cwd: str, endpoint: str) -> Any:
        return await Unjailed().start(argv, cwd=cwd, endpoint=endpoint)

    seen = await _environment_of(start, project)
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in seen["names"]
    assert "OPENROUTER_API_KEY" in seen["names"]


async def test_the_confined_runner_starts_programs_without_tmux_s_variables(tmp_path: Path) -> None:
    if sys.platform not in ("darwin", "linux") or (
        sys.platform == "linux" and not Path("/usr/bin/bwrap").exists()
    ):
        pytest.skip("the confined runner is brig's: darwin, or Linux with /usr/bin/bwrap")
    project = tmp_path / "project"
    project.mkdir()
    jail = BrigJail(BrigConfig(), _Host())

    async def start(argv: list[str], cwd: str, endpoint: str) -> Any:
        return await jail.start(argv, cwd=cwd, endpoint=endpoint)

    seen = await _environment_of(start, project)
    assert seen["TMUX"] is None and seen["TMUX_PANE"] is None
    assert seen["PATH"]


async def test_the_confined_runner_passes_neither_the_claude_token_nor_a_provider_key(tmp_path: Path) -> None:
    if sys.platform not in ("darwin", "linux") or (
        sys.platform == "linux" and not Path("/usr/bin/bwrap").exists()
    ):
        pytest.skip("the confined runner is brig's: darwin, or Linux with /usr/bin/bwrap")
    project = tmp_path / "project"
    project.mkdir()
    jail = BrigJail(BrigConfig(), _Host())

    async def start(argv: list[str], cwd: str, endpoint: str) -> Any:
        return await jail.start(argv, cwd=cwd, endpoint=endpoint)

    seen = await _environment_of(start, project)
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in seen["names"] and "OPENROUTER_API_KEY" not in seen["names"]
