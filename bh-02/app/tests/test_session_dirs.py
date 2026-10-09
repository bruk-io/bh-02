"""Sessions: the layer a session runs from, the state directory, and resuming from the CLI."""

from collections.abc import Callable, Iterator
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
    retired,
    scanned,
    session_layer,
    set_model,
    state_root,
    update,
    with_model,
)
from cordis import Row
from cordis.composition import format_layer
from cordis.loader import read_layer


def test_a_session_s_layer_keeps_a_transcript_and_names_its_model_on_the_model_row() -> None:
    rows = session_layer(Path("/s/1"), model="haiku", no_jail=True)
    assert rows == [
        Row("ui", config={"history": "/s/1/events.jsonl"}),  # what the ui showed, drawn again on a resume
        Row("transcript", config={"path": "/s/1/transcript.jsonl"}),  # what the model is sent again
        Row("switch", config={"layer": "/s/1/session.toml", "model_row": "model"}),  # /model edits it
        # Claude Code's own state (its session, which a resume continues) in the session's directory
        Row("model", config={"state": "/s/1/claude", "default": "haiku"}),
        Row("jail", "kernel:unjailed"),
    ]
    assert session_layer(Path("/s/2"), model=None, no_jail=False)[-1] == Row(
        "model", config={"state": "/s/2/claude"}
    )  # no --model: the model row's own default, and the jail the harness ships


def test_a_session_from_the_agent_sdk_stack_is_retired_and_says_why() -> None:
    old = [Row("llm", config={"session_file": "/s/claude-session", "stderr_log": "/s/claude-stderr.log"})]
    assert "Claude Agent SDK" in str(retired(old))
    assert "claude-agent-sdk:agent" in str(retired([Row("llm", "claude-agent-sdk:agent")]))
    assert retired(session_layer(Path("/s/1"), model="haiku", no_jail=True)) is None
    assert retired([Row("completion", "anthropic:completion", {"model": "haiku"})]) is None  # updated, below


def _old_session(root: Path, cwd: str, stack: str, rows: list[Row]) -> Session:
    """A session as an earlier bh-02 wrote it: its stack (`claude`, `ollama`), its own layer."""
    session = create(root, cwd, model=None, no_jail=False)
    meta = session.dir / "meta.json"
    meta.write_text(meta.read_text().replace('"stack": "sonnet"', f'"stack": "{stack}"'))
    session.layer.write_text(format_layer(rows))
    (found,) = [s for s in listed(root, cwd) if s.id == session.id]
    return found


def _base(dir: Path) -> list[Row]:
    """The rows every session's layer has but the model row (an earlier bh-02's named it `completion`)."""
    return [r for r in session_layer(dir, model=None, no_jail=False) if r.id != "model"]


def test_a_session_from_the_messages_api_stack_moves_to_the_model_row_keeping_its_model(
    tmp_path: Path,
) -> None:
    """Sessions written before the claude-code provider: their completion row named no `use`
    (the shipped `anthropic:completion`) or named it, with Messages API settings Claude Code has
    no use for. Their transcript is kept; Claude Code's session is rebuilt from it."""
    session = _old_session(tmp_path, "/work/a", "claude", [])
    rows, state = _base(session.dir), str(session.dir / "claude")
    session.layer.write_text(format_layer([*rows, Row("completion", config={"model": "claude-haiku-4-5"})]))
    update(session)
    extra = {"claude-haiku-4-5": {"provider": "claude-code", "id": "claude-haiku-4-5"}}
    assert read_layer(session.layer) == [  # an id, not a built-in name: a model of the row's own
        *rows,
        Row("model", config={"default": "claude-haiku-4-5", "extra": extra, "state": state}),
    ]
    named = Row(
        "completion", "anthropic:completion", {"model": "opus", "max_tokens": 9, "thinking": {"type": "x"}}
    )
    session.layer.write_text(format_layer([*rows, named]))
    update(session)
    assert read_layer(session.layer) == [
        *rows,
        Row("model", "models:model", {"default": "opus", "state": state}),
    ]
    session.layer.write_text(format_layer(rows))  # no model row at all: the state is added
    update(session)
    assert read_layer(session.layer) == [*rows, Row("model", config={"state": state})]


def test_a_claude_code_session_moves_to_the_model_row_and_a_second_update_changes_nothing(
    tmp_path: Path,
) -> None:
    session = _old_session(tmp_path, "/work/a", "claude", [])
    rows, state = _base(session.dir), str(session.dir / "claude")
    switch = next(r for r in rows if r.id == "switch")
    old = [*rows, Row("operator", config={"model_row": "completion"})]  # /model was the operator's
    session.layer.write_text(
        format_layer([*old, Row("completion", config={"state": state, "model": "haiku"})])
    )
    update(session)
    now = read_layer(session.layer)
    assert next(r for r in now if r.id == "switch") == switch  # /model edits the model row now
    assert next(r for r in now if r.id == "operator") == Row("operator")
    assert next(r for r in now if r.id == "model") == Row(
        "model", config={"state": state, "default": "haiku"}
    )
    written = session.layer.read_text()
    update(session)
    assert session.layer.read_text() == written


def test_an_ollama_session_s_model_is_an_openai_model_of_the_model_row(tmp_path: Path) -> None:
    """An Ollama-stack session's layer named no model row: `ollama.toml`, gone now, gave it
    `ollama:completion`. A resume makes it the model row with the Ollama model as an `extra`
    OpenAI-compatible model at the host's `/v1`, named as its model and chosen."""
    session = _old_session(tmp_path, "/work/a", "ollama", [])
    rows, state = _base(session.dir), str(session.dir / "claude")
    session.layer.write_text(format_layer(rows))
    update(session)
    llama = {"llama3.2": {"provider": "openai", "id": "llama3.2", "base_url": "http://localhost:11434/v1"}}
    assert read_layer(session.layer) == [
        *rows,
        Row("model", "models:model", {"default": "llama3.2", "extra": llama, "state": state}),
    ]
    chosen = _old_session(
        tmp_path, "/work/a", "ollama", [*rows, Row("completion", config={"model": "qwen3"})]
    )
    update(chosen)  # --ollama --model qwen3
    qwen = {"qwen3": {"provider": "openai", "id": "qwen3", "base_url": "http://localhost:11434/v1"}}
    assert read_layer(chosen.layer)[-1] == Row(
        "model", "models:model", {"default": "qwen3", "extra": qwen, "state": str(chosen.dir / "claude")}
    )


def test_a_session_started_earlier_drops_the_model_status_row_that_hid_the_model_s_name(
    tmp_path: Path,
) -> None:
    """Sessions started before the shipped layers named the default model wrote a
    `model_status` row that replaced that config, so their status bar said `default`."""
    session = create(tmp_path, "/work/a", model="haiku", no_jail=False)
    rows = read_layer(session.layer)
    session.layer.write_text(format_layer([*rows, Row("model_status", config={"row": "completion"})]))
    update(session)
    assert read_layer(session.layer) == rows  # everything else as it was
    written = session.layer.read_text()
    update(session)  # nothing superseded left: the file is not rewritten
    assert session.layer.read_text() == written


# What a session layer from before the one tool could name: the tool registry, what registered into
# it, and what offered it, as rows of their own or as overrides of shipped ones.
_BEFORE_ONE_TOOL = [
    Row("tools", "tools:registry"),
    Row("fs", disabled=True),
    Row("approve", "tui:approver"),
    Row("actions", "tools:actions"),
    Row("guard", disabled=True),
    Row("mine", "codeact:python", {"expose": ["tools"]}),
]


def test_a_session_from_before_the_one_tool_drops_the_rows_bh_02_no_longer_has(tmp_path: Path) -> None:
    session = create(tmp_path, "/work/a", model=None, no_jail=True)
    rows = read_layer(session.layer)
    session.layer.write_text(format_layer([*rows, *_BEFORE_ONE_TOOL]))
    update(session)
    assert read_layer(session.layer) == rows  # everything else as it was, the jail choice included


def test_a_session_from_before_the_one_tool_resumes(composition: Callable[..., Path], state: Path) -> None:
    """Its layer is updated before it boots, so the rows it names that no plugin fills any more
    never reach the loader (which would refuse to start: a row with no `use` it can resolve)."""
    patch = composition(
        '[[plugin]]\nid = "model"\nuse = "fragile:counting_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
    )
    runner = CliRunner()
    assert runner.invoke(main, ["--patch", str(patch)]).exit_code == 0
    (session,) = listed(state, str(Path.cwd()))
    session.layer.write_text(format_layer([*read_layer(session.layer), *_BEFORE_ONE_TOOL]))
    again = runner.invoke(main, ["--resume", "--patch", str(patch)])
    assert again.exit_code == 0, again.output + again.stderr
    import fragile

    assert fragile.SHOWN == ["seen 1", "seen 2"]  # resumed, with its history
    assert not {row.id for row in read_layer(session.layer)} & {"tools", "fs", "approve", "actions", "guard"}


def test_a_session_started_earlier_drops_its_session_row(tmp_path: Path) -> None:
    """Sessions wrote a `session` row (`tui:status`, a fixed field holding their id); the status
    row now shows the id itself, from the `sessions` value, so a resume drops the row."""
    session = create(tmp_path, "/work/a", model=None, no_jail=False)
    rows = read_layer(session.layer)
    old = Row("session", "tui:status", {"field": "session", "text": session.id, "shorter": ["x"]})
    session.layer.write_text(format_layer([old, *rows]))
    update(session)
    assert read_layer(session.layer) == rows


def test_a_session_layer_naming_the_sidebar_drops_it(tmp_path: Path) -> None:
    """bh-02 never wrote a `sidebar` row into a session's layer, but a hand edit could have
    (turning it off); with no `sidebar` row shipped, it would stop the resume, so it goes."""
    session = create(tmp_path, "/work/a", model=None, no_jail=False)
    rows = read_layer(session.layer)
    session.layer.write_text(format_layer([*rows, Row("sidebar", disabled=True)]))
    update(session)
    assert read_layer(session.layer) == rows


def test_a_session_layer_in_old_row_names_is_brought_up_to_date(tmp_path: Path) -> None:
    """A layer as an earlier bh-02 wrote it (its `session` row, the superseded `model_status`)
    and then hand-edited in the old names (`llm`, `jail_status`): a resume reads it in today's
    names, the id now the status row's own and the status bar's config the shipped one."""
    session = create(tmp_path, "/work/a", model=None, no_jail=False)
    rows = read_layer(session.layer)
    old = [
        Row("session", "tui:status", {"field": "session", "text": session.id, "shorter": ["x"]}),
        *rows,
        Row("model_status", config={"row": "completion"}),
        Row("llm", config={"max_nudges": 5}),
        Row("jail_status", disabled=True),
    ]
    session.layer.write_text(format_layer(old))
    update(session)
    # jail_status was off; the status row it became part of is not (that would also hide the
    # session and the model), and with nothing else to say it is not written at all
    assert read_layer(session.layer) == [*rows, Row("loop", config={"max_nudges": 5})]


def test_a_resumed_session_keeps_its_status_bar_when_one_old_part_was_off(tmp_path: Path) -> None:
    """An old model_status with its own config and a disabled jail_status: the status row
    carries the config (but the default model, which the models row answers now) and stays
    on, so the resumed bar still shows session and model."""
    session = create(tmp_path, "/work/a", model=None, no_jail=False)
    rows = read_layer(session.layer)
    old = [
        *rows,
        Row("model_status", disabled=True, config={"default": "opus", "row": "llm"}),
        Row("jail_status", disabled=True),
    ]
    session.layer.write_text(format_layer(old))
    update(session)
    assert read_layer(session.layer) == [*rows, Row("status", config={"model_row": "model"})]


def test_a_status_row_s_own_disabled_is_kept(tmp_path: Path) -> None:
    session = create(tmp_path, "/work/a", model=None, no_jail=False)
    rows = read_layer(session.layer)
    session.layer.write_text(
        format_layer([*rows, Row("status", disabled=True), Row("jail_status", disabled=True)])
    )
    update(session)
    assert read_layer(session.layer) == [*rows, Row("status", disabled=True)]


def test_a_session_in_old_row_names_resumes(composition: Callable[..., Path], state: Path) -> None:
    patch = composition(
        '[[plugin]]\nid = "model"\nuse = "fragile:counting_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n'
    )
    runner = CliRunner()
    assert runner.invoke(main, ["--patch", str(patch)]).exit_code == 0
    (session,) = listed(state, str(Path.cwd()))
    session_row = Row("session", "tui:status", {"field": "session", "text": session.id})
    old = [session_row, *read_layer(session.layer), Row("model_status", config={"row": "completion"})]
    session.layer.write_text(format_layer(old))
    again = runner.invoke(main, ["--resume", "--patch", str(patch)])
    assert again.exit_code == 0, again.output + again.stderr
    import fragile

    assert fragile.SHOWN == ["seen 1", "seen 2"]  # resumed, with its history
    assert fragile.FIELDS["session"] == f"{session.id} (resumed)"  # the status row's, not the old row's
    assert not {row.id for row in read_layer(session.layer)} & {"session", "model_status"}


def test_choosing_a_model_keeps_the_row_s_other_config() -> None:
    rows = [Row("model", config={"state": "/s"}), Row("jail", "kernel:unjailed")]
    assert with_model(rows, "opus") == [
        Row("jail", "kernel:unjailed"),
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


def test_a_session_from_the_agent_sdk_stack_can_t_be_resumed_and_says_so_in_one_line(state: Path) -> None:
    old = create(state, str(Path.cwd()), model=None, no_jail=False)
    old.layer.write_text(  # the layer such a session was written with
        '[[plugin]]\nid = "llm"\n'
        f'config = {{ session_file = "{old.dir}/claude-session", '
        f'stderr_log = "{old.dir}/claude-stderr.log" }}\n'
    )
    resumed = CliRunner().invoke(main, ["--resume", old.id])
    assert resumed.exit_code == 1
    (line,) = resumed.stderr.splitlines()
    assert line.startswith(f"error: can't resume {old.id}: it ran on the Claude Agent SDK stack")
    assert line.endswith("start a new session with `uv run bh-02`")
    assert [s.id for s in listed(state, str(Path.cwd()))] == [old.id]  # still listed, never deleted


def test_a_session_layer_with_both_an_old_row_and_its_new_name_is_refused_unchanged(state: Path) -> None:
    """Only a hand edit writes both `llm` and `loop`: which one's settings win is the person's call."""
    old = create(state, str(Path.cwd()), model=None, no_jail=False)
    text = old.layer.read_text() + '[[plugin]]\nid = "llm"\n[[plugin]]\nid = "loop"\n'
    old.layer.write_text(text)
    resumed = CliRunner().invoke(main, ["--resume", old.id])
    assert resumed.exit_code == 1
    lines = resumed.stderr.splitlines()
    assert lines[0] == f"error: can't resume {old.id}: {old.layer} has rows it cannot fold together for you:"
    assert "row 'llm' is now 'loop', and this layer has a 'loop' row too" in lines[1]
    assert lines[-1] == "fix that file by hand, then resume again"
    assert old.layer.read_text() == text  # nothing rewritten


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
    assert all(line.endswith(f"sonnet  patched: {patch.name}") for line in lines)  # not only "sonnet"
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
