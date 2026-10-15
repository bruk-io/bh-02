"""The models file's `default`: the model a new session starts on when no layer names one.
Lowest first: the file's `default`, a layer's model row `default` (the session's own, which
`/model` and `--model` write); with neither, no model is chosen (there are no built-ins); and the
file's counts only where the file is read (outside the project)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cordis import Row
from cordis.composition import format_layer
from cordis.loader import read_layer
from models_cordis_plugin import (
    Catalog,
    ModelConfig,
    ModelsError,
    Unusable,
    model_list,
    opened,
    parsed,
    resolved,
    set_model,
)

_TABLES = """\
[ollama]
provider = "openai"
base_url = "http://localhost:11434/v1"

[ollama.models.llama]
id = "llama3.2"

[sub]
provider = "claude-code"
models = { sonnet = { id = "sonnet" }, haiku = { id = "haiku" } }
"""


def _file(tmp_path: Path, top: str = 'default = "ollama/llama"\n') -> Path:
    path = tmp_path / "models.toml"
    path.write_text(top + _TABLES)
    return path


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


def _catalog(config: dict[str, Any]) -> Catalog:
    return Catalog(_Loader(_Entry("model", "models:model", config)))


async def test_with_no_file_default_and_no_layer_no_model_is_chosen_and_the_row_says_what_to_write(
    tmp_path: Path,
) -> None:
    config = {"models": str(_file(tmp_path, ""))}
    with pytest.raises(ModelsError) as raised:
        resolved(ModelConfig(**config))
    said = raised.value.message
    assert raised.value.kind == "unknown_model" and said.startswith("no model is chosen")
    assert (
        "the models are ollama/llama, sub/sonnet, sub/haiku; or ENDPOINT/ID" in said
        and 'default = "local/MODEL"' in said
    )
    async with opened(ModelConfig(**config)) as value:
        assert isinstance(value, Unusable) and value.error.message == said
    now = _catalog(config).current()
    assert (now["name"], now["provider"], now["unusable"]) == ("none", "", said)
    assert not any("default" in m for m in _catalog(config).listed())  # no model to mark


def test_the_models_file_default_is_the_model_when_no_layer_names_one(tmp_path: Path) -> None:
    config = {"models": str(_file(tmp_path))}
    assert resolved(ModelConfig(**config)).name == "ollama/llama"
    values = _catalog(config)
    assert values.current() == {"name": "ollama/llama", "provider": "openai"}
    listed = {m["name"]: m for m in values.listed()}
    assert listed["ollama/llama"]["default"] == "the models file" and "default" not in listed["sub/sonnet"]
    assert listed["ollama/llama"]["current"] and not listed["sub/sonnet"]["current"]
    assert values.check("sub/sonnet") is None  # /model still switches away from it
    first = model_list(values.listed(), values.path).splitlines()
    assert first[0].endswith("(default: the models file)") and first[0].startswith("● ollama/llama")
    assert first[1].startswith("  sub/sonnet") and "(default" not in first[1]


def test_a_layer_s_model_beats_the_file_s_default(tmp_path: Path) -> None:
    """None is "no layer named a model"; a model named in a layer is a choice (a resumed session
    that was switched keeps it; `--model` wins)."""
    models = str(_file(tmp_path))
    assert resolved(ModelConfig(models=models, default="sub/haiku")).name == "sub/haiku"
    assert resolved(ModelConfig(models=models, default="sub/sonnet")).name == "sub/sonnet"
    assert _catalog({"models": models, "default": "sub/sonnet"}).current()["name"] == "sub/sonnet"
    shown = {m["name"]: m for m in _catalog({"models": models, "default": "sub/sonnet"}).listed()}
    assert (
        shown["sub/sonnet"]["current"] and shown["ollama/llama"]["default"] == "the models file"
    )  # still the default


@pytest.mark.parametrize("top", ["default = 5\n", 'default = ""\n', 'default = ["llama"]\n'])
async def test_a_file_default_that_is_not_a_name_is_said_and_the_row_still_binds(
    tmp_path: Path, top: str
) -> None:
    config = ModelConfig(models=str(_file(tmp_path, top)))
    with pytest.raises(ModelsError) as raised:
        resolved(config)
    said = raised.value.message
    assert (
        raised.value.kind == "models_file" and f"the default in the models file {config.models} is " in said
    )
    assert 'not a model\'s name; give it one, like `default = "local/llama"`, or remove it' in said
    async with opened(config) as value:
        assert isinstance(value, Unusable) and value.error.message == said


async def test_a_file_default_that_names_no_model_says_what_to_write_and_the_row_still_binds(
    tmp_path: Path,
) -> None:
    config = ModelConfig(models=str(_file(tmp_path, 'default = "gone"\n')))
    with pytest.raises(ModelsError) as raised:
        resolved(config)
    said = raised.value.message
    assert raised.value.kind == "unknown_model"
    assert f"no model named 'gone', the default in the models file {config.models}; the models are" in said
    assert '[NAME]\nprovider = "openai"' in said and "[NAME.models.MODEL]" in said  # what to write
    async with opened(config) as value:
        assert isinstance(value, Unusable)
    values = _catalog({"models": config.models})
    # never raises: the status bar reads it, and says the model can't be used, as the row does
    assert values.current() == {"name": "gone", "provider": "", "unusable": said}
    assert values.check("sub/haiku") is None  # /model another model fixes it
    assert not any("default" in m for m in values.listed())  # no model to mark


def test_a_bad_file_default_is_ignored_while_a_layer_names_a_model(tmp_path: Path) -> None:
    config = ModelConfig(models=str(_file(tmp_path, "default = 5\n")), default="sub/haiku")
    assert resolved(config).name == "sub/haiku"


def test_a_file_that_cannot_be_read_still_gives_the_status_bar_a_name(tmp_path: Path) -> None:
    """Its default is unknown, so with no layer's choice the model is `default` and unusable (the
    row says the file's problem); a layer's choice of a model in the row's `extra` runs."""
    path = tmp_path / "models.toml"
    path.write_text("default = [\n")
    now = _catalog({"models": str(path)}).current()
    assert (now["name"], now["provider"]) == ("default", "") and "is not TOML" in now["unusable"]
    extra = {"sub": {"provider": "claude-code", "models": {"haiku": {"id": "haiku"}}}}
    assert _catalog({"models": str(path), "default": "sub/haiku", "extra": extra}).current() == {
        "name": "sub/haiku",
        "provider": "claude-code",
    }


def test_the_default_key_is_a_setting_but_a_default_table_is_an_endpoint() -> None:
    assert parsed('default = "x"\n', "f").default == "x"
    both = parsed('[default]\nprovider = "claude-code"\nmodels.opus.id = "opus"\n', "f")
    assert both.default is None and set(both.endpoints) == {"default"}
    with pytest.raises(ModelsError, match="'other' is not a table"):
        parsed('other = "x"\n', "f")


def test_a_default_in_a_models_file_in_the_project_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default chooses the spend: a file the model could write does not choose it."""
    project = tmp_path / "project"
    (project / ".config" / "bh-02").mkdir(parents=True)
    (project / ".config" / "bh-02" / "models.toml").write_text('default = "sub/opus"\n' + _TABLES)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(project / ".config"))
    config = {"cwd": str(project)}
    with pytest.raises(ModelsError) as raised:
        resolved(ModelConfig(**config))
    assert raised.value.message.startswith("no model is chosen")  # the file's default is not read
    assert "is not read: it is in the project" in raised.value.message
    values = _catalog(config)
    assert values.current()["name"] == "none" and values.problem is not None
    assert values.listed() == []


def test_what_model_and_the_switch_write_in_the_session_s_layer_wins_over_the_file(tmp_path: Path) -> None:
    """The session's layer starts with the model row's `state` alone (no `default`: the file's
    counts); `/model NAME` (`set_model`, as `--model` does with `with_model`) names one, which a
    resume of that layer then keeps."""
    layer = tmp_path / "session.toml"
    layer.write_text(format_layer([Row("model", config={"state": "/s/claude"})], "x"))
    models = str(_file(tmp_path))

    def model_row() -> ModelConfig:
        (row,) = [r for r in read_layer(str(layer)) if r.id == "model"]
        return ModelConfig(models=models, **(row.config or {}))

    assert resolved(model_row()).name == "ollama/llama"  # no --model, no /model: the models file's default
    set_model(str(layer), "model", "sub/haiku")
    assert resolved(model_row()).name == "sub/haiku" and model_row().state == "/s/claude"
    set_model(str(layer), "model", "sub/sonnet")
    assert resolved(model_row()).name == "sub/sonnet"  # each switch is a choice the layer keeps
