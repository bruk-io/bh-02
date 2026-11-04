"""`models.key_envs()` (TASK-0184): the variables the keys of every endpoint the model row can reach
read, whichever file or `extra` they are in, read fresh each time. The values are stand-ins."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin import Catalog

_KEYED = '[work]\nprovider = "openai"\nbase_url = "http://localhost:1/v1"\nkey = {{ env = "{name}" }}\n'


@dataclass
class _Entry:
    id: str
    use: str | None
    config: dict[str, Any]


class _Loader:
    """The loader's entries: the model row with a config a test changes, as a layer edit does."""

    def __init__(self, config: dict[str, Any], use: str = "models:model") -> None:
        self.config = config
        self.use = use

    def entries(self) -> list[_Entry]:
        return [_Entry("model", self.use, self.config)]


def _file(directory: Path, name: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text)
    return path


def test_the_default_file_the_row_s_own_file_and_its_extra_are_all_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _file(tmp_path / "xdg" / "bh-02", "models.toml", _KEYED.format(name="DEFAULT_KEY"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    loader = _Loader({})
    catalog = Catalog(loader)
    assert catalog.key_envs() == {"DEFAULT_KEY": ("work",)}
    other = _file(tmp_path / "other", "models.toml", _KEYED.format(name="OTHER_KEY"))
    loader.config = {"models": str(other)}  # a layer points the row elsewhere: read at once
    assert catalog.key_envs() == {"OTHER_KEY": ("work",)}
    loader.config = {
        "models": str(other),
        "extra": {
            "added": {"provider": "openai", "base_url": "http://x/v1", "key": {"env": "EXTRA_KEY"}},
            "again": {"provider": "openai", "base_url": "http://y/v1", "key": {"env": "OTHER_KEY"}},
        },
    }
    assert catalog.key_envs() == {"OTHER_KEY": ("work", "again"), "EXTRA_KEY": ("added",)}


def test_an_endpoint_added_to_the_file_counts_at_the_next_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _file(tmp_path / "xdg" / "bh-02", "models.toml", _KEYED.format(name="FIRST_KEY"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    catalog = Catalog(_Loader({}))
    assert catalog.key_envs() == {"FIRST_KEY": ("work",)}
    path.write_text(
        _KEYED.format(name="FIRST_KEY")
        + '[later]\nprovider = "openai"\nbase_url = "http://z/v1"\nkey = { env = "LATER_KEY" }\n'
    )
    assert catalog.key_envs() == {"FIRST_KEY": ("work",), "LATER_KEY": ("later",)}


def test_only_an_env_key_is_a_variable_and_a_file_that_is_not_read_adds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    commanded = _file(
        tmp_path / "c", "models.toml", '[a]\nprovider = "openai"\nkey = { cmd = "print-it" }\n[b]\nkey = 3\n'
    )
    assert Catalog(_Loader({"models": str(commanded)})).key_envs() == {}
    broken = _file(tmp_path / "b", "models.toml", "not [toml")
    extra = {"e": {"provider": "openai", "base_url": "http://x/v1", "key": {"env": "EXTRA_KEY"}}}
    assert Catalog(_Loader({"models": str(broken), "extra": extra})).key_envs() == {"EXTRA_KEY": ("e",)}
    assert Catalog(_Loader({"models": str(tmp_path / "absent.toml")})).key_envs() == {}


def test_a_file_in_the_project_is_not_read_but_the_row_s_extra_still_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    inside = _file(tmp_path, "models.toml", _KEYED.format(name="PROJECT_KEY"))
    extra = {"e": {"provider": "openai", "base_url": "http://x/v1", "key": {"env": "EXTRA_KEY"}}}
    assert Catalog(_Loader({"models": str(inside), "extra": extra})).key_envs() == {"EXTRA_KEY": ("e",)}


def test_a_row_that_is_another_component_has_no_endpoints() -> None:
    assert Catalog(_Loader({}, use="bh_02.testing:echo_model")).key_envs() == {}
