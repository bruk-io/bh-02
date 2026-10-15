"""Named models, pure: the models file's endpoints and the row's `extra`, which wins (there are
no built-in models), what is wrong with a table, and what a name that is no model says; then the
`models` value over them."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin import (
    Catalog,
    ModelConfig,
    ModelsError,
    chosen,
    combined,
    find,
    models_file,
    parsed,
    problem,
    resolved,
)
from models_cordis_plugin.openai import authorization

_FILE = """\
[local]
provider = "openai"
base_url = "http://localhost:11434/v1"

[local.models.llama]
id = "llama3.2"

[router]
provider = "openai"
base_url = "https://openrouter.ai/api/v1"
key = "OPENROUTER_API_KEY"
max_tokens = 4096
models = { sonnet = { id = "anthropic/claude-sonnet-4", temperature = 0.2 } }

[work]
provider = "claude-code"
base_url = "https://gateway.example/anthropic"
key_command = "print-a-token"
experimental_betas = false

[work.models.opus]
id = "claude-opus-5-5[1m]"
"""


def test_there_are_no_built_in_models_and_with_none_named_none_is_chosen() -> None:
    assert combined({}, "f", {}) == []  # no file, no extra: no models at all
    with pytest.raises(ModelsError) as raised:
        resolved(ModelConfig(models="/nonexistent/bh-02-test/models.toml"))  # no default anywhere
    message = raised.value.message
    assert raised.value.kind == "unknown_model"
    assert message.startswith(
        "no model is chosen: neither --model, /model nor the models file's `default` names one; the "
        "models are none."
    )
    assert 'default = "local/MODEL"' in message and "[local.models.MODEL]" in message


def test_the_file_adds_endpoints_whose_models_are_named_under_them_and_extra_wins() -> None:
    models = combined(
        parsed(_FILE, "/c/models.toml").endpoints,
        "/c/models.toml",
        {
            "local": {
                "provider": "openai",
                "base_url": "http://gpu:11434/v1",
                "models": {"qwen": {"id": "qwen3"}},
            }
        },
    )
    by_name = {m.name: m for m in models}
    assert list(by_name) == ["local", "router", "work"]  # a replacement keeps its place
    assert all(named.endpoint for named in models)
    assert by_name["local"].source == "the model row's extra" and all(problem(m) is None for m in models)
    qwen = find("local/qwen", models)
    assert qwen is not None and (qwen.id, qwen.table["base_url"]) == ("qwen3", "http://gpu:11434/v1")
    assert find("local/llama", models) == find("local/llama", models)  # the extra's: llama is an id there
    router = find("router/sonnet", models)  # the endpoint's settings, the model's own over them
    assert router is not None and router.id == "anthropic/claude-sonnet-4"
    assert {k: router.table[k] for k in ("key", "max_tokens", "temperature")} == {
        "key": "OPENROUTER_API_KEY",
        "max_tokens": 4096,
        "temperature": 0.2,
    }
    assert "models" not in router.table
    opus = find("work/opus", models)
    assert opus is not None and (opus.provider, opus.id) == ("claude-code", "claude-opus-5-5[1m]")
    assert opus.table["key_command"] == "print-a-token" and opus.table["experimental_betas"] is False
    raw = find("router/meta/llama-4", models)  # an id the endpoint's models doesn't name: on the endpoint
    assert raw is not None and (raw.name, raw.id) == ("router/meta/llama-4", "meta/llama-4")


_X: dict[str, Any] = {"x": {"id": "x"}}  # one model, `m/x`
_OPEN: dict[str, Any] = {"provider": "openai", "base_url": "https://h/v1", "models": _X}
_GATE: dict[str, Any] = {
    "provider": "claude-code",
    "base_url": "https://h/anthropic",
    "key_command": "print-a-token",
    "models": _X,
}


@pytest.mark.parametrize(
    ("table", "said"),
    [
        ({"models": _X}, 'names no provider; give it `provider = "openai"`'),
        ({"provider": "gemini", "models": _X}, "provider 'gemini' is not one bh-02 has"),
        (
            {"provider": "openai", "base_url": "https://h/v1"},
            "names no models; give it one, `[m.models.MODEL]`",
        ),
        ({"provider": "openai", "models": _X}, "names no base_url; give it the endpoint's base"),
        ({**_OPEN, "base_url": "ftp://h"}, "is not an http(s) URL"),
        ({**_OPEN, "base-url": "y"}, "base-url is not a setting of a openai endpoint"),
        ({**_OPEN, "key": ""}, "key must name a line of local.env"),
        ({**_OPEN, "key": "K", "key_command": "c"}, "give key (a line of local.env) or key_command"),
        ({**_OPEN, "key_command": " "}, "key_command must be a command that prints a key"),
        ({**_OPEN, "key_ttl_ms": 5}, "key_ttl_ms says how long a key_command's key is used"),
        ({**_OPEN, "key_command": "c", "key_ttl_ms": True}, "key_ttl_ms must be a whole number"),
        ({**_OPEN, "max_tokens": 0}, "max_tokens must be"),
        ({**_OPEN, "models": {"x": {"id": "x", "temperature": "hot"}}}, "temperature must be"),
        ({**_OPEN, "models": {"x": {"id": "x", "key": "K"}}}, "key is not a setting of a openai model (m/x)"),
        ({**_OPEN, "models": {"x": {}}}, "model 'x' names no id"),
        ({**_OPEN, "models": {"x": "x"}}, "models.x is not a table"),
        ({**_OPEN, "models": {"a/b": {"id": "x"}}}, "'a/b' can't name a model"),
        ({**_OPEN, "models": ["x"]}, "models must be a table of models"),
        ({**_OPEN, "id": "x"}, "names an id, as a single model's table did: a table is an endpoint now"),
        ({"provider": "claude-code", "base_url": "https://h/v1", "models": _X}, "a gateway needs both"),
        ({"provider": "claude-code", "key_command": "c", "models": _X}, "a gateway needs both"),
        ({"provider": "claude-code", "experimental_betas": False, "models": _X}, "experimental_betas is for"),
        ({**_GATE, "experimental_betas": "no"}, "experimental_betas must be true or false"),
        ({**_GATE, "key": "K"}, "key is not a setting of a claude-code endpoint"),
        ({**_GATE, "discover": True}, "discover is not a setting of a claude-code endpoint"),
        ({**_GATE, "models": {"x": {"id": "x", "max_tokens": 5}}}, "max_tokens is not a setting"),
        (
            {**_OPEN, "base_url": "http://h:notaport/v1"},
            "'http://h:notaport/v1' is not a URL (Port could not",
        ),
        (
            {**_OPEN, "base_url": "http://h:99999/v1"},
            "base_url 'http://h:99999/v1' is not a URL (Port out of",
        ),
        (
            {**_OPEN, "base_url": "http://[bad/v1"},
            "base_url 'http://[bad/v1' is not a URL (Invalid IPv6 URL)",
        ),
        ({**_OPEN, "base_url": "http://:8080/v1"}, "is not an http(s) URL with a host"),
    ],
)
def test_a_table_with_a_problem_says_what_to_fix(table: dict[str, Any], said: str) -> None:
    (named,) = [m for m in combined({"m": table}, "/c/models.toml", {}) if m.name == "m"]
    assert said in str(problem(named))
    with pytest.raises(ModelsError) as raised:
        chosen("m/x", [named], "/c/models.toml")
    message = raised.value.message  # an endpoint's own problem, or one of its model's
    assert raised.value.kind == "model_config"
    assert "endpoint 'm' (/c/models.toml)" in message or "model 'm/x' (/c/models.toml)" in message


def test_a_single_model_s_table_from_before_endpoints_says_how_to_rewrite_it() -> None:
    table = {"provider": "openai", "id": "llama3.2", "base_url": "http://localhost:11434/v1"}
    (named,) = [m for m in combined({"llama": table}, "/c/models.toml", {}) if m.name == "llama"]
    said = str(problem(named))
    assert 'Move the id to a model of it, `[llama.models.MODEL]` with `id = "llama3.2"`' in said
    assert '[llama]\nprovider = "openai"' in said and "[llama.models.MODEL]" in said


def test_an_endpoint_s_name_can_not_hold_a_slash_but_may_be_any_other_name() -> None:
    (slashed,) = combined({"a/b": _OPEN}, "/c/models.toml", {})
    assert "may not hold '/'" in str(problem(slashed))
    (opus,) = combined({"opus": _OPEN}, "/c/models.toml", {})  # nothing is built in to collide with
    assert problem(opus) is None and find("opus/x", [opus]) is not None


def test_an_endpoint_is_no_model_itself_and_says_which_of_its_models_to_name() -> None:
    models = combined(parsed(_FILE, "/c/models.toml").endpoints, "/c/models.toml", {})
    with pytest.raises(ModelsError) as raised:
        chosen("work", models, "/c/models.toml")
    assert "'work' (/c/models.toml) is an endpoint" in raised.value.message
    assert "name one of them, work/MODEL (work/opus)" in raised.value.message


def test_a_name_that_is_no_model_lists_the_models_and_says_how_to_add_it() -> None:
    with pytest.raises(ModelsError) as raised:
        chosen("gpt-5", combined({}, "/c/models.toml", {}), "/c/models.toml")
    message = raised.value.message
    assert raised.value.kind == "unknown_model"
    assert message.startswith("no model named 'gpt-5'; the models are none.")
    assert "models file /c/models.toml" in message and '[NAME]\nprovider = "openai"' in message
    models = combined(parsed(_FILE, "/c/models.toml").endpoints, "/c/models.toml", {})
    with pytest.raises(ModelsError) as named:
        chosen("gpt-5", models, "/c/models.toml")
    assert "the models are local/llama, router/sonnet, work/opus; or ENDPOINT/ID" in (named.value.message)


def test_a_models_file_that_is_not_toml_or_not_tables_is_named() -> None:
    assert parsed(None, "f").endpoints == {}  # no file: no user models
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
    nothing = values.current()  # no file, no default: no model, said
    assert (nothing["name"], nothing["provider"]) == ("none", "")
    assert nothing["unusable"].startswith("no model is chosen")
    assert values.path == str(models) and values.listed() == []
    assert "no model named 'local/llama'" in str(values.check("local/llama"))
    models.write_text(_FILE)  # written since: read again
    assert values.check("local/llama") is None and values.check("router/sonnet") is None
    listed = {m["name"]: m for m in values.listed()}
    assert list(listed) == ["local/llama", "router/sonnet", "work/opus"]
    assert not any(m["current"] for m in listed.values())  # the file names no default
    assert listed["local/llama"]["where"] == "http://localhost:11434/v1"
    assert (listed["work/opus"]["provider"], listed["work/opus"]["id"]) == (
        "claude-code",
        "claude-opus-5-5[1m]",
    )
    assert values.endpoints() == []  # none discovers, none has a problem: nothing to say besides their models
    loader.now = [
        _Entry("model", None, {"models": str(models), "default": "local/llama"})
    ]  # /model local/llama
    assert values.current() == {"name": "local/llama", "provider": "openai"}
    loader.now = [_Entry("model", None, {"models": str(models), "default": "gone"})]
    names_none = values.current()  # names no model there is: unusable, said
    assert (names_none["name"], names_none["provider"]) == ("gone", "")
    assert names_none["unusable"].startswith("no model named 'gone'")
    models.write_text("[broken\n")
    broken = values.current()  # never raises: the status bar reads it
    assert (broken["name"], broken["provider"]) == ("gone", "") and "is not TOML" in broken["unusable"]
    assert "is not TOML" in str(values.check("local/llama"))
    # not a raise since TASK-0093: `problem` is what /model says of the file, and it lists none of its models
    assert values.listed() == []
    assert values.problem is not None and "is not TOML" in values.problem


def test_the_models_value_over_another_component_says_it_has_no_models() -> None:
    values = Catalog(_Loader(_Entry("model", "bh_02.testing:echo_model", {})))
    assert values.current() == {"name": "bh_02.testing:echo_model", "provider": ""}
    assert "is bh_02.testing:echo_model, not models:model" in str(values.check("sub/haiku"))


@pytest.mark.parametrize("secret", ["sk-proj-SECRETVALUE", "gsk_secretvalue123", "not a name"])
def test_a_key_that_holds_a_value_not_a_line_name_is_refused_without_quoting_it(secret: str) -> None:
    """A key pasted where its local.env line's name goes is never said back: errors are shown in
    the conversation and kept in the session's events."""
    table = {**_OPEN, "key": secret}
    (host,) = [m for m in combined({"m": table}, "/c/models.toml", {}) if m.name == "m"]
    with pytest.raises(ModelsError) as raised:
        chosen("m/x", [host], "/c/models.toml")
    assert "not hold the key itself" in raised.value.message and secret not in raised.value.message
    named = find("m/x", [host])
    assert named is host  # a table with a problem means no model: the endpoint's own table comes back
    with pytest.raises(ModelsError) as sent:
        authorization(named, None)
    assert sent.value.kind == "model_config" and secret not in sent.value.message


@pytest.mark.parametrize(
    "secret", ["sk-caf" + chr(0xE9), "sk-" + chr(0x1F999), "sk-tab\there", "sk-bell\x07"]
)
def test_a_key_line_a_header_can_not_carry_is_a_models_error_that_never_quotes_it(
    tmp_path: Path, secret: str
) -> None:
    """TASK-0095: not printable ASCII is no header's: said as a `ModelsError` naming the line, not the
    `UnicodeEncodeError` httpx2 raises (which `/model`'s discovery used to let out of `refresh`)."""
    env = tmp_path / "local.env"
    env.write_text(f"KEYED_KEY={secret}\n", encoding="utf-8")
    table = {**_OPEN, "key": "KEYED_KEY"}
    named = find("keyed/x", combined({"keyed": table}, "/c/models.toml", {}))
    assert named is not None
    with pytest.raises(ModelsError) as raised:
        authorization(named, str(env))
    assert raised.value.kind == "authentication_failed"
    assert raised.value.message == (
        f"model 'keyed/x' names the key KEYED_KEY, whose line in {env} holds a character a request header "
        "can't carry (a key is printable ASCII). Fix that line, then try again."
    )
    assert secret not in raised.value.message


def test_a_malformed_base_url_in_the_file_is_one_model_s_problem_not_the_catalog_s(tmp_path: Path) -> None:
    """One typo'd model neither breaks `/model` for the rest nor the model row: it is listed
    with its problem, switching to it says why not, and as the default it binds `Unusable`."""
    models = tmp_path / "models.toml"
    models.write_text(
        '[typo]\nprovider = "openai"\nbase_url = "http://[bad/v1"\nmodels.x.id = "x"\n'
        '[sub]\nprovider = "claude-code"\nmodels.haiku.id = "haiku"\n'
    )
    values = Catalog(_Loader(_Entry("model", "models:model", {"models": str(models)})))
    assert [m["name"] for m in values.listed()] == ["sub/haiku"]  # typo serves no model
    (said,) = values.endpoints()
    assert said["name"] == "typo" and "Invalid IPv6 URL" in said["notes"][0]
    assert "is not a URL" in str(values.check("typo/x")) and values.check("sub/haiku") is None
    with pytest.raises(ModelsError) as raised:
        resolved(ModelConfig(default="typo/x", models=str(models)))
    assert raised.value.kind == "model_config"


@pytest.mark.parametrize(
    ("config", "said"),
    [
        ({"extra": {"x": "notatable"}}, "the model row's extra: 'x' is not a table; each endpoint is one"),
        ({"extra": "x"}, "the model row's extra is str, not a table of endpoints"),
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


_KEYED = '[keyed]\nprovider = "openai"\nbase_url = "https://h/v1"\nkey = "KEYED_KEY"\nmodels.x.id = "x"\n'


def test_switching_to_a_model_whose_key_line_is_missing_is_refused_saying_where_to_add_it(
    tmp_path: Path,
) -> None:
    env = tmp_path / "scratch.env"
    env.write_text("OTHER=1\n")
    models = tmp_path / "models.toml"
    models.write_text(_KEYED)
    values = Catalog(_Loader(_Entry("model", "models:model", {"models": str(models), "env_file": str(env)})))
    why = str(values.check("keyed/x"))
    assert why.startswith(f"model 'keyed/x' names the key KEYED_KEY, which is not a line of {env}.")
    assert "(keep that file out of git), then /model keyed/x again." in why
    env.write_text("KEYED_KEY=sk-stand-in\n")
    assert values.check("keyed/x") is None


def test_a_key_is_read_from_the_nearest_searched_file_past_a_jail_s_placeholder(tmp_path: Path) -> None:
    """The openai provider reads its key per request, from the first searched `local.env` that
    is a file: a Linux jail's placeholder directory nearer up never hides it, and `/model`'s
    check looks in the same place."""
    near, root = tmp_path / "a", tmp_path
    searched = [str(near / "local.env"), str(root / "local.env")]
    (near / "local.env").mkdir(parents=True)
    (root / "local.env").write_text("KEYED_KEY=sk-stand-in\n")  # a stand-in: never a real key
    named = find("keyed/x", combined({"keyed": {**_OPEN, "key": "KEYED_KEY"}}, "/c/models.toml", {}))
    assert named is not None
    assert authorization(named, None, searched)["Authorization"] == "Bearer sk-stand-in"
    assert authorization(named, None, searched)["Authorization"] == "Bearer sk-stand-in"  # each request
    models = tmp_path / "models.toml"
    models.write_text(_KEYED)
    values = Catalog(_Loader(_Entry("model", "models:model", {"models": str(models)})), searched=searched)
    assert values.check("keyed/x") is None
    assert Catalog(_Loader(_Entry("model", "models:model", {"models": str(models)}))).check("keyed/x")
