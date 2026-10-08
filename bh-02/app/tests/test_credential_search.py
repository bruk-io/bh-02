"""Where bh-02's credential is looked for, and what no jailed input may read: one list, from the
anchors bh-02 really runs with (its own install and its environment), never a stand-in."""

import importlib.metadata
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import CliRunner

import context_cordis_plugin
import cordis
from bh_02 import main
from bh_02.bootstrap import CREDENTIAL_FILE, code_directories, code_packages, config_directories, unreadable
from bh_02.cli import credential_search
from models_cordis_plugin.local_env import token_file

_WORKSPACE = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class _Layers:
    credentials: tuple[str, ...]


def test_every_path_the_model_row_searches_is_a_secret(tmp_path: Path) -> None:
    """The model rows search exactly the `layers` value's `credentials`, and every one of them is
    among the jail's `secrets` (cli: `unreadable`), so none is a place an input could plant a
    `local.env` for the next launch to hand to Claude Code. Before, the model row anchored on its
    own package and searched four directories of the plugins tree the jail never named."""
    searched = credential_search()
    secrets = unreadable(searched, [tmp_path / CREDENTIAL_FILE], [])
    assert [path for path in searched if path not in secrets] == []
    assert str(_WORKSPACE / CREDENTIAL_FILE) in searched  # the workspace root's, from any directory
    plugins = str(_WORKSPACE / "bh-02" / "plugins")
    assert not any(path.startswith(plugins) for path in searched)  # no plugin's own tree
    assert str(tmp_path / CREDENTIAL_FILE) in secrets and str(tmp_path / CREDENTIAL_FILE) not in searched


def test_the_model_row_reads_only_what_the_layers_value_names(tmp_path: Path) -> None:
    """What a model row finds is a function of the `credentials` it is given and nothing else:
    a `local.env` anywhere else (its own package's tree, the project) is never read."""
    elsewhere = tmp_path / "elsewhere" / CREDENTIAL_FILE
    elsewhere.parent.mkdir()
    elsewhere.write_text("NOT_A_REAL_CREDENTIAL=placeholder\n")  # a stand-in: never the real file
    named = tmp_path / "named" / CREDENTIAL_FILE
    layers = _Layers((str(named),))
    assert token_file(None, layers.credentials) is None
    named.parent.mkdir()
    named.write_text("NOT_A_REAL_CREDENTIAL=placeholder\n")
    assert token_file(None, layers.credentials) == named


def test_the_bh_02_command_boots_with_every_searched_path_among_the_secrets(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launch itself, not only how the lists are built: `bh-02` boots a composition whose
    `layers` value names what the model rows search (`credentials`, exactly `credential_search`)
    and keeps every one of those paths among the jail's `secrets`. A launch that handed either
    side another list would reopen the planted-credential hole (task-0023)."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    seen = tmp_path / "seen.json"
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
        f'[[plugin]]\nid = "probe"\nuse = "fragile:layers_seen"\nconfig = {{ out = "{seen}" }}\n'
    )
    result = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert result.exit_code == 0, result.output
    booted = json.loads(seen.read_text())
    assert booted["credentials"] == list(credential_search())  # what the model rows search
    assert [path for path in booted["credentials"] if path not in booted["secrets"]] == []
    assert str(work / CREDENTIAL_FILE) in booted["secrets"]  # and the project's own, beside it


def test_the_bh_02_command_boots_keeping_inputs_out_of_bh_02_s_config_directories(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launch hands the jail bh-02's config directories (`layers.trusted`): this run's
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
        f'[[plugin]]\nid = "probe"\nuse = "fragile:layers_seen"\nconfig = {{ out = "{seen}" }}\n'
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
    (`layers.code`): its own, cordis's, cordis_helpers's, brig's and each installed plugin's, as
    installed, found by name. With this editable install those are the workspace's `src/<package>`
    directories: the shipped context file is in one (which no input may write when bh-02 works on
    its own checkout), and the extensions' worker imports cordis from another (which a Linux jail
    must let it read). Never the workspace itself, whose `local.env` no input may read."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    seen = tmp_path / "seen.json"
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
        f'[[plugin]]\nid = "probe"\nuse = "fragile:layers_seen"\nconfig = {{ out = "{seen}" }}\n'
    )
    result = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert result.exit_code == 0, result.output
    code = json.loads(seen.read_text())["code"]
    plugins = [ep.module for ep in importlib.metadata.entry_points(group="cordis.plugins")]
    assert code == list(code_directories(code_packages(plugins)))
    packages = code_packages(plugins)
    assert packages[:4] == ("bh_02", "cordis", "cordis_helpers", "brig")
    assert {"context_cordis_plugin", "extensions_cordis_plugin", "kernel_cordis_plugin"} <= set(packages)
    shipped = Path(context_cordis_plugin.__file__).with_name("context.toml")
    assert str(shipped.parent) in code and str(Path(cordis.__file__).parent) in code
    assert all(Path(path).is_dir() for path in code)
    workspace = next((p for p in shipped.parents if (p / "uv.lock").is_file()), None)
    assert workspace is None or str(workspace) not in code  # not where its local.env is


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
    assert code_packages(["kernel_cordis_plugin", "a.b", "cordis", ""]) == (
        "bh_02",
        "cordis",
        "cordis_helpers",
        "brig",
        "kernel_cordis_plugin",
        "a",
    )
