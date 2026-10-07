"""`!COMMAND`: the shell-command row's value against a real shell, and the row on a runtime.

The commands run as the person, as they do in bh-02, in a temporary directory of the test's
own; each that leaves a program in the background ends it, or the test does."""

import asyncio
import contextlib
import os
import signal
import time
from pathlib import Path

import pytest

from commands_cordis_plugin import (
    Ran,
    ShellCommandConfig,
    answer,
    environment,
    registry,
    run_command,
    run_line,
    shell_command,
)
from cordis import Runtime, State

_TOLD = "(Before this message the person ran a shell command themselves, in bh-02, not in your REPL:)"
_NEXT = "the model reads this with your next message"


def _alive(pid: int) -> bool:
    """Whether `pid` runs: a zombie nobody reaped yet (a container's init may never) does not."""
    stat = Path(f"/proc/{pid}/stat")
    if Path("/proc/self").exists():  # Linux; darwin has no /proc
        try:
            return stat.read_text().rpartition(")")[2].split()[0] != "Z"
        except FileNotFoundError:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _written(path: Path) -> int:
    """The pid a command wrote to `path`, once it has."""
    async with asyncio.timeout(5):
        while not (path.exists() and path.read_text().strip()):
            await asyncio.sleep(0.02)
    return int(path.read_text())


def _config(tmp_path: Path, timeout: float = 30.0) -> ShellCommandConfig:
    return ShellCommandConfig(cwd=str(tmp_path), timeout=timeout, shell="/bin/sh")


async def test_a_command_runs_in_the_project_and_what_it_printed_is_shown_and_held_for_the_model(
    tmp_path: Path,
) -> None:
    here = tmp_path.resolve()
    note, told = await run_line("pwd; echo out; echo err >&2; exit 3", config=_config(tmp_path))
    assert note == {"type": "note", "text": f"{here}\nout\nerr\nexit status 3; {_NEXT}"}
    assert told == {
        "type": "for_model",
        "text": f"{_TOLD}\n$ pwd; echo out; echo err >&2; exit 3\n{here}\nout\nerr\n"
        "(End of what it printed; exit status 3.)",
    }


async def test_the_command_gets_no_terminal_and_no_input_since_the_app_owns_them(tmp_path: Path) -> None:
    """Its stdin is empty (a `cat` ends at once), its output is captured, and it is in a session
    of its own, so it can't open the terminal to draw over the app."""
    started = time.monotonic()
    ran = await run_command(
        "tty; cat; (echo drawn > /dev/tty) 2>/dev/null || echo no-terminal", _config(tmp_path)
    )
    assert ran == Ran(ran.command, "not a tty\nno-terminal\n", 0)
    assert time.monotonic() - started < 5


async def test_a_command_past_its_timeout_is_stopped_with_what_it_started(tmp_path: Path) -> None:
    started = time.monotonic()
    ran = await run_command("sleep 30 & echo $! > child; echo started; wait", _config(tmp_path, 0.5))
    assert time.monotonic() - started < 5
    assert ran.status is None and ran.output == "started\n"
    assert not _alive(int((tmp_path / "child").read_text()))  # the whole process group ended
    note, told = answer(ran, 0.5)
    assert note["text"] == (
        f"started\nstopped at its timeout, 0.5 s (the shell-command row's `timeout` sets it); {_NEXT}"
    )
    assert told["text"].endswith("started\n(End of what it printed; stopped at its timeout, 0.5 s.)")


async def test_a_command_that_closed_its_output_is_still_stopped_at_its_timeout(tmp_path: Path) -> None:
    """Its output ended long before it did: the timeout stops the command itself, not only
    the reading of what it printed."""
    ran = await run_command("echo $$ > shell; exec >/dev/null 2>&1; sleep 30", _config(tmp_path, 0.5))
    assert ran.status is None
    assert not _alive(int((tmp_path / "shell").read_text()))


async def test_a_program_left_holding_the_output_ends_with_the_command_one_that_let_go_does_not(
    tmp_path: Path,
) -> None:
    started = time.monotonic()
    ran = await run_command("sleep 30 & echo $! > held; echo done", _config(tmp_path))
    assert ran == Ran(ran.command, "done\n", 0) and time.monotonic() - started < 5
    assert not _alive(int((tmp_path / "held").read_text()))  # nobody would read what it printed
    ran = await run_command("sleep 30 > /dev/null 2>&1 & echo $! > free", _config(tmp_path))
    free = int((tmp_path / "free").read_text())
    try:
        assert ran.status == 0 and _alive(free)  # its output goes elsewhere: the person's to keep
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(free, signal.SIGKILL)


async def test_a_command_cancelled_while_it_runs_ends_with_its_process_group(tmp_path: Path) -> None:
    """bh-02 leaving (or the chat row restarting) cancels a command mid-run: nothing is left."""
    running = asyncio.ensure_future(run_command("sleep 30 & echo $! > child; wait", _config(tmp_path)))
    child = await _written(tmp_path / "child")
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert not _alive(child)


async def test_a_long_output_keeps_its_start_and_its_end(tmp_path: Path) -> None:
    ran = await run_command("head -c 100000 /dev/zero | tr '\\0' x; echo; echo the end", _config(tmp_path))
    assert ran.output.startswith("x" * 6_000 + "\n... [80009 bytes cut here] ...\nxxx")
    assert ran.output.endswith("x\nthe end\n") and len(ran.output) < 20_100


async def test_colour_a_program_writes_anyway_is_taken_out(tmp_path: Path) -> None:
    ran = await run_command(r"printf '\033[31mred\033[0m plain\n'", _config(tmp_path))
    assert ran.output == "red plain\n"


def test_the_host_s_own_variables_stay_out_of_the_command_s_environment() -> None:
    """What the command prints goes to the model, so a Claude credential the person exported, and
    what a launching Claude Code left, are not in its environment; the rest of bh-02's is."""
    given = {
        "PATH": "/bin",
        "HOME": "/home/me",
        "CLAUDE_CODE_OAUTH_TOKEN": "not-a-real-token",
        "CLAUDECODE": "1",
        "ANTHROPIC_BASE_URL": "https://example.invalid",
    }
    assert environment(given) == {"PATH": "/bin", "HOME": "/home/me"}


async def test_the_command_runs_in_bh_02_s_environment_less_the_host_s_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BH02_TEST_MARK", "kept")
    monkeypatch.setenv("CLAUDE_BH02_TEST_MARK", "leaked")
    ran = await run_command("echo $BH02_TEST_MARK ${CLAUDE_BH02_TEST_MARK:-dropped}", _config(tmp_path))
    assert ran.output == "kept dropped\n"


async def test_how_a_command_ended_is_said(tmp_path: Path) -> None:
    ran = await run_command("kill -TERM $$", _config(tmp_path))
    assert ran.status == -signal.SIGTERM
    note, told = answer(ran, 30)
    assert note["text"] == f"(it printed nothing)\nended by SIGTERM; {_NEXT}"
    assert told["text"] == f"{_TOLD}\n$ kill -TERM $$\n(End of what it printed; ended by SIGTERM.)"


async def test_an_empty_command_or_one_that_cannot_start_is_said_and_holds_nothing(tmp_path: Path) -> None:
    said = await run_line("", config=ShellCommandConfig())
    assert said == "type a shell command after !, such as !git status"
    said = await run_line("ls", config=ShellCommandConfig(shell=str(tmp_path / "no-such-shell")))
    assert isinstance(said, str) and said.startswith("couldn't run 'ls': ")
    said = await run_line("ls", config=ShellCommandConfig(cwd=str(tmp_path / "gone")))
    assert isinstance(said, str) and said.startswith("couldn't run 'ls': ")


async def test_the_person_s_own_shell_runs_it_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHELL", "/bin/sh")
    ran = await run_command("echo $0", ShellCommandConfig(cwd=str(tmp_path)))
    assert ran.output == "/bin/sh\n"


async def test_the_row_claims_its_prefix_in_the_broker_once_and_takes_it_when_it_leaves(
    tmp_path: Path,
) -> None:
    rt = Runtime()
    rt.mount(registry, id="commands")
    row = rt.mount(shell_command, id="shell-command", config={"cwd": str(tmp_path), "shell": "/bin/sh"})
    await rt.settle()
    commands = rt.root.get("commands")
    assert commands.claims("!echo hi") and not commands.claims("echo hi")
    note, told = await commands.run("!echo hi")
    assert note == {"type": "note", "text": f"hi\nexit status 0; {_NEXT}"}
    assert told["type"] == "for_model" and "$ echo hi\nhi\n" in told["text"]
    assert "!COMMAND  run COMMAND in your shell, here, as you" in await commands.run("/help")
    second = rt.mount(shell_command, id="another", config={"shell": "/bin/sh"})
    await rt.settle()
    assert second.state is State.FAILED  # one prefix, one row
    assert "a prefix named '!' is already registered" in str(second.error)
    other = rt.mount(shell_command, id="other", config={"prefix": "$", "cwd": str(tmp_path)})
    await rt.settle()
    assert other.state is State.ACTIVE and commands.claims("$ ls")
    await row.retire()
    await rt.settle()
    assert not commands.claims("!echo hi")  # the row took its prefix with it
    await rt.shutdown()
