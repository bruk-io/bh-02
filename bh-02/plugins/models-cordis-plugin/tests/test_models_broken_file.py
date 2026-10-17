"""A models file that can't be used, and a default that can't: what the model row, the catalog (`/model`'s
list, the status bar's model) and `/model NAME` say and still do (TASK-0093).

The file is one problem for the whole file (not TOML, a key that is no table, a path that can't be
read): the model row's `extra` stays usable behind it, as behind a file refused in the project, so
`/model` of one of its models gets the person out (there are no built-in models to fall back on). A
default that is no name, or names no model, or whose table has a problem, is TASK-0087's
`Unusable`, said with what to write, and the file's other models and `extra` are untouched."""

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
    Unusable,
    model_list,
    opened,
    resolved,
    set_model,
)

_LLAMA = (
    '[ollama]\nprovider = "openai"\nbase_url = "http://localhost:11434/v1"\nmodels.llama.id = "llama3.2"\n'
)
_ENDPOINT = '[local]\nprovider = "openai"\ndiscover = true\nbase_url = "http://localhost:1234/v1"\n'
# the model row's own endpoint, which a layer gives it: usable whatever the models file says
_EXTRA = {"sub": {"provider": "claude-code", "models": {"haiku": {"id": "haiku"}}}}

# What can't be read: its text (bytes when it is not text), and what the row says of it.
_UNREAD: dict[str, tuple[str | bytes | None, str, str]] = {
    "not toml": ("default = [\n", "is not TOML", "fix it"),
    "a key that is no table": ('llama = "x"\n', "'llama' is not a table", "each endpoint is one, e.g."),
    "not UTF-8 text": ('default = "llama"\n'.encode("utf-16"), "is not UTF-8 text", "fix it or remove it"),
    "a directory": (None, "can't read the models file", "fix it or remove it"),
}
# A default that can't be used: the file's text, and what the row says of it.
_BAD_DEFAULTS = {
    "a number": ("default = 5\n" + _LLAMA, "is 5, not a model's name"),
    "an empty string": ('default = ""\n' + _LLAMA, "is '', not a model's name"),
    "a list": ('default = ["llama"]\n' + _LLAMA, "not a model's name"),
    "no model": ('default = "gone"\n' + _LLAMA, "no model named 'gone', the default in the models file"),
    "a broken endpoint's model": (
        'default = "local/x:7b"\n' + _ENDPOINT.replace("true\n", 'true\nid = "y"\n') + _LLAMA,
        "names an id, as a single model's table did",
    ),
}


@dataclass
class _Entry:
    id: str
    use: str | None
    config: dict[str, Any]


class _Loader:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def entries(self) -> list[_Entry]:
        return [_Entry("model", "models:model", self.config)]


class _Fake:
    """A loader whose model row is another component (a fake a `--patch` names)."""

    def entries(self) -> list[_Entry]:
        return [_Entry("model", "bh_02.testing:echo_model", {})]


def _file(tmp_path: Path, text: str | bytes | None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "models.toml"
    if text is None:
        path.mkdir()  # a path that can't be read as a file
    elif isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    return path


def _catalog(path: Path, **config: Any) -> Catalog:
    return Catalog(_Loader({"models": str(path), **config}))


@pytest.mark.parametrize("kind", _UNREAD)
async def test_a_file_that_can_not_be_read_is_the_row_s_error_but_the_row_s_extra_stays_usable(
    tmp_path: Path, kind: str
) -> None:
    text, fragment, todo = _UNREAD[kind]
    path = _file(tmp_path, text)
    config = ModelConfig(models=str(path))
    with pytest.raises(ModelsError) as raised:  # no layer names a model: the file's default is unknown
        resolved(config)
    assert raised.value.kind == "models_file" and fragment in raised.value.message
    assert todo in raised.value.message  # what to do
    async with opened(config) as value:
        assert isinstance(value, Unusable) and value.error.message == raised.value.message
    chosen = ModelConfig(models=str(path), default="sub/haiku", extra=_EXTRA)
    assert resolved(chosen).name == "sub/haiku"  # a layer's choice of its own model runs
    values = _catalog(path, extra=_EXTRA)
    assert values.check("sub/haiku") is None  # so /model sub/haiku gets the person out
    assert "no model named 'ollama/llama'" in str(values.check("ollama/llama"))
    assert fragment in str(values.check("ollama/llama"))  # and the file's problem is said with it
    assert [m["name"] for m in values.listed()] == ["sub/haiku"]  # never a raise
    assert values.problem is not None and fragment in values.problem
    assert "only the model row's `extra` is offered" in values.problem
    assert _catalog(path).listed() == []  # with no extra, nothing: the problem says what to fix


@pytest.mark.parametrize("kind", _UNREAD)
def test_the_status_bar_and_the_list_say_a_file_that_can_not_be_read(tmp_path: Path, kind: str) -> None:
    text, fragment, todo = _UNREAD[kind]
    path = _file(tmp_path, text)
    now = _catalog(path).current()  # the file's default is unknown, so the row has no model: never blank
    assert now["name"] == "default" and now["provider"] == "" and fragment in now["unusable"]
    chosen = _catalog(path, default="sub/haiku", extra=_EXTRA).current()
    assert chosen == {"name": "sub/haiku", "provider": "claude-code"}  # a layer's choice is usable
    values = _catalog(path, extra=_EXTRA)
    said = model_list(values.listed(), values.path, values.problem)
    assert said.startswith("  sub/haiku") and "\n/model NAME switches; only the model row's `extra`" in said
    assert fragment in said  # the file's problem, as the footer


@pytest.mark.parametrize("kind", _BAD_DEFAULTS)
async def test_a_default_that_can_not_be_used_is_the_row_s_error_and_everything_else_still_works(
    tmp_path: Path, kind: str
) -> None:
    text, fragment = _BAD_DEFAULTS[kind]
    path = _file(tmp_path, text)
    config = ModelConfig(models=str(path))
    with pytest.raises(ModelsError) as raised:
        resolved(config)
    assert fragment in raised.value.message
    async with opened(config) as value:
        assert isinstance(value, Unusable)  # TASK-0087: bound, so bh-02 starts; each step says why
    assert resolved(ModelConfig(models=str(path), default="sub/haiku", extra=_EXTRA)).name == "sub/haiku"
    values = _catalog(path, extra=_EXTRA)
    assert values.check("sub/haiku") is None and values.check("ollama/llama") is None  # /model fixes it
    assert values.problem is None  # the file itself reads fine
    why = values.default_problem
    assert why is not None and fragment in why  # /model's list says the default was refused
    said = model_list(values.listed(), values.path, values.problem, default_problem=why)
    assert f"  the models file's default is refused: {why}\n/model NAME switches" in said


@pytest.mark.parametrize("kind", _BAD_DEFAULTS)
def test_the_status_bar_names_a_default_that_can_not_be_used_and_says_it_is_unusable(
    tmp_path: Path, kind: str
) -> None:
    text, fragment = _BAD_DEFAULTS[kind]
    now = _catalog(_file(tmp_path, text)).current()
    assert now["name"] and now["provider"] == ""  # never blank
    assert fragment.split(",")[0] in now["unusable"] or "not a model's name" in now["unusable"]
    assert set(now) == {"name", "provider", "unusable"}


def test_the_name_the_status_bar_shows_is_the_default_s_own_text_when_it_is_one(tmp_path: Path) -> None:
    assert _catalog(_file(tmp_path, 'default = "gone"\n')).current()["name"] == "gone"
    assert _catalog(_file(tmp_path, "default = 5\n")).current()["name"] == "default"  # no name to show


def test_a_default_a_session_recorded_from_the_file_says_it_came_from_the_file(tmp_path: Path) -> None:
    """`sessions.create` pins the file's default into the session's layer; if it names no model, the
    row's error must still say the models file's default is the cause, not 'the model row's default'."""
    path = _file(tmp_path, 'default = "gone"\n' + _LLAMA)
    with pytest.raises(ModelsError, match="no model named 'gone', the default in the models file"):
        resolved(ModelConfig(models=str(path), default="gone"))  # what the session's layer recorded
    with pytest.raises(ModelsError) as other:  # a name of the person's own, not the file's default
        resolved(ModelConfig(models=str(path), default="typo"))
    assert "the default in the models file" not in other.value.message
    assert _catalog(path, default="gone").current()["unusable"].count("the default in the models file") == 1


def test_a_default_that_is_fine_or_absent_or_not_read_has_no_problem_to_say(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _catalog(_file(tmp_path / "a", 'default = "ollama/llama"\n' + _LLAMA)).default_problem is None
    assert _catalog(_file(tmp_path / "b", _LLAMA)).default_problem is None  # none given: the row says it
    assert _catalog(tmp_path / "none.toml").default_problem is None  # no file at all
    unread = _catalog(_file(tmp_path / "c", "default = [\n"))
    assert unread.default_problem is None and unread.problem is not None  # the file is the problem
    project = tmp_path / "project"
    (project / ".config" / "bh-02").mkdir(parents=True)
    (project / ".config" / "bh-02" / "models.toml").write_text('default = "gone"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(project / ".config"))
    in_project = Catalog(_Loader({"cwd": str(project)}))
    assert in_project.default_problem is None and in_project.problem is not None  # not read: no default
    fake = Catalog(_Fake())  # a row that is another component has no models: nothing to say
    assert fake.default_problem is None


def test_a_usable_model_has_no_unusable_mark(tmp_path: Path) -> None:
    path = _file(tmp_path, 'default = "ollama/llama"\n' + _LLAMA)
    assert _catalog(path).current() == {"name": "ollama/llama", "provider": "openai"}
    assert _catalog(path, default="typo").current()["unusable"].startswith("no model named 'typo'")


async def _switch(path: Path, tmp_path: Path, name: str, **config: Any) -> tuple[Any, list[Any], Path]:
    layer = tmp_path / "session.toml"
    layer.write_text('[[plugin]]\nid = "model"\nconfig = { state = "/s/claude" }\n')
    queued: list[Any] = []

    class _Jobs:
        def put(self, job: Any, failed: Any) -> None:
            queued.append(job)

    class _Reloads:
        def status(self) -> dict[str, str]:
            return {"model": "active"}

        async def reload(self) -> None: ...

    values = _catalog(path, **config)
    answer = await Switch(_Reloads(), values, SwitchConfig(layer=str(layer)), _Jobs(), set_model).run(name)
    return answer, queued, layer


_ENDPOINT_PROBLEMS = {
    "an id beside discover": _ENDPOINT.replace("true\n", 'true\nid = "y"\n'),  # a single model's table
    "discover that is no bool": _ENDPOINT.replace("true", '"yes"'),
    "include with no discover": _ENDPOINT.replace("discover = true\n", 'include = ["q*"]\n'),
    "an include that is no list": _ENDPOINT + 'include = "q*"\n',
    "a slash in the endpoint's name": _ENDPOINT.replace("[local]", '["lo/cal"]'),
}


_BROKEN_KINDS = [*_ENDPOINT_PROBLEMS, *_BAD_DEFAULTS, *_UNREAD, "table and default"]
# every kind of breakage with the row's `extra` model to switch to, and (but a file that can't be
# read) a file model
_SWITCHES = [(kind, "sub/haiku") for kind in _BROKEN_KINDS] + [
    (kind, "ollama/llama") for kind in _BROKEN_KINDS if kind not in _UNREAD
]


@pytest.mark.parametrize(("kind", "target"), _SWITCHES)
async def test_model_name_of_a_valid_model_still_switches_while_a_table_or_the_default_is_broken(
    tmp_path: Path, kind: str, target: str
) -> None:
    """TASK-0095's close review: `/model NAME` of a model that is fine switches whatever else in the
    models file is broken: a table, the file's default, the file itself (the row's `extra` then), both."""
    if kind in _ENDPOINT_PROBLEMS:
        text: str | None = _ENDPOINT_PROBLEMS[kind] + _LLAMA
    elif kind in _BAD_DEFAULTS:
        text = _BAD_DEFAULTS[kind][0]
    elif kind in _UNREAD:
        text = _UNREAD[kind][0]
    else:
        text = 'default = "gone"\n' + _ENDPOINT_PROBLEMS["an id beside discover"] + _LLAMA
    answer, queued, layer = await _switch(_file(tmp_path, text), tmp_path, target, extra=_EXTRA)
    assert [type(a) for a in answer] == [dict, dict] and f"switching to {target}" in str(answer[0]["text"])
    (row,) = read_layer(layer)
    assert (row.config or {})["default"] == target  # recorded in the session's layer
    assert len(queued) == 1  # and the reload is queued


@pytest.mark.parametrize("kind", _ENDPOINT_PROBLEMS)
async def test_a_model_of_a_broken_endpoint_is_still_refused_with_its_problem(
    tmp_path: Path, kind: str
) -> None:
    answer, queued, layer = await _switch(
        _file(tmp_path, _ENDPOINT_PROBLEMS[kind] + _LLAMA), tmp_path, "local/x:7b"
    )
    assert isinstance(answer, str) and answer.startswith("not switched: ") and queued == []
    assert "default" not in (read_layer(layer)[0].config or {})
