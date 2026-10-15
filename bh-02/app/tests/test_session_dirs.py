"""Sessions: the layer a session runs from, the state directory, and resuming from the CLI."""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import CliRunner

from bh_02 import main
from bh_02.sessions import (
    Broken,
    Session,
    create,
    default_state_root,
    find,
    listed,
    scanned,
    session_layer,
    set_model,
    state_root,
    with_model,
)
from cordis import Row
from cordis.loader import read_layer
from models_cordis_plugin import ModelConfig, ModelsError, opened, resolved
from models_cordis_plugin.openai.testing import StubServer


@pytest.fixture(autouse=True)
def _own_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A new session reads the models file's `default`: these tests use an empty config directory,
    never the one of whoever runs them."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config" / "bh-02"


def _models_default(config: Path, text: str) -> None:
    config.mkdir(parents=True, exist_ok=True)
    (config / "models.toml").write_text(text)


def _recorded(session: Session) -> str | None:
    (row,) = [r for r in read_layer(str(session.layer)) if r.id == "model"]
    return (row.config or {}).get("default")


def test_a_new_session_records_the_models_file_s_default_and_a_resume_keeps_it(
    _own_config: Path, tmp_path: Path
) -> None:
    """The session's layer names the model it started on, so changing the file's `default`
    later moves new sessions only."""
    _models_default(
        _own_config,
        'default = "local/llama"\n[local]\nprovider = "openai"\nbase_url = "http://localhost:1/v1"\n'
        '[local.models.llama]\nid = "x"\n',
    )
    first = create(tmp_path / "s", "/work/a", model=None, no_jail=False)
    assert _recorded(first) == "local/llama" and first.stack == "local/llama"
    assert json.loads((first.dir / "meta.json").read_text())["stack"] == "local/llama"
    _models_default(_own_config, 'default = "opus"\n')
    assert _recorded(first) == "local/llama"  # still on the first model
    assert _recorded(create(tmp_path / "s", "/work/a", model=None, no_jail=False)) == "opus"
    assert _recorded(create(tmp_path / "s", "/work/a", model="haiku", no_jail=False)) == "haiku"  # --model


async def test_a_models_file_default_of_an_endpoint_s_model_starts_the_session_on_it_with_no_listing_asked(
    _own_config: Path, tmp_path: Path
) -> None:
    """TASK-0087 and TASK-0088 together: `default = "local/x:7b"` over an endpoint that lists its
    models. The session's layer and meta name it; the model row resolves it and runs a step, and the
    server is never asked for its list."""
    with StubServer(models=["listed-but-not-chosen"]) as server:
        _models_default(
            _own_config,
            'default = "local/x:7b"\n[local]\nprovider = "openai"\ndiscover = true\n'
            f'base_url = "{server.base_url}"\n',
        )
        made = create(tmp_path / "s", "/work/a", model=None, no_jail=False)
        assert _recorded(made) == "local/x:7b" and made.stack == "local/x:7b"
        assert json.loads((made.dir / "meta.json").read_text())["stack"] == "local/x:7b"
        config = ModelConfig(default=_recorded(made))  # the model row of the session's layer
        assert resolved(config).id == "x:7b"
        async with opened(config) as model:
            chunks = [c async for c in model.complete([{"role": "user", "content": "hi"}], [])]
        assert any(c.get("type") == "text" for c in chunks)
    assert [(r["method"], r["path"]) for r in server.requests] == [("POST", "/v1/chat/completions")]
    assert server.requests[0]["body"]["model"] == "x:7b"  # zero GETs: the endpoint's list was never asked


async def test_the_model_flag_naming_a_model_of_a_broken_endpoint_starts_the_session_and_its_model_says_why(
    _own_config: Path, tmp_path: Path
) -> None:
    """TASK-0095: `--model local/x:7b` over an endpoint table with a problem (an id of its own) is
    recorded as it is typed; the model row still binds, so bh-02 starts, and refuses each step with the
    table's problem. Nothing is asked of the server."""
    with StubServer(models=["x:7b"]) as server:
        _models_default(
            _own_config,
            f'[local]\nprovider = "openai"\ndiscover = true\nid = "x"\nbase_url = "{server.base_url}"\n',
        )
        made = create(tmp_path / "s", "/work/a", model="local/x:7b", no_jail=False)
        assert _recorded(made) == "local/x:7b"
        async with opened(ModelConfig(default=_recorded(made))) as model:
            with pytest.raises(ModelsError, match="names an id, as a single model's table did") as step:
                [c async for c in model.complete([{"role": "user", "content": "hi"}], [])]
        assert step.value.message.startswith("endpoint 'local' (")
    assert server.requests == []


def test_a_model_name_above_u_ffff_is_recorded_in_the_layer_and_read_back_as_typed(tmp_path: Path) -> None:
    """TASK-0094: `--model local/<id>` (and a resume's `--model`) takes any id after the endpoint, and
    cordis's `format_layer` wrote a character above U+FFFF as an escape TOML refuses, which left the
    session a layer the loader can't read."""
    name = "local/llama-\U0001f999"
    made = create(tmp_path / "s", "/work/a", model=name, no_jail=False)
    assert _recorded(made) == name and made.stack == name
    assert json.loads((made.dir / "meta.json").read_text())["stack"] == name
    other = "local/\U0001f999-2"
    set_model(made, other)  # a resume with --model rewrites the layer the same way
    assert _recorded(made) == other


def test_a_new_session_with_no_file_default_records_no_model_and_the_row_says_what_to_write(
    _own_config: Path, tmp_path: Path
) -> None:
    """There are no built-in models: with nothing naming one, the session records none, and the model
    row says no model is chosen and what to add."""
    made = create(tmp_path / "s", "/work/a", model=None, no_jail=False)
    assert _recorded(made) is None and made.stack == "default"
    with pytest.raises(ModelsError, match="no model is chosen") as said:
        resolved(ModelConfig(default=_recorded(made)))
    assert said.value.kind == "unknown_model"


@pytest.mark.parametrize(
    "text",
    ["default = [\n", 'llama = "x"\n', "default = 5\n", 'default = ""\n', 'default = ["opus"]\n'],
    ids=["not TOML", "a key that is no table", "a number", "an empty string", "a list"],
)
def test_a_models_file_that_is_not_toml_or_whose_default_is_no_name_pins_no_model(
    _own_config: Path, tmp_path: Path, text: str
) -> None:
    """TASK-0087's `Unusable` must show: a pinned model would hide that the file's default can't be
    read, so the session's layer names no model and the model row says what is wrong with the file."""
    _models_default(_own_config, text)
    made = create(tmp_path / "s", "/work/a", model=None, no_jail=False)
    assert _recorded(made) is None and made.stack == "default"  # follows the file's default
    assert json.loads((made.dir / "meta.json").read_text())["stack"] == "default"
    assert [(s.id, s.stack) for s in listed(tmp_path / "s", "/work/a")] == [(made.id, "default")]
    with pytest.raises(ModelsError) as said:  # the row's error, with what to write
        resolved(ModelConfig(default=_recorded(made)))
    assert said.value.kind == "models_file"


def test_a_default_that_names_no_model_is_pinned_and_the_row_says_the_file_s_default_is_the_cause(
    _own_config: Path, tmp_path: Path
) -> None:
    _models_default(_own_config, 'default = "nosuch"\n')
    made = create(tmp_path / "s", "/work/a", model=None, no_jail=False)
    assert _recorded(made) == "nosuch" and made.stack == "nosuch"
    with pytest.raises(ModelsError, match="no model named 'nosuch', the default in the models file"):
        resolved(ModelConfig(default=_recorded(made)))


def test_a_models_file_in_the_project_gives_a_new_session_no_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default chooses the spend: a file the model's code can write does not choose it."""
    project = tmp_path / "project"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(project / ".config"))
    _models_default(project / ".config" / "bh-02", _OPUS)
    made = create(tmp_path / "s", str(project), model=None, no_jail=False)
    assert _recorded(made) is None and made.stack == "default"


def _outcome(config: ModelConfig) -> tuple[str, str]:
    """What the model row makes of `config`, by its public surface: a model's name, or its error's kind."""
    try:
        return "model", resolved(config).name
    except ModelsError as error:
        return "error", error.kind


@dataclass(frozen=True)
class _Case:
    """A models file, where it is, and what a new session starts on: `text` (None: no file; a directory
    stands in for the file when it is `DIRECTORY`), what `create` records (`pin`: None, no model) and
    whether the row can then use the model (`works`). `where`: outside the project, in it as named, in it
    through a link, or in it while `create` is told another directory than the working one."""

    text: str | None
    pin: str | None
    works: bool = True
    where: str = "outside"


_DIRECTORY = "<a directory>"
_ENDPOINT = '[local]\nprovider = "openai"\ndiscover = true\nbase_url = "http://localhost:1/v1"\n'
_OPUS = 'default = "cc/opus"\n[cc]\nprovider = "claude-code"\nmodels.opus.id = "opus"\n'
_CONTRACT = {
    "a trusted default": _Case(_OPUS, "cc/opus"),
    "no file": _Case(None, None, works=False),  # no built-in models: nothing is chosen
    "a default table, which is an endpoint": _Case(
        '[default]\nprovider = "claude-code"\nmodels.opus.id = "opus"\n', None, works=False
    ),
    "an endpoint's model": _Case('default = "local/x:7b"\n' + _ENDPOINT, "local/x:7b"),
    "no model": _Case('default = "nosuch"\n', "nosuch", works=False),
    "not TOML": _Case("default = [\n", None, works=False),
    "a key that is no table": _Case('llama = "x"\n', None, works=False),
    "a number": _Case("default = 5\n", None, works=False),
    "an empty string": _Case('default = ""\n', None, works=False),
    "a list": _Case('default = ["opus"]\n', None, works=False),
    "a directory": _Case(_DIRECTORY, None, works=False),
    # the default chooses the spend: a file the model's code can write chooses nothing, however it is reached
    "in the project": _Case(_OPUS, None, works=False, where="project"),
    "through a link into the project": _Case(_OPUS, None, works=False, where="link"),
    "in the project, create told another directory": _Case(_OPUS, None, works=False, where="elsewhere"),
}


def _placed(case: _Case, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Put the case's models file in an XDG config directory (outside the project, in it, or reached
    through a link into it), make the project the working directory, and return the directory `create`
    is told is the session's."""
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    config = project / ".config" if case.where in ("project", "elsewhere") else tmp_path / "config"
    models = config / "bh-02"
    if case.where == "link":  # the config directory's `bh-02` is a link into the project
        models = project / "real"
        config.mkdir()
        (config / "bh-02").symlink_to(models)
    models.mkdir(parents=True)
    if case.text == _DIRECTORY:
        (models / "models.toml").mkdir()
    elif case.text is not None:
        (models / "models.toml").write_text(case.text)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    return str(tmp_path / "elsewhere") if case.where == "elsewhere" else str(project)


@pytest.mark.parametrize("kind", _CONTRACT)
def test_the_shell_and_the_model_row_agree_on_what_a_new_session_starts_on(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-0093: the shell (`create`) and the model row each decide whether the models file is
    trusted and what its default is, and cannot share a function (no package imports another). This
    drives both over the same files, by their public surfaces, and fails if they disagree on what a
    new session starts on: what `create` records in the session's layer must make the row resolve
    what it would with the layer naming none (a model, or the same error), whatever the file is: in
    the project, not TOML, a default that is no name, one that names no model, an endpoint's model."""
    case = _CONTRACT[kind]
    made = create(tmp_path / "s", _placed(case, tmp_path, monkeypatch), model=None, no_jail=False)
    assert _recorded(made) == case.pin and made.stack == (case.pin or "default")
    row = _outcome(ModelConfig(default=_recorded(made)))  # the session's layer, as the row reads it
    assert row == _outcome(ModelConfig())  # the one thing that must hold: the shell and the row agree
    assert row[0] == ("model" if case.works else "error")  # and the cases are what they claim to be


def test_a_session_s_layer_keeps_a_transcript_and_names_its_model_on_the_model_row() -> None:
    rows = session_layer(Path("/s/1"), model="haiku", no_jail=True)
    assert rows == [
        Row("ui", config={"history": "/s/1/events.jsonl"}),  # what the ui showed, drawn again on a resume
        Row("transcript", config={"path": "/s/1/transcript.jsonl"}),  # what the model is sent again
        Row("switch", config={"layer": "/s/1/session.toml", "model_row": "model"}),  # /model edits it
        # Claude Code's own state (its session, which a resume continues) in the session's directory
        Row("model", config={"state": "/s/1/claude", "default": "haiku"}),
        Row("runner", "runner:unconfined"),
    ]
    assert session_layer(Path("/s/2"), model=None, no_jail=False)[-1] == Row(
        "model", config={"state": "/s/2/claude"}
    )  # no --model: no default here (the models file's, else none), and the jail the harness ships


def test_choosing_a_model_keeps_the_row_s_other_config() -> None:
    rows = [Row("model", config={"state": "/s"}), Row("runner", "runner:unconfined")]
    assert with_model(rows, "opus") == [
        Row("runner", "runner:unconfined"),
        Row("model", config={"state": "/s", "default": "opus"}),
    ]


def test_sessions_are_listed_newest_first_for_their_own_directory(tmp_path: Path) -> None:
    first = create(tmp_path, "/work/a", model=None, no_jail=False)
    second = create(tmp_path, "/work/a", model="opus", no_jail=False)
    create(tmp_path, "/work/b", model=None, no_jail=False)
    assert [s.id for s in listed(tmp_path, "/work/a")] in (
        [second.id, first.id],
        [first.id, second.id],  # made within the same second: order by time alone can't tell
    )
    assert find(tmp_path, "/work/a", first.id) == [first]
    # a prefix names it too: one just long enough to tell it from `second` (made in the same
    # second, whose random end can share its first hex digits)
    shared = next(i for i, (a, b) in enumerate(zip(first.id, second.id, strict=True)) if a != b)
    assert find(tmp_path, "/work/a", first.id[: shared + 1]) == [first]
    assert find(tmp_path, "/work/a", first.id.rsplit("-", 1)[1]) == [first]  # and its last part
    assert find(tmp_path, "/work/a", "nope") == [] and find(tmp_path, "/nowhere", None) == []
    set_model(first, "haiku")
    chosen = next(r for r in read_layer(first.layer) if r.id == "model")
    assert chosen.config == {"state": str(first.dir / "claude"), "default": "haiku"}


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """The sessions go to a temporary state directory, from a temporary working directory."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    yield tmp_path / "state" / "bh-02" / "sessions"


def test_every_run_is_a_session_and_resuming_one_reads_its_history_back(
    composition: Callable[..., Path], state: Path
) -> None:
    patch = composition(
        '[[plugin]]\nid = "model"\nuse = "fragile:counting_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
    )
    runner = CliRunner()
    first = runner.invoke(main, ["--patch", str(patch)])
    assert first.exit_code == 0, first.output
    assert "session " in first.stderr and "bh-02 --resume" in first.stderr
    import fragile

    assert fragile.SHOWN == ["seen 1"]
    assert fragile.FIELDS["jail"].startswith("unjailed")  # the rows over `frame` ran against it
    listing = runner.invoke(main, ["sessions"])
    (session_id,) = [line.split()[0] for line in listing.output.splitlines()]
    assert (state / session_id / "transcript.jsonl").is_file()

    again = runner.invoke(main, ["--resume", "--patch", str(patch)])
    assert again.exit_code == 0, again.output
    assert fragile.FIELDS["session"] == f"{session_id} (resumed)"
    assert fragile.SHOWN == ["seen 1", "seen 2"]  # the resumed session remembered the first message


def test_resume_refuses_what_it_can_t_honour(composition: Callable[..., Path], state: Path) -> None:
    runner = CliRunner()
    nothing = runner.invoke(main, ["--resume"])
    assert (
        nothing.exit_code == 2
        and "no sessions in this directory yet; run bh-02 to start one" in nothing.stderr
    )
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_ui"\n'
    )
    assert runner.invoke(main, ["--patch", str(patch)]).exit_code == 0
    gone = runner.invoke(main, ["--resume", "--ollama"])
    assert gone.exit_code == 2 and "No such option '--ollama'" in gone.stderr  # a models file entry now
    unjailed = runner.invoke(main, ["--resume", "--no-jail"])
    assert unjailed.exit_code == 2 and "keeps the jail" in unjailed.stderr


def test_a_prefix_two_sessions_share_names_both_and_an_exact_id_wins(tmp_path: Path) -> None:
    a = create(tmp_path, "/w", model=None, no_jail=False)
    b = create(tmp_path, "/w", model=None, no_jail=False)
    assert sorted(s.id for s in find(tmp_path, "/w", "2")) == sorted([a.id, b.id])
    assert find(tmp_path, "/w", a.id) == [a]
    longer = create(tmp_path, "/w", model=None, no_jail=False)
    (tmp_path / longer.id).rename(tmp_path / f"{a.id}x")  # an id that `a.id` is a prefix of
    meta = tmp_path / f"{a.id}x" / "meta.json"
    meta.write_text(meta.read_text().replace(longer.id, f"{a.id}x"))
    assert find(tmp_path, "/w", a.id) == [a]  # exact beats prefix


def test_sessions_started_in_the_same_second_still_list_newest_first(tmp_path: Path) -> None:
    made = [create(tmp_path, "/w", model=None, no_jail=False) for _ in range(5)]
    assert [s.id for s in listed(tmp_path, "/w")] == [s.id for s in reversed(made)]


def test_resume_takes_a_prefix_or_the_last_part_and_refuses_an_ambiguous_one(
    composition: Callable[..., Path], state: Path
) -> None:
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_ui"\n'
    )
    runner = CliRunner()
    assert runner.invoke(main, ["--patch", str(patch)]).exit_code == 0
    assert runner.invoke(main, ["--patch", str(patch)]).exit_code == 0
    lines = runner.invoke(main, ["sessions"]).output.splitlines()
    assert all(line.endswith(f"default  patched: {patch.name}") for line in lines)  # not only "default"
    first, second = sorted(line.split()[0] for line in lines)
    import fragile

    resumed = runner.invoke(main, ["--resume", first[:-1], "--patch", str(patch)])
    assert resumed.exit_code == 0, resumed.output
    assert fragile.FIELDS["session"].startswith(f"{first} (resumed")
    tail = second.rsplit("-", 1)[1]  # the short id the status bar shows
    by_tail = runner.invoke(main, ["--resume", tail, "--patch", str(patch)])
    assert by_tail.exit_code == 0, by_tail.output
    assert fragile.FIELDS["session"].startswith(f"{second} (resumed")
    common = next(i for i, (x, y) in enumerate(zip(first, second, strict=True)) if x != y)
    ambiguous = runner.invoke(main, ["--resume", first[:common]])
    assert ambiguous.exit_code == 2 and "give more of one" in ambiguous.stderr
    assert first in ambiguous.stderr and second in ambiguous.stderr


def _plant(root: Path, name: str, content: str) -> Path:
    """A session directory whose meta.json is `content`, as a hand edit or a crash left it."""
    (root / name).mkdir(parents=True)
    (root / name / "meta.json").write_text(content)
    return root / name


_BROKEN = {
    "not-json": ("{not json", "not JSON"),
    "a-list": ("[1, 2]", "not a JSON object"),
    "no-cwd": ('{"id": "no-cwd", "stack": "claude", "created": "2026"}', "`cwd` is missing"),
    "created-int": ('{"id": "x", "cwd": "/w", "stack": "claude", "created": 5}', "`created` is missing"),
    "id-int": ('{"id": 7, "cwd": "/w", "stack": "claude", "created": "2026"}', "`id` is missing"),
    "patches-int": (
        '{"id": "p", "cwd": "/w", "stack": "claude", "created": "2026", "patches": 3}',
        "`patches` is not a list",
    ),
    "stack-empty": ('{"id": "s", "cwd": "/w", "stack": "", "created": "2026"}', "`stack` is missing"),
}


def test_a_broken_record_is_skipped_and_named_with_what_is_wrong(tmp_path: Path) -> None:
    good = create(tmp_path, "/w", model=None, no_jail=False)
    for name, (content, _) in _BROKEN.items():
        _plant(tmp_path, name, content)
    _plant(tmp_path, "elsewhere", '{"id": 1, "cwd": "/other"}')  # another directory's: not ours to judge
    assert listed(tmp_path, "/w") == [good]
    found, broken = scanned(tmp_path, "/w")
    assert found == [good]
    assert {b.id: b.why for b in broken}.keys() == _BROKEN.keys()
    for record in broken:
        assert _BROKEN[record.id][1] in record.why
        assert record.message.startswith(f"session record {record.dir / 'meta.json'} can't be read (")
        assert record.message.endswith(f"); fix it or remove {record.dir}")
    assert find(tmp_path, "/w", None) == [good]  # a bare resume takes the newest readable one
    assert find(tmp_path, "/w", good.id) == [good]
    (named,) = find(tmp_path, "/w", "not-json")  # naming a broken one finds it, to say why
    assert isinstance(named, Broken) and "not JSON" in named.why


def test_with_xdg_state_home_set_the_default_state_root_is_still_known(state: Path) -> None:
    """A run with `XDG_STATE_HOME` set keeps its sessions there, and still knows the default
    root, which `bh_02.cli` hides from a jailed input too (a default run's sessions)."""
    assert state_root() == state
    assert default_state_root() == Path.home() / ".local" / "state" / "bh-02" / "sessions"
