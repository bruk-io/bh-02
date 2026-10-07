"""A real worker process, started unjailed: persistence, interrupt, restart, stop, and failures
that come back as the input's text."""

import asyncio
import os
import re
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
    kernel,
    worker_argv,
)


async def test_a_traceback_shows_each_line_and_the_input_it_came_from() -> None:
    async with Kernel(Unjailed(), KernelConfig()) as k:
        await k.run("def parse(line):\n    key, value = line.split('=')\n    return key, value")
        failed = await k.run("pairs = [parse(l) for l in ['a=1', 'c']]")
        assert 'File "<input 2>", line 1, in <module>\n    pairs = [parse(l)' in failed
        assert "File \"<input 1>\", line 2, in parse\n    key, value = line.split('=')" in failed


async def test_a_name_this_kernel_never_had_says_the_kernel_is_new() -> None:
    async with Kernel(Unjailed(), KernelConfig()) as k:
        missing = await k.run("helper()")
        assert "NameError" in missing and "'helper' has not been defined in this REPL" in missing
        assert "earlier session, or before /clear or a restart" in missing
        await k.run("helper = 1")
        await k.run("del helper")
        again = await k.run("helper")
        assert "NameError" in again and "has not been defined" not in again  # it had been: no hint


async def test_the_project_s_startup_file_runs_first_when_inputs_are_confined(tmp_path: Path) -> None:
    (tmp_path / ".bh-02").mkdir()
    (tmp_path / ".bh-02" / "kernel.py").write_text("def sh(cmd):\n    return cmd\n\nTOOLS = 2\n_hidden = 1\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        first = await k.run("sh('ls')")
        assert first == "(.bh-02/kernel.py ran first and defined: TOOLS, sh)\n'ls'"
        assert await k.run("TOOLS") == "2"  # told once, then plain inputs
    (tmp_path / ".bh-02" / "kernel.py").write_text("raise RuntimeError('broken helper')\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        failed = await k.run("1")
        assert (
            failed.startswith("(.bh-02/kernel.py ran first and failed")
            and "RuntimeError: broken helper" in failed
        )
        assert failed.endswith(")\n1")
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:  # unjailed: not unasked
        told = await k.run("1")
        assert told.startswith("(.bh-02/kernel.py was not run: inputs here are put to the person")
        assert "exec(open('.bh-02/kernel.py').read())" in told and "broken" not in told


def test_the_model_is_told_its_tool_is_a_repl_of_its_own_that_persists_and_how_to_use_it() -> None:
    told = instructions_for(True)
    assert told.startswith("Your one tool is `python`: a Python REPL of your own")
    assert "Your own Python REPL, which persists" in PYTHON["description"]
    # how long it lasts, and what empties it
    assert "persists for this run of bh-02" in told and "across a /model switch" in told
    # not a notebook: the habits a model brings from one fail here
    assert "not IPython or a notebook: no `!command` or `%magic`, and no top-level `await`" in told
    assert "a resumed session too" in told and "after /clear" in told
    # the ways an input's output can go missing, measured against a real worker below
    assert "capture_output=True" in told and "never reaches you" in told and "input() fails" in told
    assert "capture_output=True" in PYTHON["description"]
    # CodeAct, not a shell: the habit a model trained on shell tools brings
    assert "Work in Python, not through a shell" in PYTHON["description"]
    assert "Work in Python, not through a shell" in told and "keep what they found in variables" in told
    assert told.endswith("Inputs run without asking.") and instructions_for(False).endswith(
        "say what they do."
    )


async def test_a_program_s_own_output_reaches_an_input_only_when_captured(tmp_path: Path) -> None:
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        assert await k.run("import subprocess; subprocess.run(['echo', 'lost']).returncode") == "0"
        said = await k.run("print(subprocess.run(['echo', 'kept'], capture_output=True, text=True).stdout)")
        assert said == "kept"
        assert "EOFError" in await k.run("input()")


async def test_touched_is_the_project_s_files_the_last_input_opened(tmp_path: Path) -> None:
    """What `memory` is given: files read or written, not a directory listed, a module imported
    or a file a program read; and nothing outside the project."""
    (tmp_path / "src" / "db").mkdir(parents=True)
    (tmp_path / "src" / "db" / "models.py").write_text("X = 1\n")
    (tmp_path / "notes.md").write_text("n")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("o")
    root = tmp_path.resolve()
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        assert k.touched() == ()
        await k.run(
            "import os\nfrom pathlib import Path\n"
            "Path('src/db/models.py').read_text()\nopen('notes.md').read()\n"
            f"Path('new.txt').write_text('w')\nopen({str(outside)!r}).read()\nos.listdir('src')\n"
            "open('notes.md').read()"
        )
        assert k.touched() == (str(root / "src/db/models.py"), str(root / "notes.md"), str(root / "new.txt"))
        await k.run(
            "import sys, subprocess\nsys.path.insert(0, 'src/db')\nimport models\n"
            "subprocess.run(['cat', 'notes.md'], capture_output=True)"
        )
        assert k.touched() == ()
        await k.run("open('missing.md')")  # an input that failed still opened what it opened
        assert k.touched() == (str(root / "missing.md"),)


async def test_touched_is_not_misled_by_a_removal_that_opens_through_a_directory_s_descriptor(
    tmp_path: Path,
) -> None:
    """`shutil.rmtree` (and so a `TemporaryDirectory`'s cleanup) opens each directory by its name
    relative to its parent's descriptor, which the audit event leaves out: resolved against the
    working directory, removing a temporary `src/db` named the project's `src` and `db`. An
    `os.open` is not heard; an `open()` in the same input still is."""
    (tmp_path / "src" / "db").mkdir(parents=True)
    (tmp_path / "notes.md").write_text("n")
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        await k.run(
            "import os, shutil, tempfile\n"
            "with tempfile.TemporaryDirectory() as t:\n"
            "    os.makedirs(os.path.join(t, 'src', 'db'))\n"
            "    shutil.rmtree(os.path.join(t, 'src'))\n"
            "    os.makedirs(os.path.join(t, 'src', 'db'))\n"  # for the cleanup to remove
            "open('notes.md').read()"
        )
        assert k.touched() == (str(tmp_path.resolve() / "notes.md"),)


async def test_only_the_project_s_files_count_towards_the_most_touched_names(tmp_path: Path) -> None:
    """`touched` names at most 1,000 files, all of them the project's: an input that first opens
    more than that elsewhere (a temporary directory, site-packages) still names the project file
    it opens after them."""
    (tmp_path / "notes.md").write_text("n")
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        await k.run(
            "import os, tempfile\n"
            "with tempfile.TemporaryDirectory() as t:\n"
            "    for i in range(1_001):\n"
            "        open(os.path.join(t, f'{i}.txt'), 'w').close()\n"
            "open('notes.md').read()"
        )
        assert k.touched() == (str(tmp_path.resolve() / "notes.md"),)
        await k.run("for i in range(1_001):\n    open(f'{i}.txt', 'w').close()")
        assert len(k.touched()) == 1_000


async def test_an_open_with_no_python_frame_above_it_is_heard_and_goes_ahead(tmp_path: Path) -> None:
    """`open` called straight from a thread `_thread` started has no Python frame above the
    hook's own: it is not the import system's, so the file is heard, and the hook does not make
    the open fail."""
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        made = await k.run(
            "import _thread, os, time\n"
            "_thread.start_new_thread(open, ('threaded.txt', 'w'))\n"
            "deadline = time.monotonic() + 5\n"
            "while not os.path.exists('threaded.txt') and time.monotonic() < deadline:\n"
            "    time.sleep(0.01)\n"
            "os.path.exists('threaded.txt')"
        )
        assert made == "True"
        assert k.touched() == (str(tmp_path.resolve() / "threaded.txt"),)


async def test_hearing_an_open_calls_the_hook_twice_however_deep_the_stack(tmp_path: Path) -> None:
    """Every audited event calls the hook, the ones its own work raises included. Telling the
    import system's frames by their code (`f_code`, which is audited) called it once per frame,
    so an open 500 frames deep called it some 500 times; now it is the open and `_getframe`."""
    for name in ("shallow.md", "deep.md"):
        (tmp_path / name).write_text("x")
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        counted = await k.run(
            "import sys\n"
            "events = []\n"
            "counting = False\n"
            "def count(event, args):\n"
            "    if counting:\n"
            "        events.append(event)\n"
            "sys.addaudithook(count)\n"
            "def at(depth, name):\n"
            "    global counting\n"
            "    if depth:\n"
            "        return at(depth - 1, name)\n"
            "    events.clear()\n"
            "    counting = True\n"
            "    open(name).close()\n"
            "    counting = False\n"
            "    return sorted(events)\n"
            "at(0, 'shallow.md'), at(500, 'deep.md')"
        )
        assert counted == "(['open', 'sys._getframe'], ['open', 'sys._getframe'])"
        root = tmp_path.resolve()
        assert k.touched() == (str(root / "shallow.md"), str(root / "deep.md"))


async def test_formatting_a_failed_input_s_traceback_is_not_heard(tmp_path: Path) -> None:
    """A failed input's traceback reads the source file of each frame in it, after the input's
    own code has stopped: those are not files the input worked on."""
    (tmp_path / "helper.py").write_text("def fail():\n    raise ValueError('boom')\n")
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        failed = await k.run("import os, sys\nsys.path.insert(0, os.getcwd())\nimport helper\nhelper.fail()")
        assert "raise ValueError('boom')" in failed  # helper.py was read, to show its frame's line
        assert k.touched() == ()


class Confined(Unjailed):
    """The unjailed process, reported as confined: what a jail looks like to the kernel, without
    needing one on this platform."""

    def report(self) -> Mapping[str, str]:
        return {**UNENFORCED, "fs_write": "enforced", "network": "enforced"}


async def test_the_namespace_persists_and_the_last_expression_is_shown() -> None:
    async with Kernel(Unjailed(), KernelConfig()) as k:
        assert await k.run("x = 20") == "(no output)"
        assert await k.run("print('hello')\nx + 22") == "hello\n42"


async def test_the_kernel_is_the_one_tool_and_its_namespace_holds_only_what_inputs_put_there() -> None:
    async with Kernel(Unjailed(), KernelConfig()) as k:
        assert k.spec == PYTHON and k.spec["name"] == "python"
        assert "Path(p).read_text()" in k.instructions() and "unjailed" in k.instructions()
        names = await k.run("sorted(n for n in globals() if not n.startswith('__'))")
        assert names == "[]"  # no functions of the host's: an input is plain Python


async def test_a_confined_kernel_says_so_and_tells_the_model_it_runs_in_a_jail() -> None:
    async with Kernel(Confined(), KernelConfig()) as k:
        assert k.confined and "runs in a jail" in k.instructions()
        assert await k.run("6 * 7") == "42"


async def test_an_input_too_long_to_send_whole_comes_back_capped_and_the_kernel_carries_on() -> None:
    """20,000 emoji are 240 KB as JSON, and a traceback has no length of its own: both used to
    overrun the host's line limit and leave the stream out of step for every later input."""
    async with Kernel(Unjailed(), KernelConfig()) as k:
        await k.run("kept = 1")
        emoji = await k.run("print('\\N{GRINNING FACE}' * 30000 + 'the end')")
        # the start and the end are kept (a summary is last), and the whole is saved for an input
        assert emoji.startswith("\N{GRINNING FACE}" * 100) and emoji.endswith("the end")
        cut = re.search(r"\[10008 characters cut here; all of it is in (\S+)\]", emoji)
        assert cut is not None and len(emoji) < 20_200
        assert Path(cut.group(1)).read_text(encoding="utf-8").startswith("\N{GRINNING FACE}" * 30000)
        huge = await k.run("raise Exception('x' * 100000)")
        assert huge.startswith("Traceback") and "characters cut here" in huge and len(huge) < 20_200
        assert huge.endswith("x" * 100)  # the end of the error, where its message is
        assert await k.run("kept + 1") == "2"  # the same worker, its namespace intact


async def test_an_answer_that_cannot_be_read_restarts_the_kernel_instead_of_raising() -> None:
    """A worker that sends what the host can't read (here, a line that is not JSON) is replaced,
    and the input says so: nothing escapes `run` to end the session."""
    async with Kernel(Unjailed(), KernelConfig()) as k:
        await k.run("x = 1")
        garbled = await k.run(
            "import gc\n"
            "channel = next(o for o in gc.get_objects() if type(o).__name__ == '_Channel')\n"
            "channel._conn.sendall(b'not json\\n')"
        )
        assert garbled.startswith("error: the REPL's answer to this input could not be read"), garbled
        again = await k.run("'x' in globals()")
        assert again.startswith("(the REPL was started again") and again.endswith("False")


async def test_a_kernel_that_cannot_start_again_says_so_as_the_input_and_tries_again_next_time() -> None:
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
        assert refused.startswith("error: the REPL could not be started again (the jail is broken)")
        jail.refuse = False
        assert (await k.run("1 + 1")).endswith("2")


async def test_an_unjailed_input_does_not_inherit_a_claude_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "not-a-real-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://not-a-real-endpoint")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "not-a-real-token")  # a launching Claude Code's
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("BH_02_TEST_KEPT", "yes")
    async with Kernel(Unjailed(), KernelConfig()) as k:
        ran = await k.run(
            "import os\n"
            "sorted(n for n in os.environ if n.startswith(('CLAUDE', 'ANTHROPIC_'))), "
            "os.environ.get('BH_02_TEST_KEPT')"
        )
        assert ran == "([], 'yes')"  # Claude's variables are the host's; the rest is inherited


async def test_an_interrupted_input_stops_and_the_namespace_survives() -> None:
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
        assert "worker.py" not in failed and 'File "<input 1>", line 1' in failed  # the input's own
        deep = await k.run("def f():\n    open('/nonexistent/x')\nf()")
        assert deep.startswith("Traceback (most recent call last):")
        assert "worker.py" not in deep and deep.count('File "<input 2>"') == 2
        missing = await k.run("undefined_name")
        assert "NameError" in missing and "undefined_name" in missing
        await k.run("x = 1")
        died = await k.run("import os; os._exit(3)")
        assert "ended" in died
        again = await k.run("'x' in globals()")
        assert again.startswith("(the REPL was started again") and again.endswith("False")


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


async def test_a_worker_whose_host_goes_away_ends_even_mid_input() -> None:
    """If bh-02 dies while an input spins, the worker must not outlive it."""
    short = tempfile.mkdtemp(prefix="bh-t-", dir="/tmp")  # a socket path must fit in ~100 bytes
    endpoint = str(Path(short) / "k.sock")
    started = await Unjailed().start(worker_argv(endpoint), cwd=short, endpoint=endpoint)
    reader, writer = await asyncio.open_unix_connection(endpoint)
    writer.write(b'{"op": "hello"}\n{"op": "exec", "code": "while True: pass"}\n')
    await writer.drain()
    await asyncio.sleep(0.2)
    writer.close()  # the host goes away mid-input
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


async def test_touched_is_normalised_so_a_path_cannot_climb_out_of_the_project(tmp_path: Path) -> None:
    """The worker is the model's process, so what it says it opened is matched, never trusted: an
    input that writes into the worker's own record a path that climbs out of the project is not
    believed."""
    root = tmp_path.resolve()
    forged = str(root / ".." / "elsewhere" / "id_test")
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        await k.run(
            "import gc\n"
            "worker = next(o for o in gc.get_objects() if type(o).__name__ == '_Kernel')\n"
            f"worker._touched[{forged!r}] = None\n"
            f"worker._touched[{str(root / 'a' / '..' / 'b.md')!r}] = None"
        )
        assert k.touched() == (str(root / "b.md"),)
