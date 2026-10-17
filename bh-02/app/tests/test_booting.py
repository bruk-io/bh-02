"""Booting the shipped layers and patched ones the way the CLI does."""

import asyncio
import importlib.metadata
import re
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

from bh_02 import CompositionError, layers, run
from bh_02.bootstrap import LayerError, NotStarted
from cordis import Effects, Inspection, Row, Runtime, State, bind, boot, component
from cordis.loader import read_layer, resolve


def test_the_app_depends_on_every_plugin_its_shipped_layer_names() -> None:
    """`uv sync --all-packages` installs every member, so a plugin the shipped layer names but
    the app does not depend on still resolves here; installed on its own (`uv tool install`),
    its row would come up unresolved. The app's own requirements must carry every one."""
    plugins = {
        ep.name: ep.dist.name for ep in importlib.metadata.entry_points(group="cordis.plugins") if ep.dist
    }
    required = {
        re.split(r"[\s;<>=!~\[]", req, maxsplit=1)[0] for req in importlib.metadata.requires("bh-02") or ()
    }
    named = {
        row.use.partition(":")[0] for layer in layers() for row in read_layer(str(layer)) if row.use
    } & set(plugins)
    assert "extensions" in named
    assert {name: plugins[name] for name in named if plugins[name] not in required} == {}


def test_every_shipped_layer_names_a_plugin_component_for_every_row() -> None:
    """The layer files ship in the wheel, and every `use` resolves through its entry point."""
    rows = {}
    for layer in layers():
        for row in read_layer(str(layer)):
            rows[row.id] = row if row.use else Row(row.id, rows[row.id].use, row.config)
    assert {"loop", "ui", "chat", "python", "runner", "system", "tools"} <= set(rows)
    assert "jail" not in rows  # a row id from before the python and runner plugins
    assert not {"actions", "fs", "approve", "guard"} & set(rows)  # the tool rows of before CodeAct
    assert rows["tools"].use == "agent:tools" and rows["loop"].config == {"requires": ["python"]}
    for row in rows.values():
        assert row.use is not None
        resolve(row.use)
    assert resolve(rows["chat"].use or "").name == "converse"
    assert resolve(rows["ui"].use or "").name == "ui"  # the TUI (tui:ui)
    assert resolve(rows["loop"].use or "").name == "loop"  # bh-02's own loop, whichever model
    assert rows["model"].use == "models:model" and rows["models"].use == "models:catalog"
    assert "completion" not in rows
    assert rows["transcript"].use == "agent:transcript"
    # the loop reads the prompt and asks `asides` on `executor`, a row that depends on nothing,
    # so /clear and /model, which reload the loop, keep the call a stopped reply left running
    assert rows["executor"].use == "agent:executor"
    assert resolve(rows["executor"].use or "").inject == set()
    assert "executor" in resolve(rows["loop"].use or "").inject
    assert resolve(rows["python"].use or "").name == "tool"  # CodeAct, whichever model
    # one rule decides whether the model's code runs unasked, for the loop, the extensions and
    # the python tool alike; it depends on the runner alone, so /clear leaves it up, and asking
    # the person is the asker's (the loop and the extensions depend on `output` for it)
    assert rows["approval"].use == "runner:approval"
    assert resolve(rows["approval"].use or "").inject == {"runner"}
    assert "output" in resolve(rows["loop"].use or "").inject
    # the jail field is a row of its own over the runner: /clear never reloads it
    assert rows["grades"].use == "tui:grades"
    assert resolve(rows["grades"].use or "").inject == {"runner", "approval", "frame", "output"}
    assert "runner" not in resolve(rows["status"].use or "").inject
    # `!COMMAND` is a layer's row, claiming its prefix in `commands`: no extension can
    assert rows["shell-command"].use == "commands:shell_command"
    assert resolve(rows["shell-command"].use or "").inject == {"commands"}
    # the model row names its model by `default`, which is None until a layer says one (then the
    # models file's `default`, else none); the status bar asks the models row which, so it needs
    # no default of its own
    chosen_by = resolve(rows["model"].use or "").config_type
    assert chosen_by is not None and chosen_by().default is None and rows["status"].config is None


async def test_a_composition_that_cannot_start_says_what_it_is_waiting_on(tmp_path: Path) -> None:
    layer = tmp_path / "broken.toml"
    layer.write_text('[[plugin]]\nid = "chat"\nuse = "chat:converse"\n')  # no loop, no ui
    with pytest.raises(CompositionError) as raised:
        await asyncio.wait_for(run([layer]), 2)
    assert "could not start" in raised.value.message
    assert "waiting on: commands, input, jobs, loop, output" in raised.value.message


async def test_a_chat_row_that_never_binds_done_fails_the_composition(
    composition: Callable[..., Path],
) -> None:
    """task-0008: `done` is now bh-02's own declared dependency (the `shell` row), not a
    hand-checked binding lookup — a row that activates but never binds it is an ordinary
    "waiting on" stall, diagnosed the same way a missing `loop`/`input`/`output` is."""
    layer = composition('[[plugin]]\nid = "chat"\nuse = "fragile:echo_model"\n')  # binds loop, not done
    with pytest.raises(CompositionError) as raised:
        await asyncio.wait_for(run([layer]), 2)
    assert "could not start" in raised.value.message
    assert "waiting on: done" in raised.value.message


async def test_a_done_binding_of_the_wrong_shape_is_a_contract_violation(
    composition: Callable[..., Path],
) -> None:
    """task-0008: the shape check is cordis's own check_contract now, not a hand-rolled
    isinstance -- a non-awaitable `done` fails `shell`'s own contract, not bh-02's bootstrap."""
    layer = composition('[[plugin]]\nid = "chat"\nuse = "fragile:bad_done_mode"\n')
    with pytest.raises(CompositionError) as raised:
        await asyncio.wait_for(run([layer]), 2)
    assert "could not start" in raised.value.message
    assert "is bound to a int, which" in raised.value.message


async def test_a_row_that_leaves_mid_run_is_reported_rather_than_a_silent_exit(
    composition: Callable[..., Path],
) -> None:
    layer = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:fragile_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:silent_ui"\n'
        '[[plugin]]\nid = "chat"\nuse = "chat:converse"\n'
        '[[plugin]]\nid = "commands"\nuse = "commands:registry"\n'
        '[[plugin]]\nid = "jobs"\nuse = "commands:jobs"\n'
    )
    with pytest.raises(CompositionError) as raised:
        await asyncio.wait_for(run([layer]), 2)
    assert "stopped early" in raised.value.message
    assert "waiting on: loop" in raised.value.message


async def test_the_shipped_stack_boots_around_a_patched_model(composition: Callable[..., Path]) -> None:
    """The python, commands and frame's rows are real; only the model is a fake. Nothing stalls."""
    patch = composition('[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n', one_reply=True)
    await asyncio.wait_for(run([*layers(), patch], [Row("chat", config={"prompt": "hi"})]), 2)


async def test_an_unrelated_providers_background_work_does_not_keep_run_from_returning(
    composition: Callable[..., Path],
) -> None:
    """The bug task-0006 fixes: Runtime.idle() is process-wide, so a heartbeat elsewhere used
    to keep `run()` waiting long after the chat row's own `done` task had finished."""
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "extra"\nuse = "fragile:heartbeat"\n',
        one_reply=True,
    )
    await asyncio.wait_for(run([*layers(), patch], [Row("chat", config={"prompt": "hi"})]), 2)


async def test_an_unrelated_providers_background_work_does_not_keep_an_interactive_session_open(
    composition: Callable[..., Path],
) -> None:
    """Same bug, the other chat row: an interactive session must still end when the input runs out,
    not wait on a heartbeat elsewhere (task-0006's literal "never ends on Ctrl-D")."""
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:one_message_ui"\n'
        '[[plugin]]\nid = "extra"\nuse = "fragile:heartbeat"\n'
    )
    await asyncio.wait_for(run([*layers(), patch]), 2)


async def test_caninputing_a_run_while_a_row_starts_cleans_up_promptly() -> None:
    """Ctrl-C during a slow startup must unwind, not wait for the slow piece to finish."""
    started = asyncio.Event()

    class Never:
        async def reply(self, message: str) -> AsyncIterator[dict[str, str]]:
            yield {"type": "text", "text": ""}  # pragma: no cover

    @component
    async def slow_loop() -> Effects:
        started.set()
        await asyncio.sleep(30)
        yield bind("loop", Never())

    async def compose() -> None:
        rt = Runtime()
        rt.mount(slow_loop, id="loop")
        try:
            await rt.idle()
        finally:
            await rt.shutdown(grace=0.05)

    running = asyncio.create_task(compose())
    await asyncio.wait_for(started.wait(), 2)
    running.cancel()
    (outcome,) = await asyncio.wait_for(asyncio.gather(running, return_exceptions=True), 2)
    assert isinstance(outcome, asyncio.CancelledError)  # cancelled cleanly, not a raising shutdown


async def test_editing_a_layer_file_reshapes_the_running_composition(
    composition: Callable[..., Path],
) -> None:
    """The layer files are the composition; a write to one is a reload."""
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:silent_ui"\n'
    )
    booted = await boot([*(str(x) for x in layers()), patch], watch=0.02)
    try:
        view = Inspection(booted.runtime)
        first = view.fiber("loop")
        assert first is not None and type(booted.runtime.root.get("loop")).__name__ == "Echo"
        chat = view.fiber("chat")

        patch.write_text(patch.read_text().replace("echo_model", "angry_model"))
        async with asyncio.timeout(2):
            while view.fiber("loop") is first:
                await asyncio.sleep(0.01)
        await booted.runtime.settle()
        assert type(booted.runtime.root.get("loop")).__name__ == "Angry"  # the loop row was swapped
        assert view.fiber("chat") is chat  # the chat row reloaded against it, in place (same fiber)
        assert view.fiber("ui") is not None and view.fiber("ui").state is State.ACTIVE
    finally:
        await booted.runtime.shutdown()


async def test_a_session_carries_on_when_its_loop_row_is_reloaded(
    composition: Callable[..., Path],
) -> None:
    """Reloading `loop` restarts the chat row (it depends on the loop), which binds a new
    `done`: the bootstrap follows it rather than ending the session (task-0010.02)."""
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:paced_ui"\n'
    )
    session = asyncio.create_task(run([*layers(), patch]))
    import fragile  # the module the fixture wrote, now imported by the composition

    async with asyncio.timeout(5):
        while fragile.SHOWN != ["one"]:
            await asyncio.sleep(0.02)
    patch.write_text(patch.read_text().replace("echo_model", "upper_model"))
    await asyncio.sleep(1.2)  # the loader polls the layer files every 0.5s
    assert not session.done(), "the session ended when its model was reloaded"
    fragile.SECOND.set()
    await asyncio.wait_for(session, 5)
    assert fragile.SHOWN == ["one", "TWO"]  # the second message went to the new model


async def test_stopping_replies_with_a_clear_or_a_model_switch_between_leaves_one_reading_running(
    composition: Callable[..., Path],
) -> None:
    """Ctrl-C while a slow section function reads the project, then /clear (or /model), again
    and again, in the shipped composition: a reading can't be stopped part-way, and /clear and
    /model reload the loop but not `system`, whose caches take no lock. The call in flight is
    the `executor` row's, which depends on nothing, so each new loop waits for the reading the
    last one left running. A loop that kept it itself started one more reading per round."""
    patch = composition(
        '[[plugin]]\nid = "model"\nuse = "fragile:counting_model"\n'
        '[[plugin]]\nid = "system"\nuse = "fragile:held_system"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:silent_ui"\n'
    )
    booted = await boot([*(str(x) for x in layers()), patch], watch=None)
    import fragile

    held = fragile.HELD
    try:
        try:
            for n, reload in enumerate(
                [("model",), ("loop", "transcript"), ("model",), ("loop", "transcript")]
            ):
                await booted.runtime.settle()
                reply = booted.runtime.root.get("loop").reply(f"go {n}")
                task = asyncio.create_task(anext(reply))
                async with asyncio.timeout(5):
                    while not held.begun:
                        await asyncio.sleep(0.01)
                await asyncio.sleep(0.05)  # time enough for this reply's own reading to begin, were it to
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await booted.loader.restart(*reload)  # what /clear and /model do to the loop
            assert (held.begun, held.running, held.most) == (1, 1, 1)
        finally:
            held.release.set()
        await booted.runtime.settle()
        said = [e async for e in booted.runtime.root.get("loop").reply("go on")]
        assert {"type": "text", "text": "seen 1"} in said  # a new conversation, answered
        assert (held.begun, held.most) == (2, 1)  # read afresh, once the one left behind was done
    finally:
        await booted.runtime.shutdown()


async def test_slash_commands_act_on_the_running_session(composition: Callable[..., Path]) -> None:
    """/rows and /clear go to the operator, not the model; /clear restarts the model and the
    Python process, and the session carries on and answers the next message."""
    patch = composition(
        '[[plugin]]\nid = "loop"\nuse = "fragile:echo_model"\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:scripted_ui"\n'
    )
    import fragile

    fragile.script("/rows", "/clear", "after", "/model", "/nope")
    await asyncio.wait_for(run([*layers(), patch]), 10)
    rows, cleared, model, unknown = fragile.NOTES
    assert "python" in rows and "python:tool" in rows and "active" in rows
    assert cleared == "the conversation was cleared; starting afresh: loop, transcript, python, agents"
    # no models file here, and no built-in models: /model lists none and says where to add them
    assert model.startswith("/model NAME switches; add models in ") and model.endswith("models.toml")
    assert unknown == "unknown command /nope; /help lists them"
    assert fragile.SHOWN == ["after"]  # only the message reached the model, after the restart


async def test_a_patch_row_with_no_use_that_no_layer_added_is_a_layer_error_naming_it(
    composition: Callable[..., Path],
) -> None:
    """cordis's `compose` refuses it with a ValueError; the run says it first, as a layer error that
    names the file, the row and what to add, and mounts nothing (`trace` hears every row's
    lifecycle from the first, so it hears nothing)."""
    patch = composition('[[plugin]]\nid = "nothing_before_me"\ndisabled = true\n')  # a patch row with no use
    heard: list[str] = []
    with pytest.raises(LayerError) as raised:
        await asyncio.wait_for(run([*layers(), patch], trace=heard.append), 5)
    message = raised.value.message
    assert message.startswith(f"{patch}: row 'nothing_before_me' has no `use`"), message
    assert 'add use = "plugin:component"' in message
    assert heard == []


async def test_a_row_that_cannot_resolve_stops_the_run_before_any_row_starts(
    composition: Callable[..., Path],
) -> None:
    """The ui row depends on nothing, so it starts at once and the app is drawn: a run that already
    knows a row's `use` names nothing says so first, mounting no row (`trace` hears nothing), and
    names the cause alone, not the rows that would have waited on it."""
    stale = composition('[[plugin]]\nid = "loop"\nuse = "nonesuch:loop"\n', one_reply=True)
    heard: list[str] = []
    with pytest.raises(NotStarted) as raised:
        await asyncio.wait_for(run([*layers(), stale], trace=heard.append), 10)
    message = raised.value.message
    assert message.startswith("could not start:\nloop: unresolved: "), message
    assert "use 'nonesuch:loop'" in message and "installed plugins: " in message
    assert "waiting on" not in message
    assert heard == []


async def test_the_line_for_a_row_that_cannot_resolve_is_the_one_the_loader_gives_it(
    composition: Callable[..., Path],
) -> None:
    """The run says it before the loader mounts a row, in the words the loader gives the same row
    once mounted (`/rows` shows them): the two are compared, so a change to one shows in the other."""
    stale = composition('[[plugin]]\nid = "loop"\nuse = "nonesuch:loop"\n')
    with pytest.raises(NotStarted) as raised:
        await asyncio.wait_for(run([stale]), 10)
    booted = await boot([stale], watch=None)
    try:
        assert raised.value.message == f"could not start:\nloop: {booted.loader.status()['loop']}"
    finally:
        await booted.runtime.shutdown()


async def test_a_shipped_layer_naming_a_use_no_plugin_provides_fails_at_boot_with_the_loader_s_error(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The shipped layer is read as every layer is, first: a row of it whose `use` no plugin
    provides is a boot failure that names the row, the use and the installed plugins, not a wait
    (here a copy of it names a plugin that does not exist, as a stale layer would)."""
    (shipped,) = layers()
    text = shipped.read_text()
    assert 'use = "agent:loop"' in text
    stale = tmp_path / "shipped.toml"
    stale.write_text(text.replace('use = "agent:loop"', 'use = "nonesuch:loop"'))
    with pytest.raises(NotStarted) as raised:
        await asyncio.wait_for(run([stale, composition("", one_reply=True)]), 10)
    assert "could not start" in raised.value.message
    assert "loop: unresolved:" in raised.value.message and "use 'nonesuch:loop'" in raised.value.message
    assert "installed plugins: " in raised.value.message
