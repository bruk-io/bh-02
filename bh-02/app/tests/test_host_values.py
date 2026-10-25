"""What the launch hands the jail as the `host` value: the sessions' state it may not read, bh-02's
configuration it may not write, and the directories bh-02 runs its own code from."""

import importlib.metadata
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner

import cordis
import memory_cordis_plugin
from bh_02 import main
from bh_02.bootstrap import code_directories, code_packages, config_directories


def test_the_bh_02_command_boots_keeping_inputs_from_reading_the_sessions_state(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launch hands the jail what no input may read (`host.secrets`): the sessions' state
    directories, this run's and the default one, where each session's Claude Code child keeps its
    config and messaging peer token. Bh-02 reads no credential file, so there is no other secret."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    seen = tmp_path / "seen.json"
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
        f'[[plugin]]\nid = "probe"\nuse = "fragile:host_seen"\nconfig = {{ out = "{seen}" }}\n'
    )
    result = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert result.exit_code == 0, result.output
    booted = json.loads(seen.read_text())
    assert "credentials" not in booted
    state = Path(os.environ["XDG_STATE_HOME"]).resolve()
    assert Path(booted["secrets"][0]).is_relative_to(state)  # this run's state
    assert booted["secrets"] == list(dict.fromkeys(booted["secrets"]))  # each once


def test_the_bh_02_command_boots_keeping_inputs_out_of_bh_02_s_config_directories(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launch hands the jail bh-02's config directories (`host.trusted`): this run's
    (`$XDG_CONFIG_HOME/bh-02`) and the default one, each as named and as it resolves, so a
    session run from the home directory can't rewrite what a later one reads and trusts there."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    linked = tmp_path / "dotfiles"
    (linked / "bh-02").mkdir(parents=True)
    (tmp_path / "xdg").symlink_to(linked)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    seen = tmp_path / "seen.json"
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
        f'[[plugin]]\nid = "probe"\nuse = "fragile:host_seen"\nconfig = {{ out = "{seen}" }}\n'
    )
    result = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert result.exit_code == 0, result.output
    trusted = json.loads(seen.read_text())["trusted"]
    assert trusted == list(config_directories(os.environ, Path.home()))
    default = Path.home() / ".config" / "bh-02"
    assert trusted[:2] == [str(tmp_path / "xdg" / "bh-02"), str(linked.resolve() / "bh-02")]
    assert str(default) in trusted  # what a run without the variable reads


def test_the_bh_02_command_boots_handing_the_jail_the_directories_bh_02_runs_code_from(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launch hands the jail the directory of every package bh-02 runs code from
    (`host.code`): its own, cordis's, cordis_helpers's, brig's and each installed plugin's, as
    installed, found by name. With this editable install those are the workspace's `src/<package>`
    directories, whose modules bh-02 imports (which no input may write when bh-02 works on its own
    checkout), and the extensions process imports cordis from one (which a Linux jail must let it
    read). Never the workspace itself, whose files no input may read."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    seen = tmp_path / "seen.json"
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
        f'[[plugin]]\nid = "probe"\nuse = "fragile:host_seen"\nconfig = {{ out = "{seen}" }}\n'
    )
    result = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert result.exit_code == 0, result.output
    code = json.loads(seen.read_text())["code"]
    plugins = [ep.module for ep in importlib.metadata.entry_points(group="cordis.plugins")]
    assert code == list(code_directories(code_packages(plugins)))
    packages = code_packages(plugins)
    assert packages[:5] == ("bh_02", "cordis", "cordis_helpers", "brig", "host_paths")
    assert {"memory_cordis_plugin", "extensions_cordis_plugin", "python_cordis_plugin"} <= set(packages)
    shipped = Path(memory_cordis_plugin.__file__).with_name("memory.py")
    assert str(shipped.parent) in code and str(Path(cordis.__file__).parent) in code
    assert all(Path(path).is_dir() for path in code)
    workspace = next((p for p in shipped.parents if (p / "uv.lock").is_file()), None)
    assert workspace is None or str(workspace) not in code  # not the workspace itself


def test_a_package_s_code_is_where_it_is_installed_as_named_and_as_it_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found by name, as installed (an import hook's, a `.pth` file's or site-packages'), never
    imported: a package's directories, a single module's file, a name not installed left out;
    and each as named and as it resolves (a workspace reached through a link)."""
    real = tmp_path / "real"
    (real / "pkg_for_code_dirs").mkdir(parents=True)
    (real / "pkg_for_code_dirs" / "__init__.py").write_text("raise RuntimeError('imported')\n")
    (real / "mod_for_code_dirs.py").write_text("raise RuntimeError('imported')\n")
    (tmp_path / "linked").symlink_to(real)
    named = tmp_path / "linked"
    monkeypatch.syspath_prepend(str(named))
    found = code_directories(["pkg_for_code_dirs", "mod_for_code_dirs", "no_such_package_here"])
    assert found == (
        str(named / "pkg_for_code_dirs"),
        str(real.resolve() / "pkg_for_code_dirs"),
        str(named / "mod_for_code_dirs.py"),
        str(real.resolve() / "mod_for_code_dirs.py"),
    )
    assert "pkg_for_code_dirs" not in sys.modules and "mod_for_code_dirs" not in sys.modules
    assert code_packages(["python_cordis_plugin", "a.b", "cordis", ""]) == (
        "bh_02",
        "cordis",
        "cordis_helpers",
        "brig",
        "host_paths",
        "python_cordis_plugin",
        "a",
    )
