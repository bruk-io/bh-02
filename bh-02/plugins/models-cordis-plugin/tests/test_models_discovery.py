"""Model discovery through the `models` value: what `/model` lists of an endpoint, the cache and when
it is asked again, and the trust each criterion of TASK-0088 asks for, over a `FakeGet` (no network)."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cordis.loader import read_layer
from models_cordis_plugin import (
    Catalog,
    ModelConfig,
    ModelsError,
    Switch,
    SwitchConfig,
    opened,
    resolved,
    set_model,
)
from models_cordis_plugin.openai import Down, Reply
from models_cordis_plugin.openai.listing import SHOWN
from models_cordis_plugin.openai.testing import FakeGet

_LOCAL = "http://localhost:1234/v1/models"
_FAR = "http://far:8080/v1/models"
_FILE = """\
[local]
provider = "openai"
discover = true
base_url = "http://localhost:1234/v1"
"""
_KEY = "sk-live-0123456789abcdef"


def _ids(*ids: object, status: int = 200) -> Reply:
    return Reply(status, json.dumps({"object": "list", "data": [{"id": i} for i in ids]}).encode())


@dataclass
class _Entry:
    id: str
    use: str | None
    config: dict[str, Any]


class _Loader:
    def __init__(self, *entries: _Entry) -> None:
        self.entries_now = list(entries)
        self.reloads = 0

    def entries(self) -> list[_Entry]:
        return self.entries_now

    def status(self) -> dict[str, str]:
        return {"model": "up"}

    async def reload(self) -> None:
        self.reloads += 1


class _Jobs:
    def put(self, job: Any, failed: Any) -> None:
        pass


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def _own_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def _file(tmp_path: Path, text: str = _FILE) -> Path:
    path = tmp_path / "models.toml"
    path.write_text(text)
    return path


def _catalog(
    tmp_path: Path, get: FakeGet, text: str = _FILE, clock: _Clock | None = None, **row: Any
) -> Catalog:
    entry = _Entry("model", "models:model", {"models": str(_file(tmp_path, text)), **row})
    return Catalog(_Loader(entry), get=get, clock=clock or _Clock())


def _switch(tmp_path: Path, catalog: Catalog) -> Switch:
    layer = tmp_path / "session.toml"
    layer.write_text('[[plugin]]\nid = "model"\nconfig = { state = "/s/claude" }\n')
    return Switch(_Loader(), catalog, SwitchConfig(layer=str(layer)), _Jobs(), set_model)


def _discovered(catalog: Catalog) -> list[str]:
    return [m["name"] for m in catalog.listed() if "/" in m["name"]]


async def test_model_lists_what_each_endpoint_serves_named_endpoint_slash_id(tmp_path: Path) -> None:
    text = _FILE + '\n[far]\nprovider = "openai"\ndiscover = true\nbase_url = "http://far:8080/v1"\n'
    get = FakeGet({_LOCAL: _ids("qwen2.5-coder:7b", "Qwen/Q:7b", "llama3.2:latest"), _FAR: Down("no luck")})
    catalog = _catalog(tmp_path, get, text)
    said = str(await _switch(tmp_path, catalog).run("")).splitlines()
    at = "http://localhost:1234/v1"
    assert [line.split() for line in said[3:6]] == [  # a name, its provider, its id, where: aligned
        ["local/Qwen/Q:7b", "openai", "Qwen/Q:7b", "at", at],
        ["local/llama3.2:latest", "openai", "llama3.2:latest", "at", at],
        ["local/qwen2.5-coder:7b", "openai", "qwen2.5-coder:7b", "at", at],
    ]
    assert said[6:] == [
        "  far: no list from http://far:8080/v1/models (no luck); its models are not listed",
        f"/model NAME switches; add models in {catalog.path}",
    ]  # one line, not an error, and the list it could make is made
    assert sorted(url for url, _ in get.calls) == [_FAR, _LOCAL]  # one request each
    listed = {m["name"]: m for m in catalog.listed()}
    assert listed["local/llama3.2:latest"] == {
        "name": "local/llama3.2:latest",
        "provider": "openai",
        "id": "llama3.2:latest",
        "current": False,
        "where": "http://localhost:1234/v1",
    }


async def test_a_model_of_an_endpoint_means_a_model_with_no_network_call(tmp_path: Path) -> None:
    """`--model`, `/model` and a layer's default all arrive as the name: it resolves from the
    endpoint's table; the model row has no way to ask a server, and the catalog asks only in `refresh`."""
    get = FakeGet({_LOCAL: _ids("x:7b")})
    catalog = _catalog(tmp_path, get, default="local/x:7b")
    models = str(tmp_path / "models.toml")
    assert resolved(ModelConfig(default="local/x:7b", models=models)).id == "x:7b"
    async with opened(ModelConfig(default="local/x:7b", models=models)):
        pass
    assert catalog.check("local/x:7b") is None and catalog.check("local/anything:at/all") is None
    assert catalog.current() == {"name": "local/x:7b", "provider": "openai"}
    assert catalog.listed() and catalog.endpoints()
    switch = _switch(tmp_path, catalog)
    note, _restarting = await switch.run("local/other:1b")  # `/model NAME`, an id the server may lack
    assert "switching to local/other:1b" in str(note["text"])
    await asyncio.sleep(0.05)  # a task any of them had scheduled would have run by now
    assert get.calls == []  # not one request, from any of them
    (row,) = read_layer(tmp_path / "session.toml")
    assert row.config == {"state": "/s/claude", "default": "local/other:1b"}  # a layer's default


_BROKEN = _FILE + 'id = "x"\n'  # an endpoint with an id beside discover = true: its table's problem


def _why(tmp_path: Path) -> str:
    return (
        f"model 'local' ({tmp_path / 'models.toml'}): an endpoint names no id, it lists its models "
        "(named local/ID). Remove id, or remove discover for a single model"
    )


async def test_a_layer_s_default_naming_a_model_of_a_broken_endpoint_binds_a_model_that_says_why(
    tmp_path: Path,
) -> None:
    """TASK-0095, by `--model` too (it writes a layer's default): refused with the table's problem; the model
    row still binds, so bh-02 starts, and each step says why."""
    get = FakeGet({_LOCAL: _ids("x")})
    _catalog(tmp_path, get, _BROKEN)  # writes the models file
    config = ModelConfig(default="local/x", models=str(tmp_path / "models.toml"))
    with pytest.raises(ModelsError) as raised:
        resolved(config)
    assert raised.value.kind == "model_config" and raised.value.message == _why(tmp_path)
    async with opened(config) as model:  # the row is up
        with pytest.raises(ModelsError) as step:
            [chunk async for chunk in model.complete([{"role": "user", "content": "hi"}], [])]
    assert step.value.message == _why(tmp_path)
    assert get.calls == []


async def test_the_models_file_s_default_naming_a_model_of_a_broken_endpoint_is_refused_the_same_way(
    tmp_path: Path,
) -> None:
    get = FakeGet({_LOCAL: _ids("x")})
    _catalog(tmp_path, get, 'default = "local/x:7b"\n' + _BROKEN)
    config = ModelConfig(models=str(tmp_path / "models.toml"))  # no layer names a model: the file's counts
    with pytest.raises(ModelsError) as raised:
        resolved(config)
    assert raised.value.message == _why(tmp_path)
    async with opened(config) as model:
        with pytest.raises(ModelsError, match="an endpoint names no id"):
            [chunk async for chunk in model.complete([{"role": "user", "content": "hi"}], [])]
    assert get.calls == []


async def test_slash_model_name_of_a_broken_endpoint_s_model_is_refused_and_the_status_bar_says_none(
    tmp_path: Path,
) -> None:
    get = FakeGet({_LOCAL: _ids("x")})
    catalog = _catalog(tmp_path, get, _BROKEN, default="local/x")
    assert catalog.check("local/x:7b") == _why(tmp_path) and catalog.check("local") == _why(tmp_path)
    # the status bar: no provider, no error, and the model is said to be unusable (TASK-0093)
    assert catalog.current() == {"name": "local/x", "provider": "", "unusable": _why(tmp_path)}
    switch = _switch(tmp_path, catalog)
    said = await switch.run("local/other:1b")  # `/model NAME`
    assert said == f"not switched: {_why(tmp_path)}"
    (row,) = read_layer(tmp_path / "session.toml")
    assert row.config == {"state": "/s/claude"}  # nothing was written to the session's layer
    assert get.calls == []


async def test_the_choices_and_the_status_bar_never_ask_a_server_and_offer_what_model_found(
    tmp_path: Path,
) -> None:
    get = FakeGet({_LOCAL: _ids("qwen2.5-coder:7b")})
    catalog = _catalog(tmp_path, get)
    switch = _switch(tmp_path, catalog)
    choices = switch.spec()["choices"]
    for _ in range(3):  # the palette's every key
        assert [c["args"] for c in choices()] == ["sonnet", "opus", "haiku"]
        catalog.current()  # the status bar's
    await asyncio.sleep(0.05)  # a task the choices scheduled would have run by now
    assert get.calls == []
    await switch.run("")  # `/model` lists, and asks
    assert len(get.calls) == 1
    offered = choices()
    assert [c["args"] for c in offered][-1] == "local/qwen2.5-coder:7b"
    assert offered[-1]["help"] == "switch to local/qwen2.5-coder:7b (openai: qwen2.5-coder:7b)"
    await asyncio.sleep(0.05)
    assert len(get.calls) == 1  # reading it again asks nothing


async def test_include_narrows_what_is_listed_from_what_was_kept(tmp_path: Path) -> None:
    get = FakeGet({_LOCAL: _ids("qwen3:30b", "llama3.2:latest", "qwen2.5-coder:7b", "mistral")})
    text = _FILE + 'include = ["qwen*"]\n'
    catalog = _catalog(tmp_path, get, text)
    await catalog.refresh()
    assert _discovered(catalog) == ["local/qwen2.5-coder:7b", "local/qwen3:30b"]
    (tmp_path / "models.toml").write_text(_FILE + 'include = ["llama*", "mistral"]\n')
    assert _discovered(catalog) == ["local/llama3.2:latest", "local/mistral"]  # no new request: it is a read
    assert len(get.calls) == 1
    (tmp_path / "models.toml").write_text(_FILE + 'include = ["zzz*"]\n')
    assert _discovered(catalog) == []
    assert catalog.endpoints()[0]["notes"] == ["none of its 4 models matches include = ['zzz*']"]


async def test_more_than_the_shown_cap_is_cut_and_said(tmp_path: Path) -> None:
    get = FakeGet({_LOCAL: _ids(*(f"m{n:04d}" for n in range(SHOWN + 5)))})
    catalog = _catalog(tmp_path, get)
    await catalog.refresh()
    assert len(_discovered(catalog)) == SHOWN
    assert catalog.endpoints()[0]["notes"] == ['5 more not shown; narrow them with include = ["qwen*"]']


async def test_a_server_s_ids_are_shown_with_control_characters_stripped(tmp_path: Path) -> None:
    get = FakeGet({_LOCAL: _ids("evil\x1b[2Jid", "bell\x07x", "\x1b\x9b", "ok:1", "sp ace", "café")})
    catalog = _catalog(tmp_path, get)
    said = str(await _switch(tmp_path, catalog).run(""))
    assert not any(ord(c) < 0x20 and c != "\n" or 0x7F <= ord(c) <= 0x9F for c in said)  # no control char
    assert _discovered(catalog) == ["local/bellx", "local/evil[2Jid", "local/ok:1"]
    assert "3 entries not listed: a model here needs an id of printable ASCII without a space" in said


async def test_an_id_is_only_a_name_and_a_body_never_a_path_an_argument_or_a_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    nasty = ["../../escape", "--flag", "$(touch${IFS}pwned)", "a;b", 'x"y\\z', "/etc/passwd", "-rf"]
    get = FakeGet({_LOCAL: _ids(*nasty)})
    catalog = _catalog(tmp_path, get)
    switch = _switch(tmp_path, catalog)
    await switch.run("")
    assert _discovered(catalog) == sorted(f"local/{i}" for i in nasty)
    for id in nasty:
        name = f"local/{id}"
        assert catalog.check(name) is None
        assert resolved(ModelConfig(default=name, models=str(tmp_path / "models.toml"))).id == id
        set_model(str(tmp_path / "session.toml"), "model", name)
        (row,) = read_layer(tmp_path / "session.toml")
        assert row.config == {"state": "/s/claude", "default": name}  # one string, whatever it holds
    assert [url for url, _ in get.calls] == [_LOCAL]  # the one URL asked is never made of an id
    assert list(work.iterdir()) == [] and not (tmp_path / "pwned").exists()  # no file made or named by one


async def test_the_key_goes_in_the_request_s_header_and_nowhere_else(tmp_path: Path) -> None:
    env = tmp_path / "local.env"
    env.write_text(f"LOCAL_KEY={_KEY}\n")
    text = _FILE + 'key = "LOCAL_KEY"\n'
    get = FakeGet({_LOCAL: Down(f"the proxy said {_KEY} is wrong, sk-live-****cdef too")})
    catalog = _catalog(tmp_path, get, text, env_file=str(env))
    switch = _switch(tmp_path, catalog)
    said = str(await switch.run(""))
    ((url, headers),) = get.calls
    assert headers["Authorization"] == f"Bearer {_KEY}" and headers["Accept"] == "application/json"
    assert url == _LOCAL and _KEY not in url  # not in the URL
    shown = " ".join([said, repr(catalog.endpoints()), repr(catalog.listed()), repr(catalog)])
    assert _KEY not in shown and "cdef" not in shown  # not in a line, even one a server echoed it into
    assert "<key>" in said  # taken out where the server said it
    get.replies[_LOCAL] = _ids("m")
    await catalog.refresh()
    assert _KEY not in repr(catalog.listed())  # and what was listed holds ids alone


async def test_a_key_whose_line_is_missing_asks_nothing_and_says_so(tmp_path: Path) -> None:
    env = tmp_path / "local.env"
    env.write_text("OTHER=1\n")
    get = FakeGet({_LOCAL: _ids("m")})
    catalog = _catalog(tmp_path, get, _FILE + 'key = "LOCAL_KEY"\n', env_file=str(env))
    said = str(await _switch(tmp_path, catalog).run(""))
    assert get.calls == []
    assert (
        "local: no list from http://localhost:1234/v1/models (model 'local' names the key LOCAL_KEY" in said
    )
    assert "then /model local again" in said


async def test_endpoints_come_only_from_the_trusted_models_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get = FakeGet({_LOCAL: _ids("m"), _FAR: _ids("m")})
    # a models file in the project, which the model's code can write: not read, so no endpoints
    project = tmp_path / "project"
    inside = project / ".config" / "bh-02" / "models.toml"
    inside.parent.mkdir(parents=True)
    inside.write_text(_FILE)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(project / ".config"))
    entry = _Entry("model", "models:model", {"cwd": str(project)})
    refused = Catalog(_Loader(entry), get=get, clock=_Clock())
    await refused.refresh()
    assert get.calls == [] and _discovered(refused) == [] and refused.endpoints() == []
    assert refused.problem is not None and "is not read: it is in the project" in refused.problem
    # a layer's `extra` is no endpoint either: its table is a problem, and nothing is asked
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    extra = {"far": {"provider": "openai", "discover": True, "base_url": "http://far:8080/v1"}}
    catalog = _catalog(tmp_path, get, "", extra=extra)
    await catalog.refresh()
    assert get.calls == [] and _discovered(catalog) == [] and catalog.endpoints() == []
    (far,) = [m for m in catalog.listed() if m["name"] == "far"]
    assert "discover is read only from the models file, never from a layer" in far["problem"]


async def test_a_listing_is_not_asked_for_again_while_fresh_and_a_failure_never_is(tmp_path: Path) -> None:
    clock, get = _Clock(), FakeGet({_LOCAL: _ids("a")})
    catalog = _catalog(tmp_path, get, clock=clock)
    await catalog.refresh()
    clock.now += 29
    await catalog.refresh()
    assert len(get.calls) == 1  # retyping /model does not ask a hosted endpoint again
    clock.now += 2  # 31 s
    get.replies[_LOCAL] = Down("gone")
    await catalog.refresh()
    assert len(get.calls) == 2 and _discovered(catalog) == []  # asked again; the failure dropped its ids
    get.replies[_LOCAL] = _ids("b")
    await catalog.refresh()  # no time passed: a failure is never fresh
    assert len(get.calls) == 3 and _discovered(catalog) == ["local/b"]


async def test_what_was_kept_is_read_however_old_and_an_endpoint_taken_out_is_forgotten(
    tmp_path: Path,
) -> None:
    clock, get = _Clock(), FakeGet({_LOCAL: _ids("a")})
    catalog = _catalog(tmp_path, get, clock=clock)
    await catalog.refresh()
    clock.now += 3600
    assert _discovered(catalog) == ["local/a"]  # no reader expires it; only a refresh asks again
    (tmp_path / "models.toml").write_text("")
    await catalog.refresh()
    assert _discovered(catalog) == [] and catalog.endpoints() == []
    (tmp_path / "models.toml").write_text(_FILE)
    assert _discovered(catalog) == []  # what it listed is gone, not kept for a return
    await catalog.refresh()
    assert len(get.calls) == 2 and _discovered(catalog) == ["local/a"]


async def test_two_refreshes_at_once_ask_once(tmp_path: Path) -> None:
    gate = asyncio.Event()
    get = FakeGet({_LOCAL: _ids("a")}, gate)
    catalog = _catalog(tmp_path, get)
    first, second = asyncio.create_task(catalog.refresh()), asyncio.create_task(catalog.refresh())
    for _ in range(5):
        await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(first, second)
    assert len(get.calls) == 1 and _discovered(catalog) == ["local/a"]


async def test_the_model_row_s_and_the_default_are_listed_before_anything_is_asked(tmp_path: Path) -> None:
    text = 'default = "local/qwen2.5-coder:7b"\n' + _FILE
    get = FakeGet({_LOCAL: _ids("other")})
    catalog = _catalog(tmp_path, get, text)
    (pinned,) = [m for m in catalog.listed() if "/" in m["name"]]
    assert (
        pinned["name"] == "local/qwen2.5-coder:7b"
        and pinned["current"]
        and pinned["default"] == "the models file"
    )
    assert catalog.current() == {"name": "local/qwen2.5-coder:7b", "provider": "openai"}
    await catalog.refresh()
    assert _discovered(catalog) == ["local/other", "local/qwen2.5-coder:7b"]  # the server's list adds to it
    switched = _catalog(tmp_path, get, text, default="local/chosen:1b")
    names = {m["name"]: m for m in switched.listed()}
    assert names["local/chosen:1b"]["current"] and "default" not in names["local/chosen:1b"]
    assert names["local/qwen2.5-coder:7b"]["default"] == "the models file"


async def test_a_refresh_that_can_not_be_made_is_no_error(tmp_path: Path) -> None:
    get = FakeGet({})
    other = Catalog(_Loader(_Entry("model", "some:fake", {})), get=get, clock=_Clock())  # not models:model
    await other.refresh()
    broken = _catalog(tmp_path, get, "[local\n")  # a models file that is not TOML: `problem` says so
    await broken.refresh()
    assert get.calls == []
    assert [m["name"] for m in broken.listed()] == ["sonnet", "opus", "haiku"]  # the built-ins, no raise
    assert broken.problem is not None and "is not TOML" in broken.problem
