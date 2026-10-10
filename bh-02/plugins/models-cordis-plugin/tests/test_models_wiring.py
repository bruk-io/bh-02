"""The rows driven by hand: the model row binds its named model's provider, entered, and starts
nothing; one it can't use still binds, saying why at each step; the catalog binds `models`."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cordis.testing import drive
from models_cordis_plugin import Catalog, CatalogConfig, ModelConfig, ModelsError, Unusable, catalog, model
from models_cordis_plugin.claude_code import ClaudeCodeError, ClaudeCodeModel
from models_cordis_plugin.openai import OpenAIModel


@dataclass(frozen=True)
class _Host:
    """The `host` value, as far as the model rows read it: where `local.env` is looked for."""

    credentials: tuple[str, ...] = ()


@pytest.fixture(autouse=True)
def _own_models_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


async def _bound(config: ModelConfig) -> Any:
    """What the row binds under `model`, entered as the runtime would enter it."""
    first = await drive(model(config=config, host=_Host()))
    manager = first[0].args[0]  # the provider's value, to be entered
    entered = await manager.__aenter__()
    effects = await drive(
        model(config=config, host=_Host()), [entered]
    )  # the runtime sends back what it entered
    assert [e.name for e in effects] == ["enter", "bind"] and effects[1].args[0] == "model"
    assert effects[1].args[1] is entered
    return entered, manager


async def test_the_default_is_sonnet_on_claude_code_and_the_credential_is_read_at_the_first_step(
    tmp_path: Path,
) -> None:
    config = ModelConfig(state=str(tmp_path / "state"), env_file=str(tmp_path / "missing.env"))
    bound, manager = await _bound(config)
    assert isinstance(bound, ClaudeCodeModel)  # an async context manager: left with the row
    with pytest.raises(ClaudeCodeError, match="missing.env"):
        async for _ in bound.complete([{"role": "user", "content": "hi"}], []):
            pass
    await manager.__aexit__(None, None, None)


async def test_a_model_from_the_models_file_on_an_openai_endpoint(tmp_path: Path) -> None:
    models = tmp_path / "models.toml"
    models.write_text('[local]\nprovider = "openai"\nid = "llama3.2"\nbase_url = "http://127.0.0.1:9/v1"\n')
    bound, manager = await _bound(ModelConfig(default="local", models=str(models)))
    assert isinstance(bound, OpenAIModel)
    await manager.__aexit__(None, None, None)


@pytest.mark.parametrize(
    ("config", "said"),
    [
        (ModelConfig(default="gpt-9"), "no model named 'gpt-9'"),
        (
            ModelConfig(default="x", extra={"x": {"id": "y"}}),
            "model 'x' (the model row's extra) names no provider",
        ),
        (
            ModelConfig(
                default="x", extra={"x": {"provider": "openai", "id": "y", "base_url": "localhost:1"}}
            ),
            "base_url 'localhost:1' is not an http(s) URL",
        ),
        (
            ModelConfig(default="x", extra={"x": {"provider": "nope.module:thing"}}),
            "names the provider 'nope.module:thing', which can't be loaded",
        ),
        (
            ModelConfig(default="x", extra={"x": {"provider": f"{__name__}:_failing", "id": "y"}}),
            f"its provider '{__name__}:_failing' failed to make the model (TypeError: no id y)",
        ),
    ],
)
async def test_a_model_that_can_t_be_used_still_binds_and_each_step_says_why(
    config: ModelConfig, said: str
) -> None:
    bound, manager = await _bound(config)
    assert isinstance(bound, Unusable)
    for _ in range(2):  # every step, not only the first
        with pytest.raises(ModelsError) as raised:
            async for _ in bound.complete([{"role": "user", "content": "hi"}], []):
                pass
        assert said in raised.value.message
    await manager.__aexit__(None, None, None)


async def test_a_factory_provider_is_given_the_model_s_table() -> None:
    config = ModelConfig(default="fake", extra={"fake": {"provider": f"{__name__}:_factory", "id": "f1"}})
    bound, manager = await _bound(config)
    assert bound == {"provider": f"{__name__}:_factory", "id": "f1"}
    await manager.__aexit__(None, None, None)


def _factory(table: Any) -> Any:
    return dict(table)


def _failing(table: Any) -> Any:
    raise TypeError(f"no id {table['id']}")


@dataclass
class _Entry:
    id: str
    use: str | None
    config: dict[str, Any]


class _Loader:
    def entries(self) -> list[_Entry]:
        return [_Entry("model", "models:model", {"default": "haiku"})]


async def test_the_catalog_row_binds_the_models_over_the_loader() -> None:
    effects = await drive(catalog(loader=_Loader(), host=_Host(), config=CatalogConfig()))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "models")]
    bound = effects[0].args[1]
    assert isinstance(bound, Catalog) and bound.current() == {"name": "haiku", "provider": "claude-code"}
