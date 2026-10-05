"""A real worker process, started unjailed: persistence, interrupt, restart, stop, and failures
that come back as the cell's text."""

import asyncio
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from cordis import Effects, Runtime, bind, component
from kernel_cordis_plugin import (
    PYTHON,
    UNENFORCED,
    Kernel,
    KernelConfig,
    Unjailed,
    instructions_for,
    is_confined,
    kernel,
    worker_argv,
)


def test_the_model_is_told_its_tool_is_a_persistent_kernel_and_how_to_use_it() -> None:
    told = instructions_for(True)
    assert told.startswith("Your one tool is `python`, the CodeAct tool bh-02 ships with")
    # how long the namespace lasts, and what empties it
    assert "lasts as long as this run of bh-02" in told and "across a /model switch" in told
    assert "a resumed session too" in told and "after /clear" in told
    # the ways a cell's output can go missing, measured against a real worker below
    assert "capture_output=True" in told and "never reaches you" in told and "input() fails" in told
    assert "capture_output=True" in PYTHON["description"]
    assert told.endswith("Cells run without asking.") and instructions_for(False).endswith(
        "say what they do."
    )


async def test_a_program_s_own_output_reaches_a_cell_only_when_captured(tmp_path: Path) -> None:
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        assert await k.run("import subprocess; subprocess.run(['echo', 'lost']).returncode") == "0"
        said = await k.run("print(subprocess.run(['echo', 'kept'], capture_output=True, text=True).stdout)")
        assert said == "kept"
        assert "EOFError" in await k.run("input()")


class Confined(Unjailed):
    """The unjailed process, reported as confined: what a jail looks like to the kernel, without
    needing one on this platform."""

    def report(self) -> Mapping[str, str]:
        return {**UNENFORCED, "fs_write": "enforced", "network": "enforced"}


async def test_the_namespace_persists_and_the_last_expression_is_shown() -> None:
    async with Kernel(Unjailed(), KernelConfig()) as k:
        assert await k.run("x = 20") == "(no output)"
        assert await k.run("print('hello')\nx + 22") == "hello\n42"


async def test_the_kernel_is_the_one_tool_and_its_namespace_holds_only_what_cells_put_there() -> None:
    async with Kernel(Unjailed(), KernelConfig()) as k:
        assert k.spec == PYTHON and k.spec["name"] == "python"
        assert "open() or pathlib" in k.instructions() and "unjailed" in k.instructions()
        names = await k.run("sorted(n for n in globals() if not n.startswith('__'))")
        assert names == "[]"  # no functions of the host's: a cell is plain Python


async def test_a_confined_kernel_says_so_and_tells_the_model_it_runs_in_a_jail() -> None:
    async with Kernel(Confined(), KernelConfig()) as k:
        assert k.confined and "runs in a jail" in k.instructions()
        assert await k.run("6 * 7") == "42"


async def test_a_cell_too_long_to_send_whole_comes_back_capped_and_the_kernel_carries_on() -> None:
    """20,000 emoji are 240 KB as JSON, and a traceback has no length of its own: both used to
    overrun the host's line limit and leave the stream out of step for every later cell."""
    async with Kernel(Unjailed(), KernelConfig()) as k:
        await k.run("kept = 1")
        emoji = await k.run("print('\\N{GRINNING FACE}' * 30000)")
        assert emoji.startswith("\N{GRINNING FACE}" * 100) and emoji.endswith("[10001 more chars]")
        huge = await k.run("raise Exception('x' * 100000)")
        assert huge.startswith("Traceback") and "more chars]" in huge and len(huge) < 21_000
        assert await k.run("kept + 1") == "2"  # the same worker, its namespace intact


async def test_an_answer_that_cannot_be_read_restarts_the_kernel_instead_of_raising() -> None:
    """A worker that sends what the host can't read (here, a line that is not JSON) is replaced,
    and the cell says so: nothing escapes `run` to end the session."""
    async with Kernel(Unjailed(), KernelConfig()) as k:
        await k.run("x = 1")
        garbled = await k.run(
            "import gc\n"
            "channel = next(o for o in gc.get_objects() if type(o).__name__ == '_Channel')\n"
            "channel._conn.sendall(b'not json\\n')"
        )
        assert garbled.startswith("error: the kernel's answer to this cell could not be read"), garbled
        again = await k.run("'x' in globals()")
        assert again.startswith("(the kernel was started again") and again.endswith("False")


async def test_a_kernel_that_cannot_start_again_says_so_as_the_cell_and_tries_again_next_time() -> None:
    class Flaky(Unjailed):
        def __init__(self) -> None:
            super().__init__()
            self.refuse = False

        async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> Any:
            if self.refuse:
                raise RuntimeError("the jail is broken")
            return await super().start(argv, cwd=cwd, endpoint=endpoint)

    jail = Flaky()
    async with Kernel(jail, KernelConfig()) as k:
        assert "ended" in await k.run("import os; os._exit(3)")
        jail.refuse = True
        refused = await k.run("1 + 1")
        assert refused.startswith("error: the kernel could not be started again (the jail is broken)")
        jail.refuse = False
        assert (await k.run("1 + 1")).endswith("2")


async def test_an_unjailed_cell_does_not_inherit_a_claude_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "not-a-real-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://not-a-real-endpoint")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "not-a-real-token")  # a launching Claude Code's
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("BH_02_TEST_KEPT", "yes")
    async with Kernel(Unjailed(), KernelConfig()) as k:
        cell = await k.run(
            "import os\n"
            "sorted(n for n in os.environ if n.startswith(('CLAUDE', 'ANTHROPIC_'))), "
            "os.environ.get('BH_02_TEST_KEPT')"
        )
        assert cell == "([], 'yes')"  # Claude's variables are the host's; the rest is inherited


async def test_an_interrupted_cell_stops_and_the_namespace_survives() -> None:
    async with Kernel(Unjailed(), KernelConfig()) as k:
        await k.run("kept = 'still here'")
        spinning = asyncio.create_task(k.run("while True: pass"))
        await asyncio.sleep(0.3)
        spinning.cancel()
        await asyncio.gather(spinning, return_exceptions=True)
        assert await k.run("kept") == "'still here'"


async def test_errors_come_back_as_text_and_a_dead_worker_is_started_again() -> None:
    async with Kernel(Unjailed(), KernelConfig()) as k:
        failed = await k.run("1/0")
        assert "ZeroDivisionError" in failed
        assert "worker.py" not in failed and 'File "<cell>", line 1' in failed  # the cell's own
        deep = await k.run("def f():\n    open('/nonexistent/x')\nf()")
        assert deep.startswith("Traceback (most recent call last):")
        assert "worker.py" not in deep and deep.count('File "<cell>"') == 2
        missing = await k.run("undefined_name")
        assert "NameError" in missing and "undefined_name" in missing
        await k.run("x = 1")
        died = await k.run("import os; os._exit(3)")
        assert "ended" in died
        again = await k.run("'x' in globals()")
        assert again.startswith("(the kernel was started again") and again.endswith("False")


async def test_the_row_starts_the_worker_and_leaving_stops_it() -> None:
    @component
    async def jail() -> Effects:
        yield bind("jail", Unjailed())

    rt = Runtime()
    rt.mount(jail, id="jail")
    row = rt.mount(kernel, id="kernel")
    await rt.settle()
    k = rt.root.get("kernel")
    pid = int(await k.run("import os; os.getpid()"))
    assert not k.confined and k.report() == UNENFORCED
    await row.retire()
    await rt.settle()
    await asyncio.sleep(0.1)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError("the worker outlived its row")
    await rt.shutdown()


def test_confined_means_writes_and_network_are_enforced() -> None:
    assert is_confined({"fs_write": "enforced", "network": "enforced", "fs_read": "unenforced"})
    assert not is_confined({"fs_write": "enforced", "network": "best_effort"})
    assert not is_confined(UNENFORCED)


async def test_a_worker_whose_host_goes_away_ends_even_mid_cell() -> None:
    """If bh-02 dies while a cell spins, the worker must not outlive it."""
    short = tempfile.mkdtemp(prefix="bh-t-", dir="/tmp")  # a socket path must fit in ~100 bytes
    endpoint = str(Path(short) / "k.sock")
    started = await Unjailed().start(worker_argv(endpoint), cwd=short, endpoint=endpoint)
    reader, writer = await asyncio.open_unix_connection(endpoint)
    writer.write(b'{"op": "hello"}\n{"op": "exec", "code": "while True: pass"}\n')
    await writer.drain()
    await asyncio.sleep(0.2)
    writer.close()  # the host goes away mid-cell
    try:
        await asyncio.wait_for(started.stopped(), 5)
    finally:
        await started.stop()
        shutil.rmtree(short, ignore_errors=True)


def _short_dir() -> str:
    return tempfile.mkdtemp(prefix="bh-kt-", dir="/tmp")  # a Unix socket path must be short


async def test_a_worker_nobody_says_hello_to_exits_by_itself() -> None:
    """A host killed while starting its worker never connects: the worker gives up, rather
    than wait in `accept` for ever."""
    where = _short_dir()
    try:
        worker = await asyncio.create_subprocess_exec(*worker_argv(f"{where}/k.sock"), "0.5")
        async with asyncio.timeout(10):
            assert await worker.wait() == 0
    finally:
        shutil.rmtree(where, ignore_errors=True)


async def test_a_worker_whose_parent_is_gone_before_its_hello_exits() -> None:
    """The unjailed case: bh-02 (the parent) killed mid-start leaves the worker to init."""
    where = _short_dir()
    starter = (
        "import subprocess, sys\n"
        "import os, time\n"
        "p = subprocess.Popen(sys.argv[1:], start_new_session=True, stdout=subprocess.DEVNULL)\n"
        "while not os.path.exists(sys.argv[-1]): time.sleep(0.02)\n"  # listening: mid-start
        "print(p.pid, flush=True)\n"
    )
    try:
        parent = await asyncio.create_subprocess_exec(
            sys.executable, "-c", starter, *worker_argv(f"{where}/k.sock"), stdout=asyncio.subprocess.PIPE
        )
        out, _ = await parent.communicate()
        pid = int(out)
        started = asyncio.get_running_loop().time()
        async with asyncio.timeout(10):
            while True:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break  # gone (init reaps it)
                await asyncio.sleep(0.1)
        assert asyncio.get_running_loop().time() - started < 5  # its parent, not its deadline
    finally:
        shutil.rmtree(where, ignore_errors=True)
