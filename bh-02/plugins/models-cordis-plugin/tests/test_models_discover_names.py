"""A table with `discover = true` is an endpoint: what is wrong with one, and how `ENDPOINT/ID`
means a model with no network (`find`, `chosen`, `resolved`): pure but for reading the file."""

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
from models_cordis_plugin.named import derived, endpoint, find, not_a_model

_FILE = """\
[llama]
provider = "openai"
id = "llama3.2"
base_url = "http://localhost:11434/v1"

[local]
provider = "openai"
discover = true
base_url = "http://localhost:1234/v1"
key = "LOCAL_KEY"
max_tokens = 2048
temperature = 0.1
include = ["qwen*"]
"""


def _models(extra: dict[str, Any] | None = None, text: str = _FILE) -> list[Named]:
    return combined(parsed(text, "/c/models.toml").models, "/c/models.toml", extra or {})


def _table(**table: Any) -> Named:
    """The table `[x]` of the models file `/c/m.toml`, an openai one with a base_url and `table`."""
    return combined({"x": {"provider": "openai", "base_url": "http://h/v1", **table}}, "/c/m.toml", {})[-1]


def test_a_table_with_discover_is_an_endpoint_with_no_id_and_is_no_model() -> None:
    (llama, local) = _models()[3:]
    assert endpoint(local) and not endpoint(llama)
    assert problem(local) is None  # no id: it lists its models
    assert not_a_model(local) is not None
    assert "is an endpoint, which lists models and is none itself" in str(not_a_model(local))
    assert "name one of them, local/ID: /model lists them" in str(not_a_model(local))
    assert not_a_model(llama) is None


@pytest.mark.parametrize(
    ("table", "said"),
    [
        ({"discover": "yes"}, "discover must be true or false"),
        (
            {"id": "x", "include": ["a*"]},
            "include narrows the models an endpoint lists; add `discover = true`",
        ),
        ({"discover": False, "id": "x", "include": ["a*"]}, "add `discover = true`"),
        ({"discover": True, "id": "x"}, "an endpoint names no id, it lists its models (named x/ID)"),
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
    assert str(problem(named)).startswith("model 'x' (/c/m.toml)")


def test_a_single_model_table_may_say_discover_is_false() -> None:
    named = _table(discover=False, id="x")
    assert problem(named) is None and not endpoint(named)


def test_an_endpoint_s_name_may_not_hold_a_slash() -> None:
    (named,) = combined(
        {"a/b": {"provider": "openai", "discover": True, "base_url": "http://h/v1"}}, "/c/m", {}
    )[3:]
    assert "an endpoint's name may not hold '/'" in str(problem(named))


def test_a_claude_code_table_does_not_discover() -> None:
    (named,) = combined({"x": {"provider": "claude-code", "id": "opus", "discover": True}}, "/c/m", {})[3:]
    assert "discover is not a setting of a claude-code model" in str(problem(named))


def test_discover_in_the_row_s_extra_is_no_endpoint_and_says_the_file_alone_has_them() -> None:
    models = _models(extra={"far": {"provider": "openai", "discover": True, "base_url": "http://h/v1"}})
    far = models[-1]
    assert not endpoint(far)  # so nothing is ever asked for it
    assert "discover is read only from the models file, never from a layer" in str(problem(far))
    assert find("far/x", models) is None  # and it names no models


def test_a_name_is_split_at_the_first_slash_and_the_id_keeps_the_rest() -> None:
    models = _models()
    for rest in ("qwen2.5-coder:7b", "Qwen/Qwen2.5-Coder:7b", "/models/x.gguf", "a/b/c", "x@y", "q4_k_m"):
        found = find(f"local/{rest}", models)
        assert found is not None and found.id == rest and found.name == f"local/{rest}"
        assert found.provider == "openai" and found.source == "/c/models.toml" and not found.shadows
    assert find("local/", models) is None  # no id
    host = find("local", models)  # the endpoint itself, which is none of its models
    assert host is not None and endpoint(host)
    assert find("nowhere/x", models) is None
    assert find("llama/x", models) is None  # a plain model lists nothing
    assert find(5, models) is None  # a layer's default may be anything


def test_a_derived_model_has_the_endpoint_s_table_but_for_discover_include_and_id() -> None:
    (local,) = [n for n in _models() if n.name == "local"]
    named = derived(local, "x:7b")
    assert named.table == {
        "provider": "openai",
        "base_url": "http://localhost:1234/v1",
        "key": "LOCAL_KEY",
        "max_tokens": 2048,
        "temperature": 0.1,
        "id": "x:7b",
    }
    assert problem(named) is None and not_a_model(named) is None


def test_an_exact_table_name_wins_over_an_endpoint_split() -> None:
    models = _models(
        text=_FILE + '\n["local/special"]\nprovider = "openai"\nid = "other"\nbase_url = "http://h/v1"\n'
    )
    found = find("local/special", models)
    assert found is not None and found.id == "other"  # a quoted table of that very name
    other = find("local/not-special", models)
    assert other is not None and other.id == "not-special"


def test_chosen_resolves_an_endpoint_model_and_says_what_an_endpoint_alone_is() -> None:
    models = _models()
    got = chosen("local/qwen2.5-coder:7b", models, "/c/models.toml")
    assert (got.provider, got.id) == ("openai", "qwen2.5-coder:7b")
    with pytest.raises(ModelsError, match="is an endpoint, which lists models and is none itself") as raised:
        chosen("local", models, "/c/models.toml")
    assert raised.value.kind == "model_config"


def test_a_name_that_is_nothing_lists_the_models_and_the_endpoints_whose_models_are_named_by_id() -> None:
    with pytest.raises(ModelsError) as raised:
        chosen("gone", _models(), "/c/models.toml")
    said = raised.value.message
    assert "the models are sonnet, opus, haiku, llama; or ENDPOINT/ID, for an endpoint (local)." in said
    with pytest.raises(ModelsError) as bare:
        chosen("local/", _models(), "/c/models.toml")
    assert bare.value.kind == "unknown_model"


@pytest.mark.parametrize(
    ("table", "said"),
    [
        ({"id": "x"}, "an endpoint names no id, it lists its models (named local/ID). Remove id"),
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
    assert why is not None and said in why and why.startswith("model 'local' (/c/models.toml)")
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
