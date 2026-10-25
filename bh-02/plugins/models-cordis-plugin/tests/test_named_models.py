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
from models_cordis_plugin.openai import headers_for

_FILE = """\
[local]
provider = "openai"
base_url = "http://localhost:11434/v1"

[local.models.llama]
id = "llama3.2"

[router]
provider = "openai"
base_url = "https://openrouter.ai/api/v1"
key = { env = "OPENROUTER_API_KEY" }
max_tokens = 4096
models = { sonnet = { id = "anthropic/claude-sonnet-4", temperature = 0.2 } }

[work]
provider = "claude-code"
base_url = "https://gateway.example/anthropic"
key = { cmd = "print-a-token", ttl_ms = 60000 }
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
        "key": {"env": "OPENROUTER_API_KEY"},
        "max_tokens": 4096,
        "temperature": 0.2,
    }
    assert "models" not in router.table
    opus = find("work/opus", models)
    assert opus is not None and (opus.provider, opus.id) == ("claude-code", "claude-opus-5-5[1m]")
    assert (
        opus.table["key"] == {"cmd": "print-a-token", "ttl_ms": 60000}
        and opus.table["experimental_betas"] is False
    )
    raw = find("router/meta/llama-4", models)  # an id the endpoint's models doesn't name: on the endpoint
    assert raw is not None and (raw.name, raw.id) == ("router/meta/llama-4", "meta/llama-4")


_X: dict[str, Any] = {"x": {"id": "x"}}  # one model, `m/x`
_OPEN: dict[str, Any] = {"provider": "openai", "base_url": "https://h/v1", "models": _X}
_GATE: dict[str, Any] = {
    "provider": "claude-code",
    "base_url": "https://h/anthropic",
    "key": {"cmd": "print-a-token"},
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
        ({**_OPEN, "base-url": "y"}, "base-url is not a setting of an openai endpoint"),
        ({**_OPEN, "key": ""}, "key must be a table saying where the key comes from"),
        ({**_OPEN, "key": "OPENAI_API_KEY"}, 'write `key = { env = "OPENROUTER_API_KEY" }`'),
        ({**_OPEN, "key": {}}, "key names no source; give exactly one of env, cmd or op"),
        ({**_OPEN, "key": {"ttl_ms": 5}}, "key names no source"),
        ({**_OPEN, "key": {"env": "K", "cmd": "c"}}, "key gives env and cmd; give exactly one"),
        ({**_OPEN, "key": {"cmd": "c", "op": "op://v/i/f"}}, "key gives cmd and op; give exactly one"),
        ({**_OPEN, "key": {"env": "lower_case"}}, "key.env must be the name of an environment variable"),
        ({**_OPEN, "key": {"env": 5}}, "key.env must be the name of an environment variable"),
        ({**_OPEN, "key": {"cmd": " "}}, "key.cmd must be a command that prints a key"),
        ({**_OPEN, "key": {"op": "vault/item"}}, "key.op must be a 1Password reference starting op://"),
        ({**_OPEN, "key": {"env": "K", "ttl_ms": 5}}, "key.ttl_ms says how long a printed key is used"),
        ({**_OPEN, "key": {"cmd": "c", "ttl_ms": True}}, "key.ttl_ms must be a whole number"),
        ({**_OPEN, "key": {"cmd": "c", "ttl_ms": 0}}, "key.ttl_ms must be a whole number"),
        ({**_OPEN, "key": {"cmd": "c", "tll_ms": 5}}, "key has tll_ms, which a key does not take"),
        ({**_OPEN, "key_command": "c"}, "key_command is not a setting of an openai endpoint"),
        ({**_OPEN, "key_ttl_ms": 5}, "key_ttl_ms is not a setting of an openai endpoint"),
        ({**_OPEN, "max_tokens": 0}, "max_tokens must be"),
        ({**_OPEN, "models": {"x": {"id": "x", "temperature": "hot"}}}, "temperature must be"),
        (
            {**_OPEN, "models": {"x": {"id": "x", "key": {"env": "K"}}}},
            "key is not a setting of an openai model (m/x)",
        ),
        ({**_OPEN, "models": {"x": {}}}, "model 'x' names no id"),
        ({**_OPEN, "models": {"x": "x"}}, "models.x is not a table"),
        ({**_OPEN, "models": {"a/b": {"id": "x"}}}, "'a/b' can't name a model"),
        ({**_OPEN, "models": ["x"]}, "models must be a table of models"),
        ({**_OPEN, "colour": "red"}, "colour is not a setting of an openai endpoint; it takes"),
        ({"provider": "claude-code", "base_url": "https://h/v1", "models": _X}, "a gateway needs both"),
        (
            {"provider": "claude-code", "key": {"cmd": "c", "ttl_ms": 5}, "models": _X},
            "key.ttl_ms is for a gateway's key",
        ),
        (
            {**_GATE, "key": {"env": "GATEWAY_KEY"}},
            "a gateway's key can't be an env: the Claude Code CLI gets it by running a command, and bh-02 "
            "never holds it",
        ),
        ({"provider": "claude-code", "base_url": "https://h/v1", "models": _X}, "a gateway needs both"),
        ({"provider": "claude-code", "experimental_betas": False, "models": _X}, "experimental_betas is for"),
        ({**_GATE, "experimental_betas": "no"}, "experimental_betas must be true or false"),
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


@pytest.mark.parametrize(
    "key", [{"env": "CLAUDE_CODE_OAUTH_TOKEN"}, {"cmd": "print-a-token"}, {"op": "op://v/i/f"}]
)
def test_a_claude_code_endpoint_without_a_base_url_takes_a_key_of_any_source_for_its_token(
    key: dict[str, Any],
) -> None:
    """The subscription token's source is the endpoint's `key`; reading the variable the CLI takes
    it from is the point there, though an openai endpoint may not (`withheld`)."""
    table = {"provider": "claude-code", "key": key, "models": _X}
    (named,) = [m for m in combined({"m": table}, "/c/models.toml", {}) if m.name == "m"]
    assert problem(named) is None


@pytest.mark.parametrize(
    ("table", "endpoint"),
    [
        ({"provider": "openai", "base_url": "https://h/v1", "models": _X}, "an openai endpoint"),
        ({"provider": "claude-code", "models": _X}, "a claude-code endpoint"),
    ],
)
def test_an_id_on_an_endpoint_of_a_built_in_provider_is_refused_as_any_setting_it_does_not_take(
    table: dict[str, Any], endpoint: str
) -> None:
    """TASK-0158: an endpoint has no id (its models carry them), so a built-in provider's endpoint refuses
    one with the generic error for a setting it does not take, not with a message about an old shape.
    TASK-0159: the article follows the provider's name ('an openai', 'a claude-code')."""
    (named,) = [m for m in combined({"m": {**table, "id": "x"}}, "/c/models.toml", {}) if m.name == "m"]
    said = str(problem(named))
    assert said.startswith(f"endpoint 'm' (/c/models.toml): id is not a setting of {endpoint}; it takes ")


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


def test_the_models_value_reads_the_model_row_and_the_file_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-stand-in")  # router's key variable (/model looks for it)
    models = tmp_path / "models.toml"
    loader = _Loader(_Entry("model", "models:model", {"models": str(models)}))
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
async def test_a_key_that_holds_a_value_not_a_name_is_refused_without_quoting_it(secret: str) -> None:
    """A key pasted where its source goes (as text, or as an env's name) is never said back: errors are
    shown in the conversation and kept in the session's events."""
    for key in (secret, {"env": secret}):
        table = {**_OPEN, "key": key}
        (host,) = [m for m in combined({"m": table}, "/c/models.toml", {}) if m.name == "m"]
        with pytest.raises(ModelsError) as raised:
            chosen("m/x", [host], "/c/models.toml")
        assert secret not in raised.value.message
        named = find("m/x", [host])
        assert named is host  # a table with a problem means no model: the endpoint's own table comes back
        with pytest.raises(ModelsError) as sent:
            await headers_for(named)
        assert sent.value.kind == "model_config" and secret not in sent.value.message
    assert "not hold the key itself" in raised.value.message


@pytest.mark.parametrize(
    "secret", ["sk-caf" + chr(0xE9), "sk-" + chr(0x1F999), "sk-tab\there", "sk-bell\x07"]
)
async def test_a_key_a_header_can_not_carry_is_a_models_error_that_never_quotes_it(
    monkeypatch: pytest.MonkeyPatch, secret: str
) -> None:
    """TASK-0095: not printable ASCII is no header's: said as a `ModelsError` naming the variable, not the
    `UnicodeEncodeError` httpx2 raises (which `/model`'s discovery used to let out of `refresh`)."""
    monkeypatch.setenv("KEYED_KEY", secret)
    table = {**_OPEN, "key": {"env": "KEYED_KEY"}}
    named = find("keyed/x", combined({"keyed": table}, "/c/models.toml", {}))
    assert named is not None
    with pytest.raises(ModelsError) as raised:
        await headers_for(named)
    assert raised.value.kind == "authentication_failed"
    assert raised.value.message == (
        "model 'keyed/x''s key from the environment variable KEYED_KEY holds a character a request header "
        "can't carry (a key is one line of printable ASCII). Check what the variable holds, fix it, "
        "then try again."
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


_KEYED = (
    '[keyed]\nprovider = "openai"\nbase_url = "https://h/v1"\nkey = { env = "KEYED_KEY" }\n'
    'models.x.id = "x"\n'
)


def test_switching_to_a_model_whose_key_variable_is_unset_is_refused_saying_what_to_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KEYED_KEY", raising=False)
    models = tmp_path / "models.toml"
    models.write_text(_KEYED)
    values = Catalog(_Loader(_Entry("model", "models:model", {"models": str(models)})))
    why = str(values.check("keyed/x"))
    assert why.startswith("model 'keyed/x' reads its key from the environment variable KEYED_KEY, which")
    assert "Export KEYED_KEY in the shell that starts bh-02" in why
    monkeypatch.setenv("KEYED_KEY", "sk-stand-in")  # a stand-in: never a real key
    assert values.check("keyed/x") is None


async def test_a_key_is_read_from_the_environment_on_every_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KEYED_KEY", raising=False)
    named = find("keyed/x", combined({"keyed": {**_OPEN, "key": {"env": "KEYED_KEY"}}}, "/c/models.toml", {}))
    assert named is not None
    with pytest.raises(ModelsError, match="not set in bh-02's environment"):
        await headers_for(named)
    monkeypatch.setenv("KEYED_KEY", "sk-stand-in")
    assert (await headers_for(named))["Authorization"] == "Bearer sk-stand-in"
    monkeypatch.setenv("KEYED_KEY", "sk-rotated")
    assert (await headers_for(named))["Authorization"] == "Bearer sk-rotated"  # each request
