"""What the models file is trusted with, and where that stops: a models file in the project
(which the model's code can write) is not read, however it got there, and is said to be where
the file's problems are said; an `openai` model's key never names the Claude Code token."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin import (
    Catalog,
    ModelConfig,
    ModelsError,
    Named,
    Unusable,
    chosen,
    combined,
    in_project,
    opened,
    problem,
    resolved,
)
from models_cordis_plugin.openai import OpenAIModel, authorization
from models_cordis_plugin.openai.testing import StubServer

_FILE = """\
[llama]
provider = "openai"
id = "llama3.2"
base_url = "http://localhost:11434/v1"

[sonnet]
provider = "openai"
id = "not-claude"
base_url = "https://example.com/v1"
"""
_REFUSED = "is not read: it is in the project"
_WHERE = "Keep your models file outside the project, and not a link into it"


@pytest.fixture
def places(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A project, a home outside it, and a third directory outside both."""
    project, home, elsewhere = tmp_path / "project", tmp_path / "home", tmp_path / "elsewhere"
    for place in (project, home, elsewhere):
        place.mkdir()
    return project, home, elsewhere


def _models(path: Path, text: str = _FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_a_models_file_in_the_project_as_named_is_refused_saying_where_it_must_be(
    places: tuple[Path, Path, Path],
) -> None:
    project, _, _ = places
    path = _models(project / "cfg" / "bh-02" / "models.toml")
    said = str(in_project(path, project))
    assert said.startswith(f"the models file {path} {_REFUSED} ({project}), which the model's code can write")
    assert (
        _WHERE in said and "set XDG_CONFIG_HOME (or the model row's `models`) to a directory outside" in said
    )
    absent = project / "nothing-here.toml"
    assert in_project(absent, project) is not None  # there or not: the model could write one


def test_a_models_file_outside_the_project_is_read(places: tuple[Path, Path, Path]) -> None:
    project, home, elsewhere = places
    path = _models(home / ".config" / "bh-02" / "models.toml")
    assert in_project(path, project) is None
    assert in_project(path, project / "sub") is None
    dotfiles = home / "dotfiles.toml"
    dotfiles.symlink_to(_models(elsewhere / "models.toml"))  # a link that stays outside: read
    assert in_project(dotfiles, project) is None


def test_a_link_into_the_project_is_refused_as_its_links_lead(places: tuple[Path, Path, Path]) -> None:
    project, home, elsewhere = places
    real = _models(project / "models.toml")
    linked = home / ".config" / "bh-02" / "models.toml"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(real)  # the file itself a link into the project
    assert f"{_REFUSED} ({project}) as its links lead ({real})" in str(in_project(linked, project))
    relative = home / "relative.toml"
    relative.symlink_to(Path("..") / "project" / "models.toml")  # a relative link, followed
    assert in_project(relative, project) is not None
    config = elsewhere / "config"
    config.symlink_to(project / "cfg", target_is_directory=True)  # a directory on its path a link into it
    _models(project / "cfg" / "bh-02" / "models.toml")
    assert in_project(config / "bh-02" / "models.toml", project) is not None


def test_a_link_in_the_project_on_the_way_out_of_it_is_refused(places: tuple[Path, Path, Path]) -> None:
    """The model can repoint a link in the project, or swap a directory there for one, so a
    file whose way passes through the project is the model's to choose, wherever it ends."""
    project, home, elsewhere = places
    outside = _models(elsewhere / "models.toml")
    (project / "cfg").mkdir()
    (project / "cfg" / "models.toml").symlink_to(outside)
    (home / "bh-02").symlink_to(project / "cfg", target_is_directory=True)
    said = str(in_project(home / "bh-02" / "models.toml", project))
    assert f"as its links lead ({project / 'cfg' / 'models.toml'})" in said


def test_the_project_counts_as_named_and_as_resolved(places: tuple[Path, Path, Path]) -> None:
    project, _, elsewhere = places
    alias = elsewhere / "alias"
    alias.symlink_to(project, target_is_directory=True)
    path = _models(project / "models.toml")
    assert in_project(path, alias) is not None  # the root named through a link
    assert in_project(alias / "models.toml", project) is not None  # the file named through one


def test_a_loop_of_links_ends_and_is_left_to_reading_to_say(places: tuple[Path, Path, Path]) -> None:
    project, home, _ = places
    (home / "a").symlink_to(home / "b")
    (home / "b").symlink_to(home / "a")
    assert in_project(home / "a" / "models.toml", project) is None  # outside; reading it fails, said


@dataclass
class _Entry:
    id: str
    use: str | None
    config: dict[str, Any]


class _Loader:
    def __init__(self, *entries: _Entry) -> None:
        self.now = list(entries)

    def entries(self) -> list[_Entry]:
        return self.now


_EXTRA = {"mine": {"provider": "openai", "id": "qwen3", "base_url": "http://gpu:11434/v1"}}


async def test_xdg_config_home_in_the_project_leaves_the_built_ins_and_extra_and_says_why(
    places: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _, _ = places
    monkeypatch.setenv("XDG_CONFIG_HOME", str(project / ".config"))
    path = _models(project / ".config" / "bh-02" / "models.toml")
    config = {"cwd": str(project), "extra": _EXTRA}
    values = Catalog(_Loader(_Entry("model", "models:model", config)))
    listed = {m["name"]: m for m in values.listed()}
    assert list(listed) == ["sonnet", "opus", "haiku", "mine"]  # not llama, and sonnet is the built-in
    assert listed["sonnet"]["provider"] == "claude-code" and "shadows" not in listed["sonnet"]
    assert str(values.problem).startswith(f"the models file {path} {_REFUSED} ({project})")
    assert values.check("haiku") is None and values.check("mine") is None
    assert str(values.check("llama")) == (
        f"no model named 'llama'; the models are sonnet, opus, haiku, mine; {values.problem}"
    )
    assert resolved(ModelConfig(**config)).provider == "claude-code"  # sonnet, built in
    assert resolved(ModelConfig(default="mine", **config)).id == "qwen3"  # the row's extra
    with pytest.raises(ModelsError) as raised:
        resolved(ModelConfig(default="llama", **config))
    assert raised.value.kind == "unknown_model" and str(values.problem) in raised.value.message
    async with opened(ModelConfig(default="llama", **config)) as value:  # binds, and each step says why
        assert isinstance(value, Unusable) and _REFUSED in value.error.message


def test_run_from_home_the_default_models_file_is_in_the_project(
    places: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """bh-02 started in the home directory: the project is the home, `~/.config` in it."""
    _, home, _ = places
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(home)  # no `cwd`: the working directory is the project
    _models(home / ".config" / "bh-02" / "models.toml")
    values = Catalog(_Loader(_Entry("model", "models:model", {})))
    assert [m["name"] for m in values.listed()] == ["sonnet", "opus", "haiku"]
    assert _REFUSED in str(values.problem)


def test_the_working_directory_counts_even_when_the_row_s_cwd_names_another(
    places: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The jail lets the model write in the working directory (the kernel's root), whatever
    project a layer tells Claude Code it works in."""
    project, _, elsewhere = places
    monkeypatch.setenv("XDG_CONFIG_HOME", str(project / ".config"))
    monkeypatch.chdir(project)
    _models(project / ".config" / "bh-02" / "models.toml")
    values = Catalog(_Loader(_Entry("model", "models:model", {"cwd": str(elsewhere)})))
    assert _REFUSED in str(values.problem) and "llama" not in [m["name"] for m in values.listed()]


def test_a_models_file_outside_the_project_is_read_and_has_no_problem(
    places: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, home, _ = places
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    _models(home / ".config" / "bh-02" / "models.toml")
    values = Catalog(_Loader(_Entry("model", "models:model", {"cwd": str(project)})))
    assert values.problem is None and "llama" in [m["name"] for m in values.listed()]
    assert resolved(ModelConfig(default="llama", cwd=str(project))).provider == "openai"


def _keyed(key: str) -> Named:
    table = {"provider": "openai", "id": "x", "base_url": "https://h/v1", "key": key}
    (named,) = [m for m in combined({"m": table}, "/c/models.toml", {}) if m.name == "m"]
    return named


async def test_a_key_naming_the_claude_code_token_is_refused_and_never_sent(tmp_path: Path) -> None:
    env = tmp_path / "local.env"
    env.write_text("CLAUDE_CODE_OAUTH_TOKEN=fake-token-for-tests\nOTHER_KEY=fake-other\n")
    named = _keyed("CLAUDE_CODE_OAUTH_TOKEN")
    said = str(problem(named))
    assert said.startswith("model 'm' (/c/models.toml): key may not name CLAUDE_CODE_OAUTH_TOKEN")
    assert "the Claude Code CLI alone" in said and "fake-token-for-tests" not in said
    with pytest.raises(ModelsError) as raised:
        chosen("m", [named], "/c/models.toml")
    assert raised.value.kind == "model_config"
    with pytest.raises(ModelsError) as sent:  # the last wall, at the request itself
        authorization(named, str(env))
    assert sent.value.kind == "model_config" and "fake-token-for-tests" not in sent.value.message
    with StubServer() as stub:
        table = {**named.table, "base_url": stub.base_url}
        async with OpenAIModel(Named("m", "openai", "x", table, "/c/models.toml"), str(env)) as model:
            with pytest.raises(ModelsError):
                async for _ in model.complete([{"role": "user", "content": "hi"}], []):
                    pass
    assert stub.requests == []  # nothing reached the server
    assert problem(_keyed("OTHER_KEY")) is None  # another line is the endpoint's own
