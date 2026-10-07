"""Where bh-02's credential is looked for, and what no jailed input may read: one list, from the
anchors bh-02 really runs with (its own install and its environment), never a stand-in."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import CliRunner

from bh_02 import main
from bh_02.bootstrap import CREDENTIAL_FILE, unreadable
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
