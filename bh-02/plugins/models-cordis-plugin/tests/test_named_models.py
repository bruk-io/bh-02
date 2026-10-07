"""Named models, pure: the built-ins, the models file and the row's `extra`, which wins, what is
wrong with a table, and what a name that is no model says; then the `models` value over them."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin import (
    BUILT_IN,
    Catalog,
    ModelConfig,
    ModelsError,
    chosen,
    combined,
    models_file,
    parsed,
    problem,
    resolved,
)
from models_cordis_plugin.openai import authorization

_FILE = """\
[llama]
provider = "openai"
id = "llama3.2"
base_url = "http://localhost:11434/v1"

[router]
provider = "openai"
id = "anthropic/claude-sonnet-4"
base_url = "https://openrouter.ai/api/v1"
key = "OPENROUTER_API_KEY"
max_tokens = 4096
temperature = 0.2

[opus]
provider = "openai"
id = "not-claude"
base_url = "https://example.com/v1"
"""


def test_the_built_ins_are_claude_through_claude_code_by_their_aliases() -> None:
    models = combined({}, "f", {})
    assert [(m.name, m.provider, m.id) for m in models] == [
        ("sonnet", "claude-code", "sonnet"),
        ("opus", "claude-code", "opus"),
        ("haiku", "claude-code", "haiku"),
    ]
    assert set(BUILT_IN) == {"sonnet", "opus", "haiku"} and all(problem(m) is None for m in models)


def test_the_file_adds_models_a_user_s_shadows_a_built_in_and_extra_wins_over_the_file() -> None:
    models = combined(
        parsed(_FILE, "/c/models.toml"),
        "/c/models.toml",
        {"llama": {"provider": "openai", "id": "qwen3", "base_url": "http://gpu:11434/v1"}},
    )
    by_name = {m.name: m for m in models}
    assert list(by_name) == ["sonnet", "opus", "haiku", "llama", "router"]  # a replacement keeps its place
    assert by_name["opus"].provider == "openai" and by_name["opus"].shadows  # allowed, and noted
    assert by_name["opus"].source == "/c/models.toml"
    assert by_name["llama"].id == "qwen3" and by_name["llama"].source == "the model row's extra"
    assert by_name["router"].table["key"] == "OPENROUTER_API_KEY" and problem(by_name["router"]) is None


@pytest.mark.parametrize(
    ("table", "said"),
    [
        ({"id": "x"}, 'names no provider; give it `provider = "openai"`'),
        ({"provider": "gemini", "id": "x"}, "provider 'gemini' is not one bh-02 has"),
        ({"provider": "openai", "base_url": "https://h/v1"}, "names no model id"),
        ({"provider": "openai", "id": "x"}, "names no base_url; give it the endpoint's base"),
        ({"provider": "openai", "id": "x", "base_url": "ftp://h"}, "is not an http(s) URL"),
        (
            {"provider": "openai", "id": "x", "base_url": "https://h/v1", "base-url": "y"},
            "base-url is not a setting",
        ),
        (
            {"provider": "openai", "id": "x", "base_url": "https://h/v1", "key": ""},
            "key must name a line of local.env",
        ),
        (
            {"provider": "openai", "id": "x", "base_url": "https://h/v1", "max_tokens": 0},
            "max_tokens must be",
        ),
        (
            {"provider": "openai", "id": "x", "base_url": "https://h/v1", "temperature": "hot"},
            "temperature must be",
        ),
        (
            {"provider": "claude-code", "id": "x", "base_url": "https://h/v1"},
            "base_url is not a setting of a claude-code",
        ),
        (
            {"provider": "openai", "id": "x", "base_url": "http://h:notaport/v1"},
            "base_url 'http://h:notaport/v1' is not a URL (Port could not be cast",
        ),
        (
            {"provider": "openai", "id": "x", "base_url": "http://h:99999/v1"},
            "base_url 'http://h:99999/v1' is not a URL (Port out of range",
        ),
        (
            {"provider": "openai", "id": "x", "base_url": "http://[bad/v1"},
            "base_url 'http://[bad/v1' is not a URL (Invalid IPv6 URL)",
        ),
        (
            {"provider": "openai", "id": "x", "base_url": "http://:8080/v1"},
            "is not an http(s) URL with a host",
        ),
    ],
)
def test_a_table_with_a_problem_says_what_to_fix(table: dict[str, Any], said: str) -> None:
    (named,) = [m for m in combined({"m": table}, "/c/models.toml", {}) if m.name == "m"]
    assert said in str(problem(named))
    with pytest.raises(ModelsError) as raised:
        chosen("m", [named], "/c/models.toml")
    assert raised.value.kind == "model_config" and "model 'm' (/c/models.toml)" in raised.value.message


def test_a_name_that_is_no_model_lists_the_models_and_says_how_to_add_it() -> None:
    with pytest.raises(ModelsError) as raised:
        chosen("gpt-5", combined({}, "/c/models.toml", {}), "/c/models.toml")
    message = raised.value.message
    assert raised.value.kind == "unknown_model"
    assert message.startswith("no model named 'gpt-5'; the models are sonnet, opus, haiku.")
    assert "models file /c/models.toml" in message and '[gpt-5]\nprovider = "openai"' in message


def test_a_models_file_that_is_not_toml_or_not_tables_is_named() -> None:
    assert parsed(None, "f") == {}  # no file: no user models
    with pytest.raises(ModelsError, match="the models file /c/m.toml is not TOML"):
        parsed("[llama\n", "/c/m.toml")
    with pytest.raises(ModelsError, match="'llama' is not a table"):
        parsed('llama = "x"\n', "/c/m.toml")


def test_the_models_file_is_under_xdg_config_home_else_dot_config() -> None:
    assert models_file(None, {"XDG_CONFIG_HOME": "/x"}) == Path("/x/bh-02/models.toml")
    assert models_file(None, {}) == Path.home() / ".config" / "bh-02" / "models.toml"
    assert models_file("/elsewhere/m.toml", {"XDG_CONFIG_HOME": "/x"}) == Path("/elsewhere/m.toml")


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


def test_the_models_value_reads_the_model_row_and_the_file_fresh(tmp_path: Path) -> None:
    models = tmp_path / "models.toml"
    env = tmp_path / "local.env"  # router's key line is there (/model looks for it)
    env.write_text("OPENROUTER_API_KEY=sk-stand-in\n")
    loader = _Loader(_Entry("model", "models:model", {"models": str(models), "env_file": str(env)}))
    values = Catalog(loader)
    assert values.current() == {"name": "sonnet", "provider": "claude-code"}  # the row's default
    assert values.path == str(models) and [m["name"] for m in values.listed()] == ["sonnet", "opus", "haiku"]
    assert values.check("llama") is not None and "no model named 'llama'" in str(values.check("llama"))
    models.write_text(_FILE)  # written since: read again
    assert values.check("llama") is None and values.check("router") is None
    listed = {m["name"]: m for m in values.listed()}
    assert listed["sonnet"]["current"] and not listed["llama"]["current"]
    assert listed["llama"]["where"] == "http://localhost:11434/v1"
    assert listed["opus"]["shadows"].startswith("shadows the built-in 'opus'")
    loader.now = [_Entry("model", None, {"models": str(models), "default": "llama"})]  # /model llama
    assert values.current() == {"name": "llama", "provider": "openai"}
    loader.now = [_Entry("model", None, {"models": str(models), "default": "gone"})]
    assert values.current() == {"name": "gone", "provider": ""}  # names no model there is
    models.write_text("[broken\n")
    assert values.current() == {"name": "gone", "provider": ""}  # never raises: the status bar reads it
    assert "is not TOML" in str(values.check("llama"))
    with pytest.raises(ModelsError):
        values.listed()  # /model says what is wrong with the file


def test_the_models_value_over_another_component_says_it_has_no_models() -> None:
    values = Catalog(_Loader(_Entry("model", "bh_02.testing:echo_model", {})))
    assert values.current() == {"name": "bh_02.testing:echo_model", "provider": ""}
    assert "is bh_02.testing:echo_model, not models:model" in str(values.check("haiku"))


@pytest.mark.parametrize("secret", ["sk-proj-SECRETVALUE", "gsk_secretvalue123", "not a name"])
def test_a_key_that_holds_a_value_not_a_line_name_is_refused_without_quoting_it(secret: str) -> None:
    """A key pasted where its local.env line's name goes is never said back: errors are shown in
    the conversation and kept in the session's events."""
    table = {"provider": "openai", "id": "x", "base_url": "https://h/v1", "key": secret}
    (named,) = [m for m in combined({"m": table}, "/c/models.toml", {}) if m.name == "m"]
    with pytest.raises(ModelsError) as raised:
        chosen("m", [named], "/c/models.toml")
    assert "not hold the key itself" in raised.value.message and secret not in raised.value.message
    with pytest.raises(ModelsError) as sent:
        authorization(named, None)
    assert sent.value.kind == "model_config" and secret not in sent.value.message


def test_a_malformed_base_url_in_the_file_is_one_model_s_problem_not_the_catalog_s(tmp_path: Path) -> None:
    """One typo'd model neither breaks `/model` for the rest nor the model row: it is listed
    with its problem, switching to it says why not, and as the default it binds `Unusable`."""
    models = tmp_path / "models.toml"
    models.write_text('[typo]\nprovider = "openai"\nid = "x"\nbase_url = "http://[bad/v1"\n')
    values = Catalog(_Loader(_Entry("model", "models:model", {"models": str(models)})))
    listed = {m["name"]: m for m in values.listed()}
    assert "Invalid IPv6 URL" in listed["typo"]["problem"] and "problem" not in listed["haiku"]
    assert "is not a URL" in str(values.check("typo")) and values.check("haiku") is None
    with pytest.raises(ModelsError) as raised:
        resolved(ModelConfig(default="typo", models=str(models)))
    assert raised.value.kind == "model_config"


@pytest.mark.parametrize(
    ("config", "said"),
    [
        ({"extra": {"x": "notatable"}}, "the model row's extra: 'x' is not a table; each model is one"),
        ({"extra": "x"}, "the model row's extra is str, not a table of models"),
        ({"default": 5}, "the model row's default is 5, not a model's name"),
        ({"cwd": 5}, "the model row's cwd is 5, not a directory"),
    ],
)
def test_a_row_config_of_the_wrong_shape_is_a_models_error_saying_what_to_fix(
    tmp_path: Path, config: dict[str, Any], said: str
) -> None:
    """cordis does not type-check a row's config, so what a layer hands the row is checked here."""
    whole = {"models": str(tmp_path / "none.toml"), **config}
    with pytest.raises(ModelsError) as raised:
        resolved(ModelConfig(**whole))
    assert raised.value.kind == "model_config" and said in raised.value.message
    values = Catalog(_Loader(_Entry("model", "models:model", whole)))
    assert values.current()["provider"] == ""  # the status bar never raises


def test_switching_to_a_model_whose_key_line_is_missing_is_refused_saying_where_to_add_it(
    tmp_path: Path,
) -> None:
    env = tmp_path / "scratch.env"
    env.write_text("OTHER=1\n")
    models = tmp_path / "models.toml"
    models.write_text(
        '[keyed]\nprovider = "openai"\nid = "x"\nbase_url = "https://h/v1"\nkey = "KEYED_KEY"\n'
    )
    values = Catalog(_Loader(_Entry("model", "models:model", {"models": str(models), "env_file": str(env)})))
    why = str(values.check("keyed"))
    assert why.startswith(f"model 'keyed' names the key KEYED_KEY, which is not a line of {env}.")
    assert "(keep that file out of git), then /model keyed again." in why
    env.write_text("KEYED_KEY=sk-stand-in\n")
    assert values.check("keyed") is None


def test_a_key_is_read_from_the_nearest_searched_file_past_a_jail_s_placeholder(tmp_path: Path) -> None:
    """The openai provider reads its key per request, from the first searched `local.env` that
    is a file: a Linux jail's placeholder directory nearer up never hides it, and `/model`'s
    check looks in the same place."""
    near, root = tmp_path / "a", tmp_path
    searched = [str(near / "local.env"), str(root / "local.env")]
    (near / "local.env").mkdir(parents=True)
    (root / "local.env").write_text("KEYED_KEY=sk-stand-in\n")  # a stand-in: never a real key
    table = {"provider": "openai", "id": "x", "base_url": "https://h/v1", "key": "KEYED_KEY"}
    (named,) = [m for m in combined({"keyed": table}, "/c/models.toml", {}) if m.name == "keyed"]
    assert authorization(named, None, searched)["Authorization"] == "Bearer sk-stand-in"
    assert authorization(named, None, searched)["Authorization"] == "Bearer sk-stand-in"  # each request
    models = tmp_path / "models.toml"
    models.write_text(
        '[keyed]\nprovider = "openai"\nid = "x"\nbase_url = "https://h/v1"\nkey = "KEYED_KEY"\n'
    )
    values = Catalog(_Loader(_Entry("model", "models:model", {"models": str(models)})), searched=searched)
    assert values.check("keyed") is None
    assert Catalog(_Loader(_Entry("model", "models:model", {"models": str(models)}))).check("keyed")
