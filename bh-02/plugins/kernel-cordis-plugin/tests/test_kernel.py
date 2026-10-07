"""A real worker process, started unjailed: persistence, interrupt, restart, stop, and failures
that come back as the input's text."""

import asyncio
import os
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from cordis import Effects, Runtime, bind, component
from cordis.testing import drive
from kernel_cordis_plugin import (
    PYTHON,
    UNENFORCED,
    Kernel,
    KernelConfig,
    Unjailed,
    instructions_for,
    kernel,
    release,
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


def _person_s(text: str | bytes) -> Path:
    """The person's own startup file, `$XDG_CONFIG_HOME/bh-02/kernel.py` (conftest gives each
    test a config directory of its own, outside its `tmp_path`), holding `text`."""
    path = Path(os.environ["XDG_CONFIG_HOME"]) / "bh-02" / "kernel.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    return path


def _project_s(root: Path, text: str) -> Path:
    """The project's startup file, `.bh-02/kernel.py` under `root`, holding `text`."""
    path = root / ".bh-02" / "kernel.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


async def test_the_person_s_startup_file_runs_before_the_project_s(tmp_path: Path) -> None:
    """Both files: the person's first, so its helpers are there for the project's, which may
    bind a name afresh; each is said with the names it defined, and leaves nothing else behind."""
    person = _person_s("def show(x):\n    return f'<{x}>'\n\nWIDTH = 80\n")
    _project_s(tmp_path, "def sh(cmd):\n    return show(cmd)\n\nWIDTH = 100\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        first = await k.run("sh('ls'), WIDTH")
        assert first == (
            f"({person} ran first and defined: WIDTH, show. "
            ".bh-02/kernel.py ran next and defined: WIDTH, sh)\n('<ls>', 100)"
        )
        assert await k.run("[n for n in globals() if n.startswith('_bh')]") == "[]"
        assert await k.run("show(1)") == "'<1>'"  # told once, then plain inputs


async def test_a_startup_file_that_is_not_there_is_passed_over(tmp_path: Path) -> None:
    person = _person_s("HELPER = 1\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:  # the project has none
        assert await k.run("HELPER") == f"({person} ran first and defined: HELPER)\n1"
    person.unlink()
    _project_s(tmp_path, "TOOLS = 2\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:  # the person has none
        assert await k.run("TOOLS") == "(.bh-02/kernel.py ran first and defined: TOOLS)\n2"
    (tmp_path / ".bh-02" / "kernel.py").unlink()
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:  # neither: nothing to tell
        assert await k.run("1") == "1"


async def test_a_failing_startup_file_says_why_and_the_next_one_still_runs(tmp_path: Path) -> None:
    """A failure is the file's traceback, its own lines shown (the person's from the source the
    host sent), and what ran before it stays, as at a REPL; the next file runs all the same."""
    person = _person_s("def show(x):\n    return x\n\n\nraise RuntimeError('broken person helper')\n")
    project = _project_s(tmp_path, "TOOLS = 2\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        first = await k.run("TOOLS")
        assert first.startswith(f"({person} ran first and failed, so what it defines is missing:\n")
        assert (
            f'File "{person}", line 5, in <module>\n' in first
            and "RuntimeError: broken person helper" in first
        )
        assert first.endswith(". .bh-02/kernel.py ran next and defined: TOOLS)\n2")
        assert await k.run("show(3)") == "3"
    person.write_text("HELPER = 1\n")
    project.write_text("raise ValueError('broken project helper')\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        first = await k.run("HELPER")
        assert first.startswith(
            f"({person} ran first and defined: HELPER. .bh-02/kernel.py ran next and failed, so what "
            "it defines is missing:\n"
        )
        assert "ValueError: broken project helper" in first and first.endswith(")\n1")
    _person_s(b"HELPER = '\xff'\n")  # not UTF-8: the host can't read it, and says so
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        told = await k.run("1")
        assert told.startswith(f"({person} could not be read ('utf-8' codec can't decode byte 0xff")
        assert "so what it defines is missing. .bh-02/kernel.py ran next and failed" in told


async def test_a_startup_file_that_ends_the_repl_is_named_and_passed_over_after(tmp_path: Path) -> None:
    """A file that ends the worker (os._exit, a crash) would end every new one: the input it
    cut short names it, and the workers after it pass it over, saying so, until `/restart kernel`
    (a new kernel) runs it again. The project's still runs."""
    person = _person_s("import os\nos._exit(3)\n")
    _project_s(tmp_path, "TOOLS = 2\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        ended = await k.run("1")
        assert ended == (
            f"the REPL's process ended as {person} ran, before this input, so this input did not run; "
            f"a new one starts with the next, without {person} (`/restart kernel` runs it again)"
        )
        passed = await k.run("TOOLS")
        assert passed.startswith(
            f"(the REPL was started again; what earlier inputs defined is gone. {person} was not run: it "
            "ended the REPL's process when it last ran, so what it defines is missing (`/restart kernel` "
            "runs it again). .bh-02/kernel.py ran next and defined: TOOLS)\n"
        ), passed
        assert passed.endswith("\n2") and await k.run("TOOLS + 1") == "3"


async def test_a_startup_file_stopped_part_way_is_not_run_again_in_that_repl(tmp_path: Path) -> None:
    """Ctrl-C as a startup file runs (it hangs, say) stops it; the next input runs in the same
    REPL without running the files again, and is told what was cut short. One that won't stop
    costs its REPL, and the next passes it over rather than hang again."""
    person = _person_s("import time\nA = 1\ntime.sleep(60)\nB = 2\n")
    _project_s(tmp_path, "TOOLS = 2\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        hanging = asyncio.create_task(k.run("1"))
        await asyncio.sleep(0.5)
        hanging.cancel()
        await asyncio.gather(hanging, return_exceptions=True)
        told = await asyncio.wait_for(k.run("sorted(n for n in globals() if not n.startswith('_'))"), 5)
    assert told == (
        f"({person} was stopped as it ran, so what it defines may be missing, and no startup file after "
        "it ran)\n['A', 'time']"
    ), told
    person.write_text(
        "import time\nwhile True:\n    try:\n        time.sleep(60)\n"
        "    except KeyboardInterrupt:\n        pass\n"
    )
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path), grace=0.5)) as k:  # one that won't stop
        hanging = asyncio.create_task(k.run("1"))
        await asyncio.sleep(0.5)
        hanging.cancel()
        await asyncio.gather(hanging, return_exceptions=True)
        told = await asyncio.wait_for(k.run("TOOLS"), 5)
    assert told == (
        f"(the REPL was started again; what earlier inputs defined is gone. {person} was not run: it would "
        "not stop at Ctrl-C when it last ran, so what it defines is missing (`/restart kernel` runs it "
        "again). .bh-02/kernel.py ran next and defined: TOOLS)\n2"
    ), told


async def test_a_startup_file_s_names_are_what_its_code_binds_on_a_line_of_their_own(tmp_path: Path) -> None:
    """A name each file binds is said even when it is bound to the object it already held
    (`WIDTH = 80` in both: one int), and what a file prints without a newline stays out of it."""
    person = _person_s("print('hello', end='')\nWIDTH = 80\n")
    _project_s(tmp_path, "WIDTH = 80\nTOOLS = 2\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        assert await k.run("WIDTH") == (
            f"({person} ran first and defined: WIDTH. "
            ".bh-02/kernel.py ran next and defined: TOOLS, WIDTH)\n80"
        )


async def test_a_startup_file_saved_with_a_byte_order_mark_runs(tmp_path: Path) -> None:
    """As `python file.py` runs it: a UTF-8 byte order mark (what some editors save) is no part of
    the source, read on the host or in the jail."""
    person = _person_s(b"\xef\xbb\xbfA = 1\n")
    (tmp_path / ".bh-02").mkdir()
    (tmp_path / ".bh-02" / "kernel.py").write_bytes(b"\xef\xbb\xbfB = 2\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        assert await k.run("A + B") == (
            f"({person} ran first and defined: A. .bh-02/kernel.py ran next and defined: B)\n3"
        )


def test_startup_is_a_file_name_or_a_list_of_them() -> None:
    """A layer's typo (a number in the list) is the row's config error, saying what to write,
    not an AttributeError from every request's instructions."""
    with pytest.raises(TypeError) as raised:
        KernelConfig(startup=[".bh-02/kernel.py", 1])  # type: ignore[list-item]
    assert str(raised.value) == (
        "`startup` must be a file name or a list of them, as in "
        '`startup = ["$XDG_CONFIG_HOME/bh-02/kernel.py", ".bh-02/kernel.py"]`, not [\'.bh-02/kernel.py\', 1]'
    )
    with pytest.raises(TypeError):
        KernelConfig(startup=3)  # type: ignore[arg-type]
    assert KernelConfig(startup="~/helpers.py").startup == "~/helpers.py"


async def test_unconfined_neither_startup_file_runs_unasked(tmp_path: Path) -> None:
    """Unjailed, a startup file would run with the person's permissions without them being
    asked: the model is told to run each as an input of its own, which the person is asked about."""
    person = _person_s("print('the person s ran unasked')\n")
    _project_s(tmp_path, "print('the project s ran unasked')\n")
    async with Kernel(Unjailed(), KernelConfig(root=str(tmp_path))) as k:
        told = await k.run("1")
    assert told == (
        f"({person} and .bh-02/kernel.py were not run: inputs here are put to the person, so run them "
        "as an input of your own if you want them: "
        f"exec(open({str(person)!r}).read()); exec(open('.bh-02/kernel.py').read()))\n1"
    )


async def test_the_person_s_startup_file_runs_in_a_jail_that_cannot_read_it(tmp_path: Path) -> None:
    """A Linux jail reads by allowlist and has no home directory, so the person's config
    directory is not in it: the host reads the person's file and sends its source, so it runs
    there all the same, its lines shown in a traceback. The project's is read in the jail."""
    person = _person_s("def show(x):\n    return 1 / x\n")
    _project_s(tmp_path, "TOOLS = 2\n")
    async with Kernel(Hiding(os.environ["XDG_CONFIG_HOME"]), KernelConfig(root=str(tmp_path))) as k:
        first = await k.run(f"open({str(person)!r})")
        assert first.startswith(
            f"({person} ran first and defined: show. .bh-02/kernel.py ran next and defined: TOOLS)\n"
        )
        assert "PermissionError: [Errno 13] the jail hides it" in first  # an input can't read it
        failed = await k.run("show(0)")
        assert f'File "{person}", line 2, in show\n    return 1 / x' in failed


async def test_a_person_s_file_whose_way_leads_through_the_project_is_read_only_in_the_jail(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The person's config directory is a link into the project (a dotfiles repository, say),
    where the model can write: it could make the file a link to one the jail hides, and the host
    would hand it over. So a person's file whose way passes through the project is read as the
    project's is: by the worker, in the jail, which decides. Each file runs once."""
    dotfiles = tmp_path / "dotfiles"
    (dotfiles / "bh-02").mkdir(parents=True)
    config = tmp_path_factory.mktemp("home") / "config"
    config.symlink_to(dotfiles)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    person = config / "bh-02" / "kernel.py"
    (dotfiles / "bh-02" / "kernel.py").write_text("HELPER = 1\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        assert await k.run("HELPER") == f"({person} ran first and defined: HELPER)\n1"
    hidden = tmp_path_factory.mktemp("hidden")
    (hidden / "secret.py").write_text("SECRET = 'a stand-in, not a secret'\n")
    (dotfiles / "bh-02" / "kernel.py").unlink()
    (dotfiles / "bh-02" / "kernel.py").symlink_to(hidden / "secret.py")  # what a model could do
    async with Kernel(Hiding(str(hidden)), KernelConfig(root=str(tmp_path))) as k:
        told = await k.run("'SECRET' in globals()")
        assert told.startswith(f"({person} ran first and failed") and "PermissionError" in told
        assert "stand-in" not in told and told.endswith(")\nFalse")
    (dotfiles / "bh-02" / "kernel.py").unlink()
    (dotfiles / "bh-02" / "kernel.py").symlink_to(_project_s(tmp_path, "TOOLS = 2\n"))
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:  # the project's own, once
        assert await k.run("TOOLS") == f"({person} ran first and defined: TOOLS)\n2"


async def test_run_from_the_home_directory_the_person_s_file_is_read_in_the_jail_and_still_theirs(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bh-02 run from the home directory: the person's config directory is in the project, where
    the model can write. Their file runs, read by the worker as the project's is (so a link the
    model planted there leads only where the jail lets it), and the model is still told it is
    the person's, not its own to edit."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME")
    person = tmp_path / ".config" / "bh-02" / "kernel.py"
    person.parent.mkdir(parents=True)
    person.write_text("HELPER = 1\n")
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        assert await k.run("HELPER") == f"({person} ran first and defined: HELPER)\n1"
        told = k.instructions()
        assert "go in .bh-02/kernel.py, the project's startup file" in told
        assert f"own in {person}, which comes before it, and that file is theirs." in told
    hidden = tmp_path_factory.mktemp("hidden")
    (hidden / "secret.py").write_text("SECRET = 'a stand-in, not a secret'\n")
    person.unlink()
    person.symlink_to(hidden / "secret.py")  # what a model could do
    async with Kernel(Hiding(str(hidden)), KernelConfig(root=str(tmp_path))) as k:
        told = await k.run("'SECRET' in globals()")
        assert told.startswith(f"({person} ran first and failed") and "PermissionError" in told
        assert "stand-in" not in told and told.endswith(")\nFalse")


async def test_a_person_s_file_whose_way_leads_through_any_root_an_input_writes_is_not_read_on_the_host(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not only the project: any root the jail lets an input write (`jail.writes()`, a `write`
    the person added) is where the model could have made the file a link to one the jail hides.
    The host reads nothing whose way passes through one, and when the jail then can't read it
    either, the note says why bh-02 did not."""
    project = tmp_path / "project"
    project.mkdir()
    dotfiles = tmp_path / "dotfiles"  # outside the project, but a root an input may write
    (dotfiles / "bh-02").mkdir(parents=True)
    config = tmp_path_factory.mktemp("home") / "config"
    config.symlink_to(dotfiles)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    person = config / "bh-02" / "kernel.py"
    hidden = tmp_path_factory.mktemp("hidden")
    (hidden / "secret.py").write_text("SECRET = 'a stand-in, not a secret'\n")
    (dotfiles / "bh-02" / "kernel.py").symlink_to(hidden / "secret.py")  # what a model could do
    async with Kernel(Writing(str(hidden), [str(dotfiles)]), KernelConfig(root=str(project))) as k:
        told = await k.run(
            "import linecache\n'SECRET' in globals(), linecache.getlines(" + repr(str(person)) + ")"
        )
    assert told.startswith(
        f"({person} ran first and failed (its way passes through {dotfiles}, where inputs can write, so "
        "bh-02 left it to the jail), so what it defines is missing:\n"
    ), told
    assert "PermissionError" in told and "stand-in" not in told and told.endswith(")\n(False, [])")
    (dotfiles / "bh-02" / "kernel.py").unlink()
    (dotfiles / "bh-02" / "kernel.py").write_text("HELPER = 1\n")
    async with Kernel(Writing(str(hidden), [str(dotfiles)]), KernelConfig(root=str(project))) as k:
        assert await k.run("HELPER") == f"({person} ran first and defined: HELPER)\n1"  # read in the jail


async def test_a_startup_file_is_named_from_home_or_the_config_directory_on_the_host(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`~/` and `$XDG_CONFIG_HOME/` (that variable's value, else `~/.config`, as for the context
    file) are the host's to expand: the jail has no home in it."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME")
    (home / ".config" / "bh-02").mkdir(parents=True)
    (home / ".config" / "bh-02" / "kernel.py").write_text("A = 1\n")
    (home / "helpers.py").write_text("B = 2\n")
    config = KernelConfig(
        root=str(tmp_path), startup=("$XDG_CONFIG_HOME/bh-02/kernel.py", "~/helpers.py", ".bh-02/kernel.py")
    )
    async with Kernel(Hiding(str(home)), config) as k:
        assert await k.run("A + B") == (
            f"({home}/.config/bh-02/kernel.py ran first and defined: A. "
            f"{home}/helpers.py ran next and defined: B)\n3"
        )
        told = k.instructions()
        assert f"helpers of their own in {home}/.config/bh-02/kernel.py and {home}/helpers.py" in told
    one = KernelConfig(root=str(tmp_path), startup="~/helpers.py")  # a single string is one file
    async with Kernel(Confined(), one) as k:
        assert await k.run("B") == f"({home}/helpers.py ran first and defined: B)\n2"


def test_the_model_is_told_only_the_project_s_startup_file_is_its_to_edit() -> None:
    mine, theirs = (".bh-02/kernel.py",), ("/home/me/.config/bh-02/kernel.py",)
    for confined in (True, False):
        told = instructions_for(confined, mine, theirs=theirs)
        assert "go in .bh-02/kernel.py, the project's startup file, which you can write and grow" in told
        assert (
            "Only the project's startup file is yours to edit: the person may keep helpers of their "
            "own in /home/me/.config/bh-02/kernel.py, which comes before it, and that file is theirs."
        ) in told
    assert "Only the project's" not in instructions_for(True)  # no file of the person's to name
    alone = instructions_for(True, (), theirs=theirs)  # only the person's
    assert "go in" not in alone and "That file is theirs, not yours to edit." in alone


def test_under_an_allowlist_the_model_is_told_how_to_see_the_person_s_helpers() -> None:
    """A Linux jail has no home directory in it: the person's helpers run (the host sent their
    source), but the model's code finds no such file to open, so it is told what shows one."""
    mine, theirs, reads = (".bh-02/kernel.py",), ("/home/me/.config/bh-02/kernel.py",), ("/usr", "/w/app")
    told = instructions_for(True, mine, reads, theirs=theirs)
    assert "finds no such file (bh-02 reads it for the REPL): inspect.getsource(helper) shows one" in told
    assert "inspect.getsource" not in instructions_for(True, mine, reads)  # no file of the person's
    assert "inspect.getsource" not in instructions_for(True, mine, (), theirs=theirs)  # it reads everything


async def test_the_kernel_tells_the_model_where_the_person_s_startup_file_is(tmp_path: Path) -> None:
    """By its place on this machine, `$XDG_CONFIG_HOME` expanded, though there is no file yet."""
    async with Kernel(Confined(), KernelConfig(root=str(tmp_path))) as k:
        told = k.instructions()
    person = Path(os.environ["XDG_CONFIG_HOME"]) / "bh-02" / "kernel.py"
    assert "go in .bh-02/kernel.py, the project's startup file" in told
    said = "Only the project's startup file is yours to edit: the person may keep helpers of their own in"
    assert f"{said} {person}, which comes before it" in told


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


# The worker, run under an audit hook that refuses to open anything under a directory (the
# first argument), wherever a link leads from: a jail with no such directory in it.
_HIDING = """
import os, runpy, sys
hidden = os.path.join(os.path.realpath(sys.argv[1]), "")
def hook(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        if os.path.realpath(os.fsdecode(args[0])).startswith(hidden):
            raise PermissionError(13, "the jail hides it", os.fsdecode(args[0]))
sys.addaudithook(hook)
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


class Hiding(Confined):
    """A confined jail with no `hidden` directory in it, as a Linux jail has no home directory
    (and no secret) in it: the worker can open nothing under `hidden`."""

    def __init__(self, hidden: str) -> None:
        self._hidden = hidden

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> Any:
        executable, isolated, *worker = argv
        return await super().start(
            [executable, isolated, "-c", _HIDING, self._hidden, *worker], cwd=cwd, endpoint=endpoint
        )


class Writing(Hiding):
    """A `Hiding` jail that lets an input write `roots` besides the project (brig's `write`)."""

    def __init__(self, hidden: str, roots: Sequence[str]) -> None:
        super().__init__(hidden)
        self._roots = tuple(roots)

    def writes(self) -> tuple[str, ...]:
        return self._roots


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


class Ending(Unjailed):
    """A jail that ends its worker itself and says why (`started.ended()`), as a Linux
    `brig:jail` does when the host undoes one of its holds."""

    def __init__(self) -> None:
        super().__init__()
        self.why = ""

    async def start(self, argv: Sequence[str], *, cwd: str, endpoint: str) -> Any:
        started = await super().start(argv, cwd=cwd, endpoint=endpoint)
        jail = self

        class Said:
            def interrupt(self) -> bool:
                return started.interrupt()

            def ended(self) -> str:
                return jail.why

            async def stop(self) -> None:
                jail.why = ""
                await started.stop()

        return Said()


async def test_a_worker_its_jail_ended_between_inputs_is_started_again_for_the_next() -> None:
    """The jail can say it ended the worker before the end of its socket has reached the kernel
    (nothing has run on bh-02's event loop since): the next input still runs, in a new worker,
    told why, and is not sent to the one that ended."""
    jail = Ending()
    async with Kernel(jail, KernelConfig()) as k:
        pid = int(await k.run("import os; x = 1; os.getpid()"))
        jail.why = "something on the host replaced /p/.git/config"
        os.killpg(pid, 9)
        time.sleep(0.5)  # the worker is gone, and the event loop has not run since
        again = await k.run("'x' in globals()")
        assert again.startswith(
            "(the REPL was started again, because something on the host replaced /p/.git/config"
        ), again
        assert again.endswith("False")


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


class Holding(Unjailed):
    """A jail that holds something on the host while it runs, and says what `release` freed."""

    def __init__(self) -> None:
        self.released = 0

    async def release(self) -> str:
        self.released += 1
        return "Nothing holds /w/local.env until the kernel starts again."


async def test_release_ends_the_worker_now_and_the_next_input_starts_another() -> None:
    """`/release`: the worker ends at once (so its jail lets go of what it holds on the host),
    the jail says what it freed, and the next input starts a new worker, told its variables went."""
    jail = Holding()
    async with Kernel(jail, KernelConfig()) as k:
        await k.run("kept = 1")
        said = await k.release()
        assert said.startswith("The kernel is stopped")
        assert said.endswith("Nothing holds /w/local.env until the kernel starts again.")
        assert jail.released == 1
        again = await k.run("'kept' in globals()")
        assert again.startswith("(the REPL was started again") and again.endswith("False")


async def test_release_while_an_input_runs_leaves_it_alone_and_says_so() -> None:
    jail = Holding()
    async with Kernel(jail, KernelConfig()) as k:
        running = asyncio.ensure_future(k.run("import time; time.sleep(1); 'done'"))
        await asyncio.sleep(0.3)
        said = await k.release()
        assert "An input is running" in said and jail.released == 0
        assert await running == "'done'"


async def test_an_unjailed_kernel_holds_nothing_to_release() -> None:
    assert await Unjailed().release() == ""


async def test_the_release_row_offers_slash_release_over_the_kernel() -> None:
    registered: list[tuple[Mapping[str, Any], Any]] = []

    class Commands:
        def register(self, spec: Mapping[str, Any], run: Any) -> Any:
            registered.append((spec, run))
            return lambda: None

    async with Kernel(Holding(), KernelConfig()) as k:
        effects = await drive(release(kernel=k, commands=Commands()))
        assert [e.name for e in effects] == ["acquire"]
        effects[0].args[0](*effects[0].args[1:])
        ((spec, run),) = registered
        assert spec["name"] == "release" and "credential" in spec["help"]
        assert (await run("")).startswith("The kernel is stopped")
