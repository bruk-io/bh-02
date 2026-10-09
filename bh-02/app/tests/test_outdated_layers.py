"""Layer files written for an earlier bh-02: the translation to today's row names, a `--patch`
file naming old rows refused with what to change, and `bh-02 update-layer` rewriting one."""

import os
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from bh_02 import main
from bh_02.bootstrap import layers
from bh_02.outdated import translated
from cordis import Row
from cordis.composition import parse_layer
from cordis.loader import read_layer


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    yield tmp_path


# A patch as an earlier bh-02's person wrote it: a fake model, a model default in the status
# bar, the jail's field turned off, the chat row's config, a tool row, and /clear's rows.
_OLD = """\
# my patch
[[plugin]]
id = "llm"
use = "bh_02.testing:echo"

[[plugin]]
id = "model_status"
config = { default = "fake", row = "completion" }

[[plugin]]
id = "jail_status"
disabled = true

[[plugin]]
id = "mode"
config = { greeting = "hi" }

[[plugin]]
id = "actions"
use = "tools:actions"

[[plugin]]
id = "operator"
config = { clear = ["llm", "transcript", "kernel"] }
"""


def test_the_shipped_layers_are_already_in_today_s_names() -> None:
    for layer in layers():
        rows = read_layer(str(layer))
        assert translated(rows) == (rows, [])


def test_an_old_layer_reads_in_today_s_names_and_says_what_changed() -> None:
    rows, changes = translated(parse_layer(_OLD))
    assert rows == [
        Row("loop", "bh_02.testing:echo"),
        # the two status-bar rows, one row: the model's config under its new names, and on,
        # though jail_status was off (turning all of it off would hide the session and model)
        Row("status", None, {"model_row": "model"}),
        Row("chat", config={"greeting": "hi"}),
        Row("operator"),
        Row("conversation", config={"clear": ["loop", "transcript", "kernel"]}),  # /clear is its now
    ]
    assert changes == [
        "row 'llm' is now 'loop'; rename its id",
        "row 'model_status' is now part of 'status', the status bar's one row; its config moves "
        'there as config = { model_row = "model" }',
        "row 'jail_status' is now part of 'status', the status bar's one row; it was disabled, "
        "but 'status' cannot turn off one part, so the status bar stays on: to turn off all of "
        "it (session, model and jail), give 'status' `disabled = true`",
        "row 'mode' is now 'chat'; rename its id",
        "row 'actions' was removed: the model's tools are registered with `tools` (agent:tools) by "
        "the rows that offer them, the kernel's python among them, and unjailed each call is put to "
        "the person in the modal; delete it",
        "row 'operator': its config names a renamed row; make it "
        'config = { clear = ["loop", "transcript", "kernel"] }',
        "row 'operator': /clear is the conversation row's now (agent:conversation): add a "
        '\'conversation\' row with config = { clear = ["loop", "transcript", "kernel"] }; delete its config',
    ]
    assert translated(rows) == (rows, [])  # once is enough


def test_the_rows_bh_02_no_longer_has_are_dropped_with_why() -> None:
    rows, changes = translated(
        [
            Row("session", "tui:status", {"field": "session", "text": "1", "shorter": ["1"]}),
            Row("greeting", "tui:status", {"field": "hello", "text": "hi"}),
            Row("mine", "fs:tools"),
            Row("approve", "tui:approver"),
            Row("kernel", "kernel:kernel"),
            Row("tools", "tools:registry"),  # the old tools plugin, whatever the row's id
            Row("tools", disabled=True),  # a change to today's broker, agent:tools: kept
        ]
    )
    assert rows == [Row("kernel", "kernel:kernel"), Row("tools", disabled=True)]
    assert changes[0] == "row 'session' was removed: the status row shows the session's id itself; delete it"
    assert changes[1].startswith("row 'greeting' was removed: tui:status is now the status bar's one row")
    assert changes[2].startswith("row 'mine' was removed: fs:tools is gone: the model's tools are registered")
    assert changes[3].startswith("row 'approve' was removed: the model's tools are registered with `tools`")
    assert changes[4].startswith("row 'tools' was removed: tools:registry is gone")


_NO_SIDEBAR = "bh-02 has no sidebar now (`bh-02 sessions` lists this directory's sessions)"


def test_the_sidebar_is_dropped_with_why_but_a_sidebar_row_of_your_own_stays() -> None:
    """The shipped `sidebar` row (`tui:sessions`) is gone: a change to it, or any row using
    `tui:sessions`, is dropped. A row called `sidebar` that names a plugin of the person's own
    is theirs, and still runs."""
    rows, changes = translated([Row("sidebar", disabled=True), Row("listed", "tui:sessions")])
    assert rows == []
    assert changes == [
        f"row 'sidebar' was removed: {_NO_SIDEBAR}; delete it",
        f"row 'listed' was removed: tui:sessions is gone: {_NO_SIDEBAR}; delete it",
    ]
    own = [Row("sidebar", "mine:panel")]
    assert translated(own) == (own, [])


_NO_SHELL_HINTS = "bh-02 no longer tells the model how Python does what an input ran through a shell"


def test_the_shell_hints_are_dropped_with_why_but_a_row_of_your_own_by_that_id_stays() -> None:
    """The shipped `shell-hints` row (`kernel:shell_hints`) is gone: a change to it, or any row
    using `kernel:shell_hints`, is dropped. A row called `shell-hints` that names a plugin of the
    person's own is theirs, and still runs."""
    rows, changes = translated([Row("shell-hints", disabled=True), Row("hints", "kernel:shell_hints")])
    assert rows == []
    assert changes == [
        f"row 'shell-hints' was removed: {_NO_SHELL_HINTS}; delete it",
        f"row 'hints' was removed: kernel:shell_hints is gone: {_NO_SHELL_HINTS}; delete it",
    ]
    own = [Row("shell-hints", "mine:hints")]
    assert translated(own) == (own, [])


def test_a_patch_naming_the_sidebar_is_refused_and_update_layer_drops_it(state: Path) -> None:
    patch = state / "quiet.toml"
    patch.write_text('[[plugin]]\nid = "sidebar"\ndisabled = true\n')  # how the sidebar was turned off
    result = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert result.exit_code == 1 and "Traceback" not in result.output
    assert result.stderr.splitlines() == [
        "error: a --patch file names rows this bh-02 renamed or no longer has:",
        f"  {patch}: row 'sidebar' was removed: {_NO_SIDEBAR}; delete it",
        f"run `bh-02 update-layer {patch}` to rewrite it (the original is kept beside it as .bak), "
        "then run again",
    ]
    assert "no sessions" in CliRunner().invoke(main, ["sessions"]).stderr  # none left behind
    assert CliRunner().invoke(main, ["update-layer", str(patch)]).exit_code == 0
    assert read_layer(patch) == []


def test_an_old_fixed_field_is_dropped_even_under_the_status_row_s_id() -> None:
    """A fixed field an earlier bh-02 wrote as `id = "status"` is not today's status row: its
    `field` and `text` would fail the status row's config at boot, so it is removed, with why."""
    rows, changes = translated([Row("status", "tui:status", {"field": "x", "text": "y"})])
    assert rows == []
    assert changes == [
        "row 'status' was removed: tui:status is now the status bar's one row (session, model, "
        "jail), not a fixed field; delete it"
    ]


@pytest.mark.parametrize("key", ["row", "model_row"])
def test_an_old_model_row_named_llm_or_completion_is_the_model_row_not_the_loop(key: str) -> None:
    """Before the completion row, the model was the `llm` row's config; then the completion's;
    it is the model row's now, and the loop has none, so a status field following `loop`
    would never change."""
    rows, _ = translated([Row("model_status", config={key: "llm", "default": "x"})])
    assert rows == [Row("status", None, {"model_row": "model"})]
    rows, _ = translated([Row("operator", config={"model_row": "llm", "clear": ["llm"]})])
    assert rows == [
        Row("operator"),
        Row("conversation", config={"clear": ["loop"]}),
        Row("switch", config={"model_row": "model"}),
    ]
    rows, _ = translated([Row("operator", config={"model_row": "completion", "clear": ["completion"]})])
    assert rows == [
        Row("operator"),
        Row("conversation", config={"clear": ["model"]}),
        Row("switch", config={"model_row": "model"}),
    ]


def test_claude_code_s_row_is_the_model_row_naming_its_model_by_name() -> None:
    old = [Row("completion", "claude-code:completion", {"model": "opus", "state": "/s/claude"})]
    rows, changes = translated(old)
    assert rows == [Row("model", "models:model", {"default": "opus", "state": "/s/claude"})]
    assert changes == [
        "row 'completion' is now 'model'; rename its id",
        "row 'model': claude-code:completion is gone: Claude Code is a provider of the model row now, "
        'which names its model `default`; make it use = "models:model", config = { default = "opus", '
        'state = "/s/claude" }',
    ]
    assert translated(rows) == (rows, [])  # once is enough
    by_id, _ = translated([Row("completion", config={"model": "claude-opus-4-1"})])  # no use: Claude Code's
    extra = {"claude-opus-4-1": {"provider": "claude-code", "id": "claude-opus-4-1"}}
    assert by_id == [Row("model", None, {"default": "claude-opus-4-1", "extra": extra})]
    bare, said = translated([Row("completion", "claude-code:completion")])
    # no config stays no config: an empty one would replace the session's model config whole
    assert bare == [Row("model", "models:model")]
    assert not any("config = {" in line for line in said)


def test_ollama_s_row_is_an_openai_model_of_the_model_row_at_its_host_s_v1() -> None:
    rows, changes = translated(
        [Row("completion", "ollama:completion", {"host": "http://gpu:11434/", "model": "qwen3"})]
    )
    extra = {"qwen3": {"provider": "openai", "id": "qwen3", "base_url": "http://gpu:11434/v1"}}
    assert rows == [Row("model", "models:model", {"default": "qwen3", "extra": extra})]
    assert changes[1].startswith(
        "row 'model': ollama:completion is gone: Ollama is an OpenAI-compatible model of the model row now; "
        'make it use = "models:model", config = { default = "qwen3", extra = '
    )
    assert translated(rows) == (rows, [])
    defaults, said = translated([Row("completion", "ollama:completion", {"model": "qwen2.5:7b"})])
    pasted = said[1].split("make it ", 1)[1].split(", ", 1)[1]  # the hint is TOML a person can paste
    assert tomllib.loads(pasted)["config"] == defaults[0].config
    assert '"qwen2.5:7b" = { provider = "openai"' in pasted
    defaults, _ = translated([Row("completion", "ollama:completion")])  # Ollama's own defaults
    llama = {"llama3.2": {"provider": "openai", "id": "llama3.2", "base_url": "http://localhost:11434/v1"}}
    assert defaults == [Row("model", "models:model", {"default": "llama3.2", "extra": llama})]


def test_bh_02_s_fakes_that_bound_completion_bind_model_under_new_names() -> None:
    rows, changes = translated([Row("completion", "bh_02.testing:echo_completion")])
    assert rows == [Row("model", "bh_02.testing:echo_model")]
    assert changes[-1] == (
        "row 'model': bh_02.testing:echo_completion is now bh_02.testing:echo_model; make it "
        'use = "bh_02.testing:echo_model"'
    )


def test_the_project_context_s_rows_are_the_system_prompt_s_and_memory_s() -> None:
    """`context:project` is `agent:system` and `context:on_touch` is `memory:on_touch`; a `system`
    row's `root` and `home` go to a `memory` row too, its `files` are gone; and the broker
    `agent:memory` is `agent:notes`, under the id `notes`."""
    rows, changes = translated(
        [
            Row("system", "context:project", {"root": "/p", "home": "/h", "files": ["x.toml"]}),
            Row("on-touch", "context:on_touch"),
            Row("memory", "agent:memory"),
        ]
    )
    assert rows == [
        Row("system", "agent:system", {"root": "/p"}),
        Row("memory", None, {"root": "/p", "home": "/h"}),
        Row("on-touch", "memory:on_touch"),
        Row("notes", "agent:notes"),
    ]
    assert any("files is gone (context files are gone" in change for change in changes)
    assert translated(rows) == (rows, [])  # once
    assert translated([Row("system", config={"root": "/p"})]) == ([Row("system", config={"root": "/p"})], [])


def test_the_status_row_s_default_model_is_gone() -> None:
    rows, changes = translated([Row("status", config={"default_model": "fake"})])
    assert rows == [] and changes == [
        "row 'status': default_model is gone (the status bar shows the model and provider the model "
        "row names); delete its config"
    ]
    rows, _ = translated([Row("status", "tui:status", {"default_model": "fake", "model_row": "m"})])
    assert rows == [Row("status", "tui:status", {"model_row": "m"})]
    kept = [Row("status", disabled=True)]
    assert translated(kept) == (kept, [])


def test_today_s_status_row_naming_the_old_model_row_names_the_model_row() -> None:
    rows, changes = translated([Row("status", "tui:status", {"model_row": "completion"})])
    assert rows == [Row("status", "tui:status", {"model_row": "model"})]
    assert changes == [
        "row 'status': its config names a renamed row; make it config = { model_row = \"model\" }"
    ]
    assert translated(rows) == (rows, [])


def test_a_renamed_row_whose_new_id_is_taken_is_left_for_the_person() -> None:
    """Both `llm` and `loop`: renaming would make two `loop` rows, and which one's settings win
    is the person's call, so `llm` keeps its id and the change says so, every time."""
    old = [Row("llm", "bh_02.testing:echo"), Row("loop", config={"max_nudges": 1})]
    rows, changes = translated(old)
    assert rows == old
    clash = (
        "row 'llm' is now 'loop', and this layer has a 'loop' row too: fold what 'llm' sets "
        "into 'loop' and delete 'llm'"
    )
    assert changes == [clash]
    assert translated(rows) == (rows, [clash])  # not "up to date"


def test_update_layer_refuses_a_clash_and_writes_nothing(state: Path) -> None:
    text = '[[plugin]]\nid = "llm"\nuse = "bh_02.testing:echo"\n\n[[plugin]]\nid = "loop"\n'
    patch = state / "both.toml"
    patch.write_text(text)
    result = CliRunner().invoke(main, ["update-layer", str(patch)])
    assert result.exit_code == 1
    assert result.stderr.splitlines() == [
        f"error: {patch} has rows update-layer cannot fold together for you:",
        f"  {patch}: row 'llm' is now 'loop', and this layer has a 'loop' row too: fold what "
        "'llm' sets into 'loop' and delete 'llm'",
        "nothing was rewritten; fix those by hand, then run it again",
    ]
    assert patch.read_text() == text and not (state / "both.toml.bak").exists()
    refused = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert refused.exit_code == 1 and "row 'llm' is now 'loop', and this layer has" in refused.stderr
    # the refusal does not send the person to update-layer, which would refuse it too
    assert "`bh-02 update-layer" not in refused.stderr
    assert refused.stderr.splitlines()[-1] == (
        f"fold the clashing rows in {patch} together by hand (update-layer leaves which one wins "
        "to you), then run again"
    )


def test_a_patch_with_a_clash_and_other_changes_says_to_fold_first_then_update(state: Path) -> None:
    """A clash plus a row update-layer can rewrite: fold by hand first, then update-layer does
    the rest, and after the fold it does."""
    patch = state / "both.toml"
    patch.write_text('[[plugin]]\nid = "llm"\n\n[[plugin]]\nid = "loop"\n\n[[plugin]]\nid = "mode"\n')
    refused = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert refused.exit_code == 1
    assert refused.stderr.splitlines()[-1] == (
        f"fold the clashing rows in {patch} together by hand (update-layer leaves which one wins "
        f"to you), then `bh-02 update-layer {patch}` for the rest, then run again"
    )
    patch.write_text('[[plugin]]\nid = "loop"\n\n[[plugin]]\nid = "mode"\n')  # folded by hand
    assert CliRunner().invoke(main, ["update-layer", str(patch)]).exit_code == 0
    assert [row.id for row in read_layer(str(patch))] == ["loop", "chat"]


def test_a_patch_with_a_clash_in_one_file_still_names_update_layer_for_the_other(state: Path) -> None:
    clash, plain = state / "both.toml", state / "old.toml"
    clash.write_text('[[plugin]]\nid = "llm"\n\n[[plugin]]\nid = "loop"\n')
    plain.write_text('[[plugin]]\nid = "mode"\n')
    refused = CliRunner().invoke(main, ["--no-jail", "--patch", str(clash), "--patch", str(plain)])
    assert refused.exit_code == 1
    assert f"run `bh-02 update-layer {plain}` to rewrite it" in refused.stderr
    assert f"`bh-02 update-layer {clash}`" not in refused.stderr


def test_a_row_using_an_old_status_component_becomes_the_status_row() -> None:
    rows, changes = translated([Row("bar", "tui:model", {"default": "opus", "row": "completion"})])
    assert rows == [Row("status", "tui:status", {"model_row": "model"})]
    assert changes == [
        "row 'bar' is now part of 'status', the status bar's one row; its config moves there as "
        'config = { model_row = "model" }'
    ]


def test_a_patch_naming_old_rows_is_refused_with_each_row_and_what_to_change(state: Path) -> None:
    """A `--patch` is the person's file: refused, before the TUI starts or a session is made,
    with every outdated row, what to change, and the command that does it."""
    patch = state / "mine.toml"
    patch.write_text(_OLD)
    result = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert result.exit_code == 1
    lines = result.stderr.splitlines()
    assert lines[0] == "error: a --patch file names rows this bh-02 renamed or no longer has:"
    assert f"  {patch}: row 'llm' is now 'loop'; rename its id" in lines
    assert f"  {patch}: row 'mode' is now 'chat'; rename its id" in lines
    assert any(
        line.startswith(f"  {patch}: row 'actions' was removed: the model's tools are registered")
        for line in lines
    )
    hint = f"run `bh-02 update-layer {patch}` to rewrite it (the original is kept beside it as .bak)"
    assert lines[-1] == f"{hint}, then run again"
    assert len(lines) == 9  # the heading, a line per change, the hint
    assert "Traceback" not in result.output
    assert "no sessions" in CliRunner().invoke(main, ["sessions"]).stderr  # none left behind
    assert patch.read_text() == _OLD  # refused, not rewritten behind the person's back


@pytest.mark.parametrize(
    ("use", "said"),
    [
        ("claude-code:completion", "claude-code:completion is gone: Claude Code is a provider"),
        ("ollama:completion", "ollama:completion is gone: Ollama is an OpenAI-compatible model"),
    ],
)
def test_a_patch_naming_a_provider_row_is_refused_with_the_update_layer_hint(
    state: Path, use: str, said: str
) -> None:
    patch = state / "provider.toml"
    patch.write_text(f'[[plugin]]\nid = "completion"\nuse = "{use}"\n')
    result = CliRunner().invoke(main, ["--no-jail", "--patch", str(patch)])
    assert result.exit_code == 1
    lines = result.stderr.splitlines()
    assert f"  {patch}: row 'completion' is now 'model'; rename its id" in lines
    assert any(line.startswith(f"  {patch}: row 'model': {said}") for line in lines)
    assert lines[-1].startswith(f"run `bh-02 update-layer {patch}` to rewrite it")
    assert CliRunner().invoke(main, ["update-layer", str(patch)]).exit_code == 0
    (row,) = read_layer(patch)
    assert row.id == "model" and row.use == "models:model"


def test_a_migrated_ollama_patch_chooses_the_model_so_model_is_refused_and_update_layer_says_so(
    state: Path,
) -> None:
    """The patch update-layer writes from an Ollama row sets the model row's config, which
    replaces the session layer's whole: `--model` would not take effect, so it is refused."""
    patch = state / "ollama.toml"
    patch.write_text('[[plugin]]\nid = "completion"\nuse = "ollama:completion"\n')
    updated = CliRunner().invoke(main, ["update-layer", str(patch)])
    assert updated.exit_code == 0
    note = updated.stdout.splitlines()[-1]
    assert note.startswith(
        f"note: {patch} sets the model row's config, so while it is a --patch it chooses the model"
    )
    # the models file it names is the one this run reads: $XDG_CONFIG_HOME's (conftest sets it)
    assert f"models file ({os.environ['XDG_CONFIG_HOME']}/bh-02/models.toml)" in note
    refused = CliRunner().invoke(main, ["--no-jail", "--model", "haiku", "--patch", str(patch)])
    assert refused.exit_code == 1 and "Traceback" not in refused.output
    assert refused.stderr.startswith(
        f"error: --model haiku would not take effect: {patch} sets the model row's config"
    )
    assert "no sessions" in CliRunner().invoke(main, ["sessions"]).stderr  # none left behind


def test_update_layer_rewrites_the_file_keeps_a_copy_and_runs_once(state: Path) -> None:
    patch = state / "mine.toml"
    patch.write_text(_OLD)
    runner = CliRunner()
    first = runner.invoke(main, ["update-layer", str(patch)])
    assert first.exit_code == 0, first.output + first.stderr
    backup = state / "mine.toml.bak"
    assert backup.read_text() == _OLD  # the original, comments and all
    assert read_layer(patch) == translated(parse_layer(_OLD))[0]
    header = patch.read_text().splitlines()[0]  # says what wrote it, and where the original is
    assert "update-layer" in header and "mine.toml.bak" in header
    said = first.stdout.splitlines()
    assert said[0] == f"{patch}: row 'llm' is now 'loop'; rename its id"
    assert said[-1] == f"rewritten; the original, with its comments, is {backup}"
    rewritten = patch.read_text()
    again = runner.invoke(main, ["update-layer", str(patch)])
    assert again.exit_code == 0 and again.stdout == f"{patch} is up to date: nothing to change\n"
    assert patch.read_text() == rewritten and backup.read_text() == _OLD  # the copy is the original still


def test_update_layer_says_when_it_replaces_an_earlier_backup(state: Path) -> None:
    patch = state / "mine.toml"
    patch.write_text(_OLD)
    runner = CliRunner()
    assert runner.invoke(main, ["update-layer", str(patch)]).exit_code == 0
    backup = state / "mine.toml.bak"
    assert "was there already" not in runner.invoke(main, ["update-layer", str(patch)]).stdout
    second = '[[plugin]]\nid = "mode"\n'  # old names put back by hand
    patch.write_text(second)
    again = runner.invoke(main, ["update-layer", str(patch)])
    assert again.exit_code == 0
    assert again.stdout.splitlines()[-1] == (
        f"note: {backup} was there already, from an earlier run; it now holds this run's original"
    )
    assert backup.read_text() == second


def test_an_updated_patch_runs(state: Path, composition: Callable[..., Path]) -> None:
    """What `update-layer` writes is a patch this bh-02 runs: the old `llm` fake is the loop."""
    ui = composition('[[plugin]]\nid = "ui"\nuse = "fragile:one_message_recorded_ui"\n')
    patch = state / "old.toml"
    patch.write_text('[[plugin]]\nid = "llm"\nuse = "fragile:echo_model"\n')
    runner = CliRunner()
    assert runner.invoke(main, ["--patch", str(ui), "--patch", str(patch)]).exit_code == 1
    assert runner.invoke(main, ["update-layer", str(patch)]).exit_code == 0
    ran = runner.invoke(main, ["--patch", str(ui), "--patch", str(patch)])
    assert ran.exit_code == 0, ran.output + ran.stderr
    import fragile

    assert fragile.SHOWN  # the fake model answered, as the loop


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ('[[plugin]\nid = "llm"\n', "fix the file or drop it"),  # not TOML
        ('[[plugin]]\nuse = "agent:loop"\n', "has no 'id'"),  # not a layer's shape
    ],
)
def test_update_layer_refuses_a_file_it_can_t_read_and_writes_nothing(
    state: Path, text: str, why: str
) -> None:
    patch = state / "broken.toml"
    patch.write_text(text)
    result = CliRunner().invoke(main, ["update-layer", str(patch)])
    assert result.exit_code == 1
    assert result.stderr.startswith(f"error: {patch}: ") and why in result.stderr
    assert "Traceback" not in result.output
    assert patch.read_text() == text and not (state / "broken.toml.bak").exists()


def test_model_moves_from_the_operator_to_the_switch_row() -> None:
    """`/model` is the models plugin's `switch` row: a session's operator config hands it the
    layer and model row it read, and translating again changes nothing more."""
    session = [Row("operator", config={"layer": "/s/session.toml", "model_row": "model", "forget": ["/s/t"]})]
    rows, changes = translated(session)
    assert rows == [Row("operator"), Row("switch", config={"layer": "/s/session.toml", "model_row": "model"})]
    assert changes == [
        "row 'operator': /model is the models plugin's now (models:switch): make it config = "
        '{ forget = ["/s/t"] }, and add a \'switch\' row with config = { layer = "/s/session.toml", '
        'model_row = "model" }',
        "row 'operator': `forget` is gone: /clear writes an empty conversation over the transcript "
        "row's file, keeping the old as .bak; delete its config",
    ]
    assert translated(rows) == (rows, [])


def test_a_layer_that_fills_the_operator_gets_the_switch_row() -> None:
    own = [Row("operator", "commands:operator")]
    rows, changes = translated(own)
    assert rows == [
        Row("operator", "commands:operator"),
        Row("jobs", "commands:jobs"),
        Row("conversation", "agent:conversation"),
        Row("switch", "models:switch"),
    ]
    assert changes == [
        "/model is the models plugin's now (models:switch): add a 'switch' row with use = \"models:switch\"",
        "/clear is the conversation row's now (agent:conversation): add a 'conversation' row with "
        'use = "agent:conversation"',
        "the chat row waits on `jobs` now, where commands queue the restarts they ask for: add a "
        "'jobs' row with use = \"commands:jobs\"",
    ]
    assert translated(rows) == (rows, [])
    assert translated([Row("operator", disabled=False)]) == (
        [Row("operator", disabled=False)],
        [],
    )  # a change to the shipped operator: the shipped layer has the switch row
    taken = [Row("switch", config={"layer": "/x"}), Row("operator", config={"model_row": "model"})]
    rows, changes = translated(taken)
    assert rows == [Row("switch", config={"layer": "/x"}), Row("operator")]
    assert changes == [
        "row 'operator': /model is the models plugin's now (models:switch), which reads config = "
        "{ model_row = \"model\" }: delete its config, and set it on the 'switch' row by hand"
    ]


def test_compact_is_the_conversation_row_and_an_operator_s_forget_is_gone() -> None:
    """/clear and /compact are one row's: the `compact` row is renamed to it, keeping its
    config, and an operator's `forget` (the files /clear emptied) is gone, since /clear writes
    over the transcript row's file, keeping the old."""
    rows, changes = translated([Row("compact", "agent:compact", {"timeout": 60})])
    assert rows == [Row("conversation", "agent:conversation", {"timeout": 60})]
    assert changes == [
        "row 'compact': /compact is the conversation row's now, with /clear; make it "
        'id = "conversation", use = "agent:conversation"'
    ]
    assert translated([Row("compact", config={"timeout": 60})])[0] == [
        Row("conversation", config={"timeout": 60})
    ]
    both = [
        Row("operator", "commands:operator", {"clear": ["loop"], "forget": ["/x"]}),
        Row("compact", "agent:compact"),
    ]
    rows, changes = translated(both)
    assert rows == [
        Row("operator", "commands:operator"),
        Row("jobs", "commands:jobs"),
        Row("switch", "models:switch"),
        Row("conversation", "agent:conversation"),
    ]
    assert changes[-2] == (
        "row 'operator': `forget` is gone: /clear writes an empty conversation over the transcript "
        "row's file, keeping the old as .bak; /clear is the conversation row's now "
        '(agent:conversation), which reads config = { clear = ["loop"] }: set it on the '
        "'conversation' row by hand; delete its config"
    )
    assert translated(rows) == (rows, [])


def test_a_layer_that_fills_the_chat_row_gets_the_jobs_row() -> None:
    rows, changes = translated([Row("chat", "chat:session"), Row("loop", "agent:loop")])
    assert rows == [Row("chat", "chat:session"), Row("jobs", "commands:jobs"), Row("loop", "agent:loop")]
    assert changes == [
        "the chat row waits on `jobs` now, where commands queue the restarts they ask for: add a "
        "'jobs' row with use = \"commands:jobs\""
    ]
    assert translated(rows) == (rows, [])
    assert translated([Row("chat", config={"prompt": "hi"})])[1] == []  # a change to the shipped row
