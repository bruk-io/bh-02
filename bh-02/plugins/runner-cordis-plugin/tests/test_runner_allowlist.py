"""The jail's environment allow-list (decision-0010): `~/.config/bh-02/runner.toml` names the
variables the jail lets through on top of its baseline. A layer's `env` replaces the file's list, a
file the model could have written is not read, a file that is wrong stops the row, and a name an
endpoint's `key = { env = ... }` reads is refused. The values here are stand-ins, never a real key."""

import asyncio
import json
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from cordis.testing import drive
from runner_cordis_plugin import BASELINE_ENV, BrigConfig, Runner, allowlist, confined


@dataclass(frozen=True)
class _Host:
    paths: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    auto_memory: str = ""
    key_envs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    models_file: str = ""


def _file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "xdg" / "bh-02" / "runner.toml"
    path.parent.mkdir(parents=True)
    path.write_text(text)
    return path


def test_the_file_is_where_the_models_file_is() -> None:
    home = Path("/home/me")
    assert allowlist.location({}, home) == home / ".config/bh-02/runner.toml"
    assert allowlist.location({"XDG_CONFIG_HOME": "/x"}, home) == Path("/x/bh-02/runner.toml")
    assert allowlist.location({"XDG_CONFIG_HOME": "rel"}, home) == home / ".config/bh-02/runner.toml"


def test_a_file_lists_its_names_once_in_order() -> None:
    assert allowlist.parsed('env = ["B", "A", "B"]', "f") == ("B", "A")
    assert allowlist.parsed("", "f") == ()


@pytest.mark.parametrize(
    ("text", "says"),
    [
        ("env = [", "is not TOML"),
        ('env = ["A"]\nallow = ["x"]', "'allow'"),
        ('env = "A"', "env must be a list"),
        ("env = [1]", "env must be a list"),
        ('env = ["A=secret-value"]', "not variable names"),
    ],
)
def test_a_file_that_is_wrong_is_refused_saying_what_to_fix(text: str, says: str) -> None:
    with pytest.raises(allowlist.Refused) as raised:
        allowlist.parsed(text, "/c/runner.toml")
    assert says in str(raised.value) and "/c/runner.toml" in str(raised.value)


def test_a_missing_file_leaves_the_baseline(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    standing = allowlist.read(tmp_path / "xdg" / "bh-02" / "runner.toml", project)
    assert standing == allowlist.Standing()
    config, note = allowlist.effective(BrigConfig(), standing, file=tmp_path, readers={}, models_file="m")
    assert config.env == BASELINE_ENV and note == ""


def test_a_file_outside_the_project_is_read(tmp_path: Path) -> None:
    path = _file(tmp_path, 'env = ["GITHUB_TOKEN"]')
    project = tmp_path / "project"
    project.mkdir()
    standing = allowlist.read(path, project)
    config, _ = allowlist.effective(BrigConfig(), standing, file=path, readers={}, models_file="m")
    assert config.env == (*BASELINE_ENV, "GITHUB_TOKEN")


def test_a_file_in_the_project_is_not_read_and_the_person_is_told_where_to_put_it(tmp_path: Path) -> None:
    path = tmp_path / ".config" / "bh-02" / "runner.toml"  # run from the home directory
    path.parent.mkdir(parents=True)
    path.write_text('env = ["GITHUB_TOKEN"]')
    standing = allowlist.read(path, tmp_path)
    assert standing.names == () and "is not read" in standing.unread and "XDG_CONFIG_HOME" in standing.unread
    config, note = allowlist.effective(BrigConfig(), standing, file=path, readers={}, models_file="m")
    assert config.env == BASELINE_ENV  # the narrow direction: never a wider list
    assert note == standing.unread


def test_a_file_reached_through_a_link_into_the_project_is_not_read(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "dir").mkdir(parents=True)
    (project / "dir" / "runner.toml").write_text('env = ["GITHUB_TOKEN"]')
    outside = tmp_path / "xdg" / "bh-02"
    outside.mkdir(parents=True)
    (outside / "runner.toml").symlink_to(project / "dir" / "runner.toml")
    standing = allowlist.read(outside / "runner.toml", project)
    assert standing.names == () and standing.unread


def test_a_file_that_can_not_be_used_stops_the_read(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(allowlist.Refused, match="not TOML"):
        allowlist.read(_file(tmp_path, "env = ["), project)
    broken = tmp_path / "xdg" / "bh-02" / "runner.toml"
    broken.write_bytes(b"\xff\xfe")
    with pytest.raises(allowlist.Refused, match="UTF-8"):
        allowlist.read(broken, project)


def test_a_layer_s_env_replaces_the_file_s_and_the_start_says_so() -> None:
    standing = allowlist.Standing(("GITHUB_TOKEN",))
    config, note = allowlist.effective(
        BrigConfig(env=("PATH", "HOME")), standing, file=Path("/c/runner.toml"), readers={}, models_file="m"
    )
    assert config.env == ("PATH", "HOME")
    assert "layer's runner `env` replaced the list in /c/runner.toml" in note
    assert "GITHUB_TOKEN" not in note  # names of the file are not repeated; never values either


def test_a_layer_that_omits_env_takes_the_file_s() -> None:
    standing = allowlist.Standing(("GITHUB_TOKEN",))
    config, note = allowlist.effective(
        BrigConfig(allow=("CLAUDE.md",)), standing, file=Path("/c/runner.toml"), readers={}, models_file="m"
    )
    assert config.env == (*BASELINE_ENV, "GITHUB_TOKEN") and config.allow == ("CLAUDE.md",) and note == ""


def test_a_layer_env_over_an_empty_file_has_nothing_to_say() -> None:
    _, note = allowlist.effective(
        BrigConfig(env=("PATH",)), allowlist.Standing(), file=Path("/c/r.toml"), readers={}, models_file="m"
    )
    assert note == ""


def test_a_name_a_key_reads_is_refused_naming_the_variable_the_endpoint_and_both_files() -> None:
    with pytest.raises(allowlist.Refused) as raised:
        allowlist.effective(
            BrigConfig(),
            allowlist.Standing(("OPENROUTER_API_KEY",)),
            file=Path("/c/runner.toml"),
            readers={"OPENROUTER_API_KEY": ("openrouter",)},
            models_file="/c/models.toml",
        )
    message = str(raised.value)
    assert "OPENROUTER_API_KEY" in message and "'openrouter'" in message
    assert "/c/runner.toml" in message and "/c/models.toml" in message


def test_a_layer_s_env_naming_a_key_is_refused_too() -> None:
    with pytest.raises(allowlist.Refused, match="layer"):
        allowlist.effective(
            BrigConfig(env=("PATH", "OPENROUTER_API_KEY")),
            allowlist.Standing(),
            file=Path("/c/runner.toml"),
            readers={"OPENROUTER_API_KEY": ("openrouter",)},
            models_file="/c/models.toml",
        )


def test_a_file_name_the_layer_replaced_is_not_refused() -> None:
    config, _ = allowlist.effective(
        BrigConfig(env=("PATH",)),
        allowlist.Standing(("OPENROUTER_API_KEY",)),
        file=Path("/c/runner.toml"),
        readers={"OPENROUTER_API_KEY": ("openrouter",)},
        models_file="/c/models.toml",
    )
    assert config.env == ("PATH",)


# Listens on argv[1], so the runner sees it up; writes its environment's names to argv[2].
_LISTEN_AND_LIST = """
import json, os, socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
with open(sys.argv[2], "w") as out:
    json.dump(sorted(os.environ), out)
while True:
    time.sleep(0.1)
"""


@pytest.fixture
def _jailable() -> None:
    if sys.platform not in ("darwin", "linux") or (
        sys.platform == "linux" and not Path("/usr/bin/bwrap").exists()
    ):
        pytest.skip("the confined runner is brig's: darwin, or Linux with /usr/bin/bwrap")


async def _names_in_the_jail(runner: Runner, project: Path) -> list[str]:
    endpoint = str(Path(tempfile.mkdtemp(prefix="bh-k-", dir="/tmp"), "k.sock"))
    seen = project / "env.json"
    started = await runner.start(
        [sys.executable, "-I", "-c", _LISTEN_AND_LIST, endpoint, str(seen)],
        cwd=str(project),
        endpoint=endpoint,
    )
    try:
        for _ in range(200):
            if seen.exists() and seen.read_text().endswith("]"):
                break
            await asyncio.sleep(0.05)
        names: list[str] = json.loads(seen.read_text())
        return names
    finally:
        await started.stop()


async def _runner_of(config: BrigConfig, host: _Host) -> Any:
    effects = await drive(confined(config=config, host=host))
    return effects[0].args[1]


@pytest.mark.usefixtures("_jailable")
async def test_the_jail_holds_the_baseline_and_the_file_s_names_and_a_key_exported_and_not_listed_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the file and no layer: the worker's environment is the baseline (what is set of it)
    plus the file's names; a provider key in the shell that the file does not list is not there."""
    _file(tmp_path, 'env = ["GITHUB_TOKEN"]')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("GITHUB_TOKEN", "stand-in-listed")
    monkeypatch.setenv("OPENROUTER_API_KEY", "stand-in-key")
    monkeypatch.setenv("UNLISTED_THING", "x")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    names = await _names_in_the_jail(await _runner_of(BrigConfig(), _Host()), project)
    assert "GITHUB_TOKEN" in names
    assert "OPENROUTER_API_KEY" not in names and "UNLISTED_THING" not in names
    assert "PATH" in names  # the baseline still passes


@pytest.mark.usefixtures("_jailable")
async def test_with_no_file_the_jail_holds_the_baseline_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    monkeypatch.setenv("GITHUB_TOKEN", "stand-in")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    assert "GITHUB_TOKEN" not in await _names_in_the_jail(await _runner_of(BrigConfig(), _Host()), project)


async def test_a_malformed_file_stops_the_row_before_a_jail_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _file(tmp_path, 'env = ["A"]\nbogus = 1')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "project").mkdir()
    monkeypatch.chdir(tmp_path / "project")
    with pytest.raises(allowlist.Refused, match="bogus"):
        await drive(confined(config=BrigConfig(), host=_Host()))


async def test_a_name_a_key_reads_stops_the_row_at_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _file(tmp_path, 'env = ["OPENROUTER_API_KEY"]')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    host = _Host(key_envs={"OPENROUTER_API_KEY": ("openrouter",)}, models_file="/m/models.toml")
    with pytest.raises(allowlist.Refused, match="OPENROUTER_API_KEY"):
        await drive(confined(config=BrigConfig(), host=host))
