"""An endpoint with `discover = true`: what is wrong with one, and how `ENDPOINT/ID` means a model
with no network (`find`, `chosen`, `resolved`): pure but for reading the file."""

from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin import (
    ModelConfig,
    ModelsError,
    Named,
    chosen,
    combined,
    opened,
    parsed,
    problem,
    resolved,
)
from models_cordis_plugin.named import derived, find, not_a_model

_FILE = """\
[ollama]
provider = "openai"
base_url = "http://localhost:11434/v1"
models.llama.id = "llama3.2"

[local]
provider = "openai"
discover = true
base_url = "http://localhost:1234/v1"
key = { env = "LOCAL_KEY" }
max_tokens = 2048
temperature = 0.1
include = ["qwen*"]
"""


def _models(extra: dict[str, Any] | None = None, text: str = _FILE) -> list[Named]:
    return combined(parsed(text, "/c/models.toml").endpoints, "/c/models.toml", extra or {})


def _table(**table: Any) -> Named:
    """The endpoint `[x]` of the models file `/c/m.toml`, an openai one with a base_url and `table`."""
    return combined({"x": {"provider": "openai", "base_url": "http://h/v1", **table}}, "/c/m.toml", {})[-1]


def test_an_endpoint_that_discovers_needs_no_models_of_its_own_and_is_no_model() -> None:
    (ollama, local) = _models()
    assert local.endpoint and ollama.endpoint
    assert problem(local) is None  # no models: it lists its server's
    assert not_a_model(local) is not None
    assert "is an endpoint, which serves models and is none itself" in str(not_a_model(local))
    assert "name one of them, local/MODEL: /model lists them" in str(not_a_model(local))
    llama = find("ollama/llama", _models())
    assert llama is not None and not llama.endpoint and not_a_model(llama) is None


@pytest.mark.parametrize(
    ("table", "said"),
    [
        ({"discover": "yes"}, "discover must be true or false"),
        (
            {"models": {"m": {"id": "x"}}, "include": ["a*"]},
            "include narrows the models an endpoint's server lists; add `discover = true`",
        ),
        ({"discover": False, "models": {"m": {"id": "x"}}, "include": ["a*"]}, "add `discover = true`"),
        ({"discover": True, "colour": "red"}, "colour is not a setting of an openai endpoint; it takes"),
        (
            {"discover": True, "include": "qwen*"},
            'include must be a list of patterns, like `include = ["qwen*"]`',
        ),
        ({"discover": True, "include": []}, "include must be a list of patterns"),
        ({"discover": True, "include": ["a", ""]}, "include must be a list of patterns"),
        ({"discover": True, "include": ["a", 5]}, "include must be a list of patterns"),
        ({"discover": True, "base_url": "ftp://h"}, "is not an http(s) URL"),
    ],
)
def test_a_table_that_discovers_wrongly_is_that_table_s_problem(table: dict[str, Any], said: str) -> None:
    named = _table(**table)
    assert said in str(problem(named))
    assert str(problem(named)).startswith("endpoint 'x' (/c/m.toml)")


def test_an_endpoint_with_models_may_say_discover_is_false() -> None:
    named = _table(discover=False, models={"m": {"id": "x"}})
    assert problem(named) is None and named.endpoint


def test_an_endpoint_with_neither_models_nor_discover_says_to_give_it_one() -> None:
    assert "names no models" in str(problem(_table(discover=False)))


def test_an_endpoint_s_name_may_not_hold_a_slash() -> None:
    (named,) = combined(
        {"a/b": {"provider": "openai", "discover": True, "base_url": "http://h/v1"}}, "/c/m", {}
    )
    assert "an endpoint's name may not hold '/'" in str(problem(named))


def test_a_claude_code_table_does_not_discover() -> None:
    (named,) = combined(
        {"x": {"provider": "claude-code", "models": {"o": {"id": "opus"}}, "discover": True}}, "/c/m", {}
    )
    assert "discover is not a setting of a claude-code endpoint" in str(problem(named))


def test_discover_in_the_row_s_extra_says_the_file_alone_has_it_and_names_no_model() -> None:
    models = _models(extra={"far": {"provider": "openai", "discover": True, "base_url": "http://h/v1"}})
    far = models[-1]
    assert far.endpoint and far.source == "the model row's extra"
    assert "discover is read only from the models file, never from a layer" in str(problem(far))
    found = find("far/x", models)  # its table has a problem: the endpoint comes back, refused
    assert found is far and not_a_model(far) == problem(far)


def test_a_name_is_split_at_the_first_slash_and_the_id_keeps_the_rest() -> None:
    models = _models()
    for rest in ("qwen2.5-coder:7b", "Qwen/Qwen2.5-Coder:7b", "/models/x.gguf", "a/b/c", "x@y", "q4_k_m"):
        found = find(f"local/{rest}", models)
        assert found is not None and found.id == rest and found.name == f"local/{rest}"
        assert found.provider == "openai" and found.source == "/c/models.toml" and not found.endpoint
    assert find("local/", models) is None  # no id
    host = find("local", models)  # the endpoint itself, which is none of its models
    assert host is not None and host.endpoint
    assert find("nowhere/x", models) is None
    assert find("sonnet/x", models) is None  # no endpoint of that name: there are no built-ins either
    assert find(5, models) is None  # a layer's default may be anything


def test_a_derived_model_has_the_endpoint_s_table_but_for_discover_include_and_its_id() -> None:
    (local,) = [n for n in _models() if n.name == "local"]
    named = derived(local, "x:7b")
    assert named.table == {
        "provider": "openai",
        "base_url": "http://localhost:1234/v1",
        "key": {"env": "LOCAL_KEY"},
        "max_tokens": 2048,
        "temperature": 0.1,
        "id": "x:7b",
    }
    assert problem(named) is None and not_a_model(named) is None


def test_a_model_the_endpoint_names_wins_over_the_same_name_as_an_id() -> None:
    models = _models(text=_FILE + '\n[local.models.special]\nid = "other"\nmax_tokens = 99\n')
    found = find("local/special", models)
    assert found is not None and (found.id, found.table["max_tokens"]) == ("other", 99)  # its own table
    other = find("local/not-special", models)
    assert other is not None and (other.id, other.table["max_tokens"]) == ("not-special", 2048)


def test_chosen_resolves_an_endpoint_model_and_says_what_an_endpoint_alone_is() -> None:
    models = _models()
    got = chosen("local/qwen2.5-coder:7b", models, "/c/models.toml")
    assert (got.provider, got.id) == ("openai", "qwen2.5-coder:7b")
    with pytest.raises(ModelsError, match="is an endpoint, which serves models and is none itself") as raised:
        chosen("local", models, "/c/models.toml")
    assert raised.value.kind == "model_config"


def test_a_name_that_is_nothing_lists_the_models_and_the_endpoints_whose_models_are_named_by_id() -> None:
    with pytest.raises(ModelsError) as raised:
        chosen("gone", _models(), "/c/models.toml")
    said = raised.value.message
    assert "the models are ollama/llama; or ENDPOINT/ID, an id on an endpoint " in said
    assert "(ollama, local)." in said
    with pytest.raises(ModelsError) as bare:
        chosen("local/", _models(), "/c/models.toml")
    assert bare.value.kind == "unknown_model"


@pytest.mark.parametrize(
    ("table", "said"),
    [
        ({"colour": "red"}, "colour is not a setting of an openai endpoint; it takes"),
        ({"include": "qwen*"}, 'include must be a list of patterns, like `include = ["qwen*"]`'),
        ({"include": []}, "include must be a list of patterns"),
        ({"base_url": "localhost:1234"}, "base_url 'localhost:1234' is not an http(s) URL with a host"),
        ({"max_tokens": 0}, "max_tokens must be a whole number above 0"),
    ],
)
def test_an_endpoint_whose_table_has_a_problem_names_no_model_and_says_that_problem(
    table: dict[str, Any], said: str
) -> None:
    """TASK-0095: the table is broken, so what is derived from it is too: `local/x` is refused with the
    endpoint's own problem (which says what to write), not resolved through a table bh-02 calls broken."""
    sound = {"provider": "openai", "discover": True, "base_url": "http://localhost:1234/v1"}
    models = combined({"local": {**sound, **table}}, "/c/models.toml", {})
    host = models[-1]
    why = problem(host)
    assert why is not None and said in why and why.startswith("endpoint 'local' (/c/models.toml)")
    assert derived(host, "x:7b") is host  # no model is derived from it: the table to fix is the one named
    for name in ("local/x:7b", "local/Qwen/q", "local"):  # a model of it, and the endpoint itself
        found = find(name, models)
        assert found is not None and not_a_model(found) == why
        with pytest.raises(ModelsError) as raised:
            chosen(name, models, "/c/models.toml")
        assert raised.value.kind == "model_config" and raised.value.message == why


async def test_the_model_row_resolves_a_layer_s_default_of_an_endpoint_model_and_binds_it(
    tmp_path: Path,
) -> None:
    file = tmp_path / "models.toml"
    file.write_text(_FILE)
    config = ModelConfig(default="local/Qwen/q:7b", models=str(file))
    named = resolved(config)
    assert (named.name, named.id) == ("local/Qwen/q:7b", "Qwen/q:7b")
    async with opened(config) as bound:
        assert type(bound).__name__ == "OpenAIModel"  # the endpoint's own provider, entered
