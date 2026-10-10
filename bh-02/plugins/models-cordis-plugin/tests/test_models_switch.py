"""`/model`, beside the catalog it reads: listing the models, switching by name in the session's
layer, and the row that registers it on a runtime."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cordis import Effects, Row, Runtime, bind, component
from cordis.loader import read_layer
from models_cordis_plugin import Switch, SwitchConfig, model_list, set_model, shadowing, switch


class _Loader:
    def __init__(self) -> None:
        self.reloads = 0
        self.rows = {"loop": "active", "model": "active"}

    def status(self) -> dict[str, str]:
        return dict(self.rows)

    async def reload(self) -> None:
        self.reloads += 1


class _Models:
    """The `models` value: two Claude models and a local one, haiku the model row's now."""

    path = "/home/me/.config/bh-02/models.toml"

    def __init__(self) -> None:
        self.now = "haiku"
        self.broken = False
        self.problem: str | None = None  # why the models file is not read (it is in the project)

    def listed(self) -> list[dict[str, Any]]:
        if self.broken:
            raise ValueError("the models file is not TOML")
        return [
            {"name": "sonnet", "provider": "claude-code", "id": "sonnet", "current": self.now == "sonnet"},
            {"name": "haiku", "provider": "claude-code", "id": "haiku", "current": self.now == "haiku"},
            {
                "name": "llama",
                "provider": "openai",
                "id": "llama3.2",
                "current": False,
                "where": "http://localhost:11434/v1",
            },
            {
                "name": "typo",
                "provider": "",
                "id": "",
                "current": False,
                "problem": "model 'typo' names no provider",
            },
        ]

    def current(self) -> dict[str, str]:
        return {"name": self.now, "provider": "claude-code"}

    def check(self, name: str) -> str | None:
        known = {m["name"]: m for m in self.listed()}
        if name not in known:
            return f"no model named {name!r}"
        return known[name].get("problem")


class _Jobs:
    """The `jobs` value as `/model` needs it: each reload queued, with what the person would be
    told if it failed; `drain` runs them, as the jobs row would after the answer."""

    def __init__(self) -> None:
        self.queued: list[tuple[Any, Any]] = []
        self.told: list[str] = []

    def put(self, job: Any, failed: Any) -> None:
        self.queued.append((job, failed))

    def empty(self) -> bool:
        return not self.queued


async def _drain(jobs: _Jobs) -> None:
    while jobs.queued:
        job, failed = jobs.queued.pop(0)
        try:
            await job()
        except Exception as error:
            jobs.told.append(failed(f"{type(error).__name__}: {error}"))


async def test_model_lists_the_models_and_switches_by_name_in_the_session_s_layer(tmp_path: Path) -> None:
    layer = tmp_path / "session.toml"
    layer.write_text('[[plugin]]\nid = "model"\nconfig = { state = "/s/claude" }\n')
    calls: list[tuple[str, str, str]] = []
    loader, jobs, models = _Loader(), _Jobs(), _Models()
    run = Switch(loader, models, SwitchConfig(layer=str(layer)), jobs, lambda *a: calls.append(a)).run
    assert str(await run("")).splitlines() == [
        "  sonnet  claude-code  sonnet",
        "● haiku   claude-code  haiku",
        "  llama   openai       llama3.2  at http://localhost:11434/v1",
        "  typo",
        "    model 'typo' names no provider",
        f"/model NAME switches; add models in {models.path}",
    ]
    assert await run("haiku") == "model: haiku already; nothing to switch"
    assert await run("gpt-9") == "not switched: no model named 'gpt-9'"
    assert await run("typo") == "not switched: model 'typo' names no provider"
    assert calls == [] and jobs.empty()  # nothing changed: no reload, no restart announced
    note, restarting = await run("llama")  # across providers, by name
    assert isinstance(note, dict) and str(note["text"]).startswith("switching to llama")
    assert restarting == {"type": "restarting", "rows": ["model"]}  # the ui holds lines for it
    assert calls == [(str(layer), "model", "llama")] and loader.reloads == 0  # queued, not run here
    await _drain(jobs)
    assert loader.reloads == 1  # the layers are read again now, not when the watcher next looks
    for bad in ("/model sonnet-x", "/sonnet", "sonnet x"):  # a command typed twice, two words
        assert str(await run(bad)).startswith(f"not a model name: {bad!r}; type /model and one name")
    assert calls == [(str(layer), "model", "llama")]  # none of them was recorded
    unsessioned = Switch(_Loader(), _Models(), SwitchConfig(), _Jobs(), lambda *a: None)
    assert "no session layer" in str(await unsessioned.run("x"))
    set_model(str(layer), "model", "llama")
    (row,) = read_layer(layer)
    assert row == Row("model", config={"state": "/s/claude", "default": "llama"})


async def test_model_refuses_when_a_later_layer_sets_the_model_row_s_config(tmp_path: Path) -> None:
    """A `--patch` that sets the model row's config replaces the session layer's whole: /model
    would record a name that never runs, so it says so and records nothing."""
    base, layer, patch, other = (tmp_path / n for n in ("base.toml", "session.toml", "p.toml", "q.toml"))
    base.write_text('[[plugin]]\nid = "model"\nuse = "models:model"\n')
    layer.write_text('[[plugin]]\nid = "model"\nconfig = { default = "haiku" }\n')
    patch.write_text('[[plugin]]\nid = "model"\nconfig = { env_file = "/x/local.env" }\n')
    other.write_text('[[plugin]]\nid = "model"\ndisabled = false\n')  # no config: shadows nothing
    files = [str(base), str(layer), str(other), str(patch)]
    assert shadowing(files, str(layer), "model") == str(patch)
    assert shadowing(files[:3], str(layer), "model") is None
    assert shadowing([str(patch), str(layer)], str(layer), "model") is None  # before it: overridden by it
    calls: list[tuple[str, str, str]] = []
    jobs = _Jobs()
    chosen = Switch(
        _Loader(),
        _Models(),
        SwitchConfig(layer=str(layer)),
        jobs,
        lambda *a: calls.append(a),
        lambda mine, rid: shadowing(files, mine, rid),
    )
    assert await chosen.run("llama") == (
        f"not switched: {patch} sets the 'model' row's config, which replaces the session's (where "
        "/model records the model) whole, so the model that file names stays. Set "
        "`default = \"llama\"` in that file's 'model' row, or run without it"
    )
    assert calls == [] and jobs.empty()


def test_the_model_command_offers_each_usable_model_as_a_choice() -> None:
    models = _Models()
    spec = Switch(_Loader(), models, SwitchConfig(), _Jobs(), lambda *a: None).spec()
    choices = spec["choices"]()
    assert [c["args"] for c in choices] == ["sonnet", "haiku", "llama"]  # not the one with a problem
    assert choices[0]["help"] == "switch to sonnet (claude-code: sonnet)"
    assert choices[1]["help"] == "the model now (claude-code: haiku)"
    models.broken = True
    assert spec["choices"]() == []  # read each time; a broken file offers none, /model says why


def test_the_model_list_marks_a_shadowed_built_in() -> None:
    listed = [
        {
            "name": "sonnet",
            "provider": "openai",
            "id": "x",
            "current": True,
            "shadows": "shadows the built-in 'sonnet' (f)",
        }
    ]
    assert model_list(listed, "f").splitlines()[:2] == [
        "● sonnet  openai  x",
        "    shadows the built-in 'sonnet' (f)",
    ]


async def test_the_model_list_says_why_the_models_file_is_not_read_instead_of_where_to_add() -> None:
    """A models file in the project is not read: /model says so where it would say to add models
    there, and still lists the models there are."""
    models = _Models()
    models.problem = "the models file /p/.config/bh-02/models.toml is not read: it is in the project (/p)"
    chosen = Switch(_Loader(), models, SwitchConfig(), _Jobs(), lambda *a: None)
    said = str(await chosen.run("")).splitlines()
    assert said[0] == "  sonnet  claude-code  sonnet"
    assert said[-1] == f"/model NAME switches; {models.problem}" and "add models in" not in said[-1]


class _Commands:
    """A `commands` value that keeps what is registered, and takes it back on removal."""

    def __init__(self) -> None:
        self.runs: dict[str, Any] = {}

    def register(self, spec: dict[str, Any], run: Any) -> Any:
        self.runs[spec["name"]] = run
        return lambda: self.runs.pop(spec["name"], None)


class _Failing(_Loader):
    async def reload(self) -> None:
        raise RuntimeError("the layer does not parse")


async def test_the_switch_row_registers_model_and_queues_the_reload_in_jobs(tmp_path: Path) -> None:
    """The reload `/model NAME` asks for is queued in `jobs`, run after the command answered,
    with what the person is told if it fails."""
    layer = tmp_path / "session.toml"
    layer.write_text('[[plugin]]\nid = "model"\nconfig = { default = "haiku" }\n')
    commands, jobs, loader = _Commands(), _Jobs(), _Failing()

    @component(provides=("commands", "loader", "models", "jobs"))
    async def around() -> Effects:
        yield bind("commands", commands)
        yield bind("loader", loader)
        yield bind("models", _Models())
        yield bind("jobs", jobs)

    rt = Runtime()
    rt.mount(around, id="around")
    rt.mount(switch, id="switch", config=SwitchConfig(layer=str(layer)))
    await rt.settle()
    answer: Sequence[Any] = await commands.runs["model"]("sonnet")
    assert answer[0]["text"].startswith("switching to sonnet")
    assert read_layer(layer) == [Row("model", config={"default": "sonnet"})]
    await _drain(jobs)
    (told,) = jobs.told
    assert told.startswith("the model switch's reload failed (RuntimeError: the layer does not parse)")
    await rt.shutdown()
    assert commands.runs == {}
