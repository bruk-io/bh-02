"""The python tool booted from the shipped layers: a real loop, kernel and jail; only the model
is a fake, which calls scripted inputs. An input is plain Python: it reads and writes files and
runs programs itself, the jail decides what it may touch, and unjailed every input is asked about."""

import asyncio
import contextlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import cordis
import memory_cordis_plugin
from agent_cordis_plugin import ToolBroker
from bh_02.bootstrap import (
    code_directories,
    code_packages,
    config_directories,
    credential_files,
    layers,
    run,
    unreadable,
)
from cordis import Row
from cordis.loader import boot
from extensions_cordis_plugin import Extensions, ExtensionsConfig
from models_cordis_plugin.local_env import token_file
from python_cordis_plugin import Kernel, KernelConfig, worker_argv
from runner_cordis_plugin import Approval, BrigConfig, BrigJail, Runner, recorded_group, self_modify_denied

# darwin's jail (seatbelt) reads by denylist: everything but the secrets. Linux's (bubblewrap)
# reads by allowlist: the system, the interpreter and the project, so a file anywhere else is
# absent there, not merely hidden.
_READS_EVERYWHERE_ELSE = sys.platform == "darwin"
_BWRAP = "/usr/bin/bwrap"


@pytest.fixture
def _needs_a_jail() -> None:
    """runner:confined runs on darwin (seatbelt) and on Linux with bubblewrap installed. A fixture,
    not `skipif`: looking for the binary at import time is an import-time side effect."""
    if sys.platform not in ("darwin", "linux"):
        pytest.skip(f"runner:confined runs on darwin and Linux; this is {sys.platform}")
    if sys.platform == "linux" and not Path(_BWRAP).exists():
        pytest.skip(
            f"runner:confined on Linux needs bubblewrap at {_BWRAP}; install the `bubblewrap` package"
        )


def _shown() -> str:
    import fragile  # the module the fixture wrote, imported by the composition

    return str(fragile.shown())


def _asked() -> list[str]:
    """The code of every input the person was asked about."""
    import fragile

    return [str(request["input"]["code"]) for request in fragile.ASKED]


def _answers(*these: bool) -> None:
    import fragile

    fragile.answers(*these)


def _inputs(composition: Callable[..., Path], *inputs: str, extra: str = "") -> Path:
    code = json.dumps(list(inputs))
    return composition(
        f'[[plugin]]\nid = "model"\nuse = "fragile:input_model"\nconfig = {{ code = {code} }}\n' + extra,
        one_reply=True,
    )


def _jailed_in(project: Path) -> str:
    """Layer rows that put the kernel in `project`, inside brig's jail (the fixture's layers
    default to no jail)."""
    return (
        f'[[plugin]]\nid = "python"\nconfig = {{ root = "{project}" }}\n'
        '[[plugin]]\nid = "runner"\nuse = "runner:confined"\n'
    )


async def test_unjailed_inputs_share_a_namespace_of_plain_python_and_each_is_asked_about(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    (tmp_path / "note.txt").write_text("read with open()")
    inputs = (
        "x = 6 * 7",
        "x",
        f"open({str(tmp_path / 'note.txt')!r}).read()",
        "sorted(n for n in globals() if not n.startswith('__'))",
        "undefined_name",
        f"open({str(tmp_path / 'declined.txt')!r}, 'w').write('x')",
    )
    patch = _inputs(composition, *inputs)
    _answers(True, True, True, True, True, False)
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert _asked() == list(inputs)  # every input, with its code, before it ran
    assert "[1] 42" in out  # the namespace outlived the input that set it
    assert "[2] 'read with open()'" in out  # a file, read with plain Python
    assert "[3] ['x']" in out  # nothing in the namespace but what inputs put there
    assert "[4] Traceback" in out and "NameError" in out
    assert "[5] denied: the person said no to this call" in out
    assert not (tmp_path / "declined.txt").exists()  # a no ran nothing


async def test_an_input_calls_another_row_s_tool_as_a_function_put_to_the_person_as_the_model_s_call_is(
    composition: Callable[..., Path],
) -> None:
    """Booted from the shipped layers with a layer row's `echo` tool: an input calls it as
    `tools.echo(...)`, and the call goes through the loop as the model's own would, put to the
    person (it runs in bh-02's own process) and run only on a yes; a no raises `tools.Error`."""
    patch = _inputs(
        composition,
        "print(tools.echo(text='from code'))",
        "try:\n    tools.echo(text='again')\nexcept tools.Error as error:\n    print('not run:', error)",
        extra='[[plugin]]\nid = "echo"\nuse = "fragile:echo_tool"\n',
    )
    _answers(True, True, True, False)  # the first input, its call; the second input, not its call
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    import fragile

    assert [request["name"] for request in fragile.ASKED] == ["python", "echo", "python", "echo"]
    echo = fragile.ASKED[1]
    assert echo["runs"] == "host" and echo["input"] == {"text": "from code"}
    assert "[0] (bh-02's other tools are functions in your namespace: tools.echo;" in out
    assert "echo: from code" in out
    assert "[1] not run: denied: the person said no to this call" in out


async def test_unjailed_an_input_and_an_extension_are_both_put_to_the_person_by_the_approval_row(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The loop and the extensions row ask one `approval` row, which asks through the ui."""
    project = tmp_path / "project"
    plugins = project / ".bh-02" / "plugins"
    plugins.mkdir(parents=True)
    source = "from cordis import Effects, component\n"
    (plugins / "todo.py").write_text(source)
    extensions = f'[[plugin]]\nid = "extensions"\nconfig = {{ root = "{project}" }}\n'
    patch = _inputs(composition, "6 * 7", extra=extensions)
    _answers(False, False)  # which is asked first is a race between two rows: both are noes
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    assert sorted(_asked()) == sorted([source, "6 * 7"])
    assert "[0] denied: the person said no to this call" in _shown()
    status = json.loads((plugins / "status.json").read_text())
    assert status["todo"]["error"] == "the person declined to load it"


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_input_does_coding_work_in_the_project_without_asking(
    composition: Callable[..., Path],
    tmp_path: Path,
) -> None:
    """Write a new file, edit an existing one, and run programs (python, git in a repository the
    project already is), all with plain Python in the project directory; nothing is asked about.
    `git init` is not among them: the jail denies writing `.git/config`."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "greet.py").write_text("def greet():\n    return 'hi'\n")
    git = shutil.which("git")
    if git:  # the project is a repository already, made outside the jail
        subprocess.run([git, "init", "-q"], cwd=project, check=True)
        subprocess.run([git, "config", "user.email", "t@example.invalid"], cwd=project, check=True)
        subprocess.run([git, "config", "user.name", "t"], cwd=project, check=True)
    inputs = [
        "from pathlib import Path\nPath('new.py').write_text('X = 1\\n')\n"
        "print(sorted(p.name for p in Path('.').glob('*.py')))",
        "p = Path('greet.py')\np.write_text(p.read_text().replace(\"'hi'\", \"'hello'\"))\n"
        "print(p.read_text())",
        "import subprocess, sys\n"
        "print(subprocess.run([sys.executable, '-B', '-c', 'import greet; print(greet.greet())'],"
        " capture_output=True, text=True, check=True).stdout)",
    ]
    if git:
        inputs.append(
            f"s = subprocess.run([{git!r}, 'status', '--short'], capture_output=True, text=True)\n"
            f"a = subprocess.run([{git!r}, 'add', '-A'], capture_output=True, text=True)\n"
            f"c = subprocess.run([{git!r}, 'commit', '-qm', 'edit'], capture_output=True, text=True)\n"
            f"n = subprocess.run([{git!r}, 'rev-list', '--count', 'HEAD'], capture_output=True, text=True)\n"
            "print(sorted(s.stdout.split()), a.returncode, c.returncode, c.stderr.strip(), n.stdout.strip())"
        )
    patch = _inputs(composition, *inputs, extra=_jailed_in(project))
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert _asked() == []  # confined: no input was asked about
    assert "[0] ['greet.py', 'new.py']" in out, out
    assert "return 'hello'" in out and (project / "greet.py").read_text().endswith("return 'hello'\n")
    assert "[2] hello" in out, out  # a program the input started, in the jail, ran the edited code
    assert (project / "new.py").read_text() == "X = 1\n"
    if git:
        assert "[3] ['??', '??', 'greet.py', 'new.py'] 0 0  1" in out, out  # status, add, commit


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_input_cannot_rewrite_the_composition_or_leave_the_project(
    composition: Callable[..., Path],
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"

    def attempt(path: Path) -> str:
        return (
            f"try:\n    open({str(path)!r}, 'a').write('x'); print('WROTE')\n"
            "except OSError:\n    print('DENIED')"
        )

    (project / ".git" / "hooks").mkdir(parents=True)
    placeholder = tmp_path / "PATCH"
    network = (
        "import socket\ntry:\n    socket.create_connection(('1.1.1.1', 80), timeout=3); print('WROTE')\n"
        "except OSError:\n    print('DENIED')"
    )
    ssh = Path.home() / ".ssh"
    credentials = (
        f"import os\ntry:\n    os.listdir({str(ssh)!r}); print('WROTE')\nexcept OSError:\n    print('DENIED')"
    )
    patch = _inputs(
        composition,
        attempt(project / "ok.txt"),
        attempt(outside),
        attempt(placeholder),
        attempt(project / ".git" / "hooks" / "pre-commit"),
        network,
        credentials if ssh.is_dir() else "print('DENIED')",
        extra=_jailed_in(project),
    )
    patch.write_text(patch.read_text().replace(str(placeholder), str(patch.resolve())))  # the patch itself
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] WROTE" in out, out  # the project is writable
    assert all(f"[{n}] DENIED" in out for n in range(1, 6)), out  # outside, the patch, hooks, network, ~/.ssh
    assert not outside.exists() and not patch.read_text().endswith("x")  # neither was touched
    assert _asked() == []


def _writes(*paths: Path) -> list[str]:
    return [
        f"try:\n    open({str(p)!r}, 'a').write('x'); print('WROTE')\nexcept OSError:\n    print('DENIED')"
        for p in paths
    ]


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_input_may_edit_the_project_s_guidance_but_not_what_runs_code_later(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / ".claude").mkdir()
    inputs = _writes(
        project / "CLAUDE.md",
        project / "AGENTS.md",
        project / ".git" / "config",
        project / ".claude" / "x.json",
    )
    patch = _inputs(composition, *inputs, extra=_jailed_in(project))
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] WROTE" in out and "[1] WROTE" in out, out  # guidance files: `allow`'s default
    assert "[2] DENIED" in out and "[3] DENIED" in out, out  # git config and Claude settings stay denied
    assert (project / "CLAUDE.md").read_text() == "x" and not (project / ".git" / "config").exists()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_the_jail_row_s_allow_lets_an_input_write_one_more_self_modification_path(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    (project / ".git" / "hooks").mkdir(parents=True)
    inputs = _writes(
        project / ".git" / "config", project / ".git" / "hooks" / "pre-commit", project / "CLAUDE.md"
    )
    jail = _jailed_in(project) + 'config = { allow = [".git/config"] }\n'
    patch = _inputs(composition, *inputs, extra=jail)
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] WROTE" in out, out  # the one it allowed
    assert "[1] DENIED" in out, out  # hooks still denied
    assert "[2] DENIED" in out, out  # an `allow` replaces the default: CLAUDE.md is denied again


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_input_cannot_read_the_credential_file_bh_02_names_from_another_directory(
    composition: Callable[..., Path],
    tmp_path: Path,
) -> None:
    """bh-02 runs in a project far from the workspace whose `local.env` holds its credential: a
    input can't open that file, nor have a program it starts read it."""
    project, workspace = tmp_path / "project", tmp_path / "workspace"
    project.mkdir()
    workspace.mkdir()
    secret = workspace / "local.env"
    secret.write_text("NOT_A_REAL_CREDENTIAL=placeholder\n")  # a stand-in: never the real file
    readable = workspace / "notes.txt"
    readable.write_text("fine")

    def attempt(path: Path) -> str:
        return f"try:\n    open({str(path)!r}).read(); print('READ')\nexcept OSError:\n    print('DENIED')"

    patch = _inputs(
        composition,
        attempt(secret),
        attempt(readable),  # darwin: the rest of the filesystem reads, only the secret is hidden
        "import subprocess\n"
        f"r = subprocess.run(['/bin/cat', {str(secret)!r}], capture_output=True, text=True)\n"
        "print('READ' if r.returncode == 0 else 'DENIED')",
        extra=_jailed_in(project),
    )
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})], secrets=[str(secret)])
    out = _shown()
    assert "[0] DENIED" in out and "[2] DENIED" in out, out
    assert f"[1] {'READ' if _READS_EVERYWHERE_ELSE else 'DENIED'}" in out, out  # Linux: not allowlisted
    assert "placeholder" not in out, out


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_kernel_starts_in_a_worktree_and_cannot_write_its_layer_in_the_project(
    composition: Callable[..., Path],
    tmp_path: Path,
) -> None:
    """A git worktree (or submodule): `.git` is a `gitdir:` file, so `.git/hooks` can't exist,
    and on Linux bubblewrap can't make a mount point under a file; the jail denies the file
    itself instead, and the kernel starts. And a layer file inside the project (where
    `--patch mine.toml` usually is) can't be written, though the project can."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").write_text("gitdir: /nowhere\n")
    mine = project / "mine.toml"
    mine.write_text('[[plugin]]\nid = "runner"\nuse = "runner:confined"\n')
    patch = _inputs(
        composition,
        *_writes(project / "ok.txt", mine, project / ".git" / "hooks" / "pre-commit"),
        extra=_jailed_in(project),
    )
    _answers()
    await run([*layers(), patch, mine], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] WROTE" in out and "[1] DENIED" in out and "[2] DENIED" in out, out
    assert mine.read_text().endswith('"runner:confined"\n') and (project / ".git").is_file()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_input_cannot_read_the_project_s_own_local_env_but_reads_beside_it(
    composition: Callable[..., Path],
    tmp_path: Path,
) -> None:
    """The credential inside the project, where an input may write: the one case an allowlist
    alone can't hide, so on Linux it is a mask over the file. Nor can an input overwrite, append
    to, remove or rename over it. A sibling reads in the same run,
    in-process and from a program the input starts; the host's file is untouched; and nothing
    the jail made in the project outlives it."""
    project = tmp_path / "project"
    project.mkdir()
    secret = project / "local.env"
    secret.write_text("NOT_A_REAL_CREDENTIAL=placeholder\n")  # a stand-in: never the real file
    (project / "notes.txt").write_text("fine")

    def attempt(what: str) -> str:
        return f"try:\n    {what}; print('READ')\nexcept OSError:\n    print('DENIED')"

    patch = _inputs(
        composition,
        attempt("open('local.env').read()"),
        attempt("open('notes.txt').read()"),
        "import subprocess\n"
        "r = subprocess.run(['/bin/cat', 'local.env'], capture_output=True, text=True)\n"
        "print('READ' if r.returncode == 0 else 'DENIED')",
        # nor may it replace what it can't read: overwrite, append, remove, rename over
        attempt("open('local.env', 'w').write('X=1')"),
        attempt("open('local.env', 'a').write('X=1')"),
        attempt("__import__('os').remove('local.env')"),
        attempt("open('new.env', 'w').write('X=1'); __import__('os').replace('new.env', 'local.env')"),
        extra=_jailed_in(project),
    )
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] DENIED" in out and "[1] READ" in out and "[2] DENIED" in out, out
    assert all(f"[{n}] DENIED" in out for n in (3, 4, 5, 6)), out
    assert "placeholder" not in out, out
    (project / "new.env").unlink(missing_ok=True)  # the rename's source, left when it is refused
    assert secret.read_text() == "NOT_A_REAL_CREDENTIAL=placeholder\n"
    assert sorted(p.name for p in project.iterdir()) == ["local.env", "notes.txt"]  # nothing left behind


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_input_cannot_plant_a_credential_where_the_model_row_looks(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bh-02 run inside its own workspace: every place the model row looks for `local.env`
    (`credentials`, nearest first) is under the project, where an input may write. An input can't
    create one where there is none (the next launch would hand its token to Claude Code), in
    a directory of its own or one the host imports code from, by writing, by renaming a file of
    its own there, or as a link; nor replace the one that is there. Nothing the jail made on the
    host outlives it, and the model row still finds the real file."""
    project = tmp_path / "project"
    imported = project / "pkg" / "src"  # a directory the host imports code from (editable install)
    imported.mkdir(parents=True)
    monkeypatch.syspath_prepend(str(imported))
    real = project / "local.env"
    real.write_text("NOT_A_REAL_CREDENTIAL=placeholder\n")  # a stand-in: never the real file
    credentials = [str(imported / "local.env"), str(project / "pkg" / "local.env"), str(real)]

    def attempt(what: str) -> str:
        return f"import os\ntry:\n    {what}; print('WROTE')\nexcept OSError:\n    print('DENIED')"

    absent = credentials[:2]
    inputs = [
        *(attempt(f"open({p!r}, 'w').write('X=1')") for p in absent),
        *(attempt(f"open('mine.env', 'w').write('X=1'); os.replace('mine.env', {p!r})") for p in absent),
        *(attempt(f"os.symlink('/tmp/elsewhere.env', {p!r})") for p in absent),
        attempt(f"open({str(real)!r}, 'w').write('X=1')"),
        attempt(f"open('mine.env', 'w').write('X=1'); os.replace('mine.env', {str(real)!r})"),
    ]
    before = sorted(str(p) for p in project.rglob("*"))
    patch = _inputs(composition, *inputs, extra=_jailed_in(project))
    _answers()
    secrets = unreadable(credentials, [], [])
    await run(
        [*layers(), patch], [Row("chat", config={"prompt": "go"})], credentials=credentials, secrets=secrets
    )
    out = _shown()
    assert all(f"[{n}] DENIED" in out for n in range(len(inputs))), out
    (project / "mine.env").unlink(missing_ok=True)  # the renames' source, left when each is refused
    assert sorted(str(p) for p in project.rglob("*")) == before  # no file planted, no placeholder left
    assert real.read_text() == "NOT_A_REAL_CREDENTIAL=placeholder\n"
    assert token_file(None, credentials) == real


@dataclass(frozen=True)
class _Layers:
    paths: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    memory: str = ""


def _python(jail: BrigJail | Runner, config: KernelConfig) -> Kernel:
    """The python tool's process over `jail`, as the python row builds it: started by a runner,
    its inputs confined as the approval rule says of that runner."""
    runner = jail if isinstance(jail, Runner) else Runner(jail)
    return Kernel(runner, config, rule=Approval(runner))


async def test_on_linux_release_frees_where_the_model_row_looks_until_the_next_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/release` (the runner's `release()`, the python row's `stopped` registered with it): the
    jail holding an absent `local.env` where the model row looks ends, and with it the hold, so
    the person can create the file. An input run before they do holds it again (that is all
    `/restart python` would have given them); after they do, the next input's jail masks it: it
    can neither read nor rewrite it."""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the hold is bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    credential = project / "local.env"
    jail = BrigJail(BrigConfig(), _Layers(credentials=(str(credential),), secrets=(str(credential),)))
    reach = (
        "import os\n"
        f"for how in ('r', 'w'):\n"
        "    try:\n"
        f"        open({str(credential)!r}, how)\n"
        "        print(how, 'OPENED')\n"
        "    except OSError as error:\n"
        "        print(how, type(error).__name__)\n"
    )
    runner = Runner(jail)
    async with _python(runner, KernelConfig(root=str(project))) as kernel:
        runner.on_release(kernel.stopped)
        assert credential.is_dir()  # held: the person can't create it
        (record,) = (tmp_path / "state" / "bh-02" / "jails").iterdir()
        group = recorded_group(record.read_text())
        assert group is not None
        said = await runner.release()
        assert said.startswith("The Python process is stopped") and f"Nothing holds {credential}" in said, (
            said
        )
        assert not credential.exists() and runner.released()
        with pytest.raises(ProcessLookupError):
            os.killpg(group, 0)  # the jail is gone, not only its worker
        await kernel.run("1")
        assert credential.is_dir() and not runner.released()  # an input came first: held again
        await runner.release()
        await kernel.__aexit__(None, None, None)  # `/restart python`: stops the jail ...
        await kernel.__aenter__()  # ... and starts one at once, which holds the path again
        assert credential.is_dir()
        await runner.release()
        credential.write_text("CLAUDE_CODE_OAUTH_TOKEN=stand-in-not-a-token\n")  # never a real one
        out = await kernel.run(reach)
        assert "r PermissionError" in out and "w PermissionError" in out, out
        assert str(credential) in kernel.notice()
    assert credential.read_text() == "CLAUDE_CODE_OAUTH_TOKEN=stand-in-not-a-token\n"
    assert token_file(None, [str(credential)]) == credential


# A program that listens and waits, standing in for the extensions' worker: the runner's
# second program, run from a directory of its own.
_LISTENS = """
import socket, sys, time
server = socket.socket(socket.AF_UNIX)
server.bind(sys.argv[1])
server.listen(4)
time.sleep(60)
"""


async def test_on_linux_the_kernel_tells_the_model_its_own_worker_s_trees_when_another_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner starts the Python process and the extensions' worker, and a Linux jail
    reads the directory of the program it runs. What the kernel tells the model is its own
    worker's jail: another program starting on the same jail, from another directory, leaves
    `kernel.instructions()` as it was, so the loop tells the model no change and names no tree
    its inputs can't read."""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the allowlist is bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project, elsewhere = tmp_path / "project", tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    (elsewhere / "worker.py").write_text(_LISTENS)
    jail = BrigJail(BrigConfig(), _Layers())
    sockets = Path(tempfile.mkdtemp(prefix="bh-x-", dir="/tmp"))  # a socket path must be short
    endpoint = str(sockets / "x.sock")
    try:
        async with _python(jail, KernelConfig(root=str(project))) as kernel:
            told = kernel.instructions()
            own = str(Path(worker_argv(endpoint)[2]).parent)  # the kernel's worker's directory
            assert own in kernel.reads() and own in told, kernel.reads()
            argv = [sys.executable, "-I", str(elsewhere / "worker.py"), endpoint]
            other = await jail.start(argv, cwd=str(project), endpoint=endpoint)
            try:
                assert str(elsewhere) not in kernel.reads(), kernel.reads()
                assert kernel.instructions() == told
                assert str(elsewhere) in other.reads()  # the other program's own
            finally:
                await other.stop()
    finally:
        shutil.rmtree(sockets, ignore_errors=True)


async def test_on_linux_release_frees_the_credential_path_while_the_extensions_worker_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model has written an extension, so the runner runs a second program, the extensions'
    worker, whose jail also holds the absent `local.env` where bh-02 looks for its credential
    (and takes the shared jail lock). On `/release` each owner stops its own program (the
    extensions row registers its worker's stop as the python row does), so the path is free and
    nothing claims another session holds it; the runner stays released until the next input
    starts something. (A stand-in program here, stopped by the test as its owner; the real
    extensions' worker under a Linux jail is
    `test_on_linux_the_extensions_worker_imports_cordis_from_an_editable_install`'s.)"""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the hold is bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project, elsewhere = tmp_path / "project", tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    (elsewhere / "worker.py").write_text(_LISTENS)
    credential = project / "local.env"
    jail = BrigJail(BrigConfig(), _Layers(credentials=(str(credential),), secrets=(str(credential),)))
    sockets = Path(tempfile.mkdtemp(prefix="bh-x-", dir="/tmp"))  # a socket path must be short
    endpoint = str(sockets / "x.sock")
    try:
        runner = Runner(jail)
        async with _python(runner, KernelConfig(root=str(project))) as kernel:
            runner.on_release(kernel.stopped)
            argv = [sys.executable, "-I", str(elsewhere / "worker.py"), endpoint]
            extensions = await runner.start(argv, cwd=str(project), endpoint=endpoint)

            async def stop() -> str:
                await extensions.stop()
                return ""

            runner.on_release(stop)
            try:
                records = sorted((tmp_path / "state" / "bh-02" / "jails").iterdir())
                groups = [recorded_group(record.read_text()) for record in records]
                assert len(groups) == 2 and credential.is_dir()
                said = await runner.release()
                assert f"Nothing holds {credential}" in said and "stays held" not in said, said
                assert not credential.exists()
                for group in groups:
                    assert group is not None
                    with pytest.raises(ProcessLookupError):
                        os.killpg(group, 0)  # both jails are gone, the extensions' worker's too
                assert runner.released()
                await kernel.run("1")  # the next input
                assert not runner.released() and credential.is_dir()
            finally:
                await extensions.stop()
    finally:
        shutil.rmtree(sockets, ignore_errors=True)


def _code() -> tuple[str, ...]:
    """The directories bh-02 runs its own code from, as the `bh-02` command finds them
    (`layers.code`): with this editable install, the workspace's `src/<package>` directories."""
    plugins = (ep.module for ep in importlib.metadata.entry_points(group="cordis.plugins"))
    return code_directories(code_packages(plugins))


_HELLO = """
from cordis import Effects, acquire, component

@component
async def hello(*, commands) -> Effects:
    async def run(args: str) -> str:
        return f"hello {args}"

    yield acquire(commands.register, {"name": "hello", "help": "Say hello", "usage": "/hello NAME"}, run)
"""


class _Added:
    """What the extensions add to bh-02, for a test: `commands` (`register`), `frame` (`status`)
    and `system` (`add`) at once; and an `approval` rule that confines, as a jail's does, so the
    `output` is never asked."""

    confined = True

    def __init__(self) -> None:
        self.runs: dict[str, Callable[[str], Awaitable[Any]]] = {}

    def register(self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[Any]]) -> Callable[[], None]:
        self.runs[str(spec["name"])] = run
        return lambda: None

    def status(self, field: str, text: str, *shorter: str) -> Callable[[], None]:
        return lambda: None

    def add(self, section: Callable[[], str]) -> Callable[[], None]:
        return lambda: None

    def unasked(self, request: Mapping[str, Any]) -> bool:
        return True

    async def confirm(self, request: Mapping[str, Any]) -> bool:
        raise AssertionError("a confined load is never put to the person")


async def test_on_linux_the_extensions_worker_imports_cordis_from_an_editable_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Linux jail reads by allowlist, and with an editable install (`uv run` in the checkout,
    `uv tool install --editable`) the environment's `.pth` files name the workspace's `src`
    directories, outside the project and the interpreter: the extensions' worker could not import
    cordis, never listened, and no extension loaded. The jail reads the directories bh-02 runs
    its own code from (`layers.code`, read-only), so the real worker, in a project elsewhere,
    loads the model's extension and what it adds reaches bh-02."""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the allowlist is bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    plugins = project / ".bh-02" / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "hello.py").write_text(_HELLO)
    added = _Added()
    jail = BrigJail(BrigConfig(), _Layers(code=_code()))
    config = ExtensionsConfig(root=str(project), watch=3600)  # entering looks once
    async with Extensions(
        Runner(jail), added, added, added, ToolBroker(), added, added, config
    ) as extensions:
        status = json.loads((plugins / "status.json").read_text())
        assert extensions.statuses["hello"].ok, status
        assert status["hello"]["state"] == "active", status
        assert await added.runs["hello"]("there") == "hello there"


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_input_can_t_write_bh_02_s_own_code_when_the_project_is_its_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bh-02 working on its own checkout (an editable install): the project is the workspace, and
    the directories bh-02 runs its own code from are in it. bh-02 imports their modules in its own
    process (a plugin a layer names later, say), so an input that rewrote one, or wrote a module
    beside one, would choose code bh-02 runs. The jail denies writing every one of them
    (`layers.code`), as it does a layer file: the module stays as it was, and no module of the
    input's lands beside it or beside cordis. So it does when the project is a `src` directory of
    the checkout: the host's `sys.path` names that directory, which, being the project, is not
    denied as a host import path."""
    shipped = Path(memory_cordis_plugin.__file__).with_name("memory.py")
    checkout = next((p for p in shipped.parents if (p / "uv.lock").is_file()), None)
    if checkout is None:
        pytest.skip("bh-02 is not installed editable from its workspace here")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    planted = [
        shipped.with_name("planted_by_an_input.py"),
        Path(cordis.__file__).with_name("planted_by_an_input.py"),
    ]
    before = shipped.read_bytes()
    # brig's self-modification list let through, so the jail makes no placeholder in the checkout
    # (`.envrc/`, ...): what this is about is bh-02's own code alone
    config = BrigConfig(allow=self_modify_denied(()))
    inputs = [
        _append_to(shipped, text=""),  # opened to append, nothing written: the real file stays as it was
        *(_append_to(path, mode="x", text="import os\n") for path in planted),
    ]
    said: dict[Path, list[str]] = {}
    try:
        for root in (checkout, shipped.parent.parent):  # the workspace, then the plugin's `src`
            jail = BrigJail(config, _Layers(code=_code()))
            async with _python(jail, KernelConfig(root=str(root))) as kernel:
                said[root] = [await kernel.run(code) for code in inputs]
    finally:
        for path in planted:
            path.unlink(missing_ok=True)
    for root, answers in said.items():
        assert [a.splitlines()[-1].split()[0] for a in answers] == ["DENIED"] * len(inputs), (root, answers)
    assert shipped.read_bytes() == before


@pytest.mark.usefixtures("_needs_a_jail")
async def test_on_linux_the_person_s_startup_file_runs_in_a_jail_that_has_no_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Linux jail reads by allowlist: the person's config directory is not in it. The host
    reads the person's startup file and sends its source, so its helpers are there all the same;
    the project's is read inside the jail, which can see the project."""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the allowlist is bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    person = Path(os.environ["XDG_CONFIG_HOME"]) / "bh-02" / "kernel.py"  # conftest: outside the project
    person.parent.mkdir(parents=True)
    person.write_text("def show(x):\n    return f'<{x}>'\n")
    project = tmp_path / "project"
    (project / ".bh-02").mkdir(parents=True)
    (project / ".bh-02" / "kernel.py").write_text("TOOLS = 2\n")
    async with _python(BrigJail(BrigConfig(), _Layers()), KernelConfig(root=str(project))) as kernel:
        out = await kernel.run(f"import os\nprint(os.path.exists({str(person)!r}))\nshow(TOOLS)")
    assert out.startswith(
        f"({person} ran first and defined: show. .bh-02/kernel.py ran next and defined: TOOLS)\n"
    ), out
    assert out.endswith("\nFalse\n'<2>'"), out  # the jail can't see the person's file; its helper runs


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_session_run_from_home_can_t_choose_what_a_later_session_reads_as_the_person_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run from the home directory, bh-02's config directory is under a root an input may
    write. A later session elsewhere reads the person's startup file there on the host and hands
    its text to the model, so an input replacing it with a link to a file the jail hides (an SSH
    key) would have the next session hand that file over, in the REPL's linecache and in the
    failing file's traceback. The jail denies the directory (`layers.trusted`, the app's
    `config_directories`: this run's `$XDG_CONFIG_HOME/bh-02` and the default `~/.config/bh-02`),
    as named and as it resolves: no write, link, rename over a file, or moving its parent away."""
    home = tmp_path / "home"
    xdg = home / "xdg" / "bh-02"
    xdg.mkdir(parents=True)
    (home / ".config").mkdir()  # the default directory's parent, without a bh-02 of its own
    person = xdg / "kernel.py"
    person.write_text("HELPER = 1\n")
    key = home / ".ssh" / "id_ed25519"  # a file the jail hides (brig's credential list)
    key.parent.mkdir()
    key.write_text("-----BEGIN STAND-IN KEY, NOT A SECRET-----\nc3RhbmQtaW4K\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "xdg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    trusted = config_directories(os.environ, home)
    assert trusted == (str(xdg), str(home / ".config" / "bh-02"))

    def attempt(what: str) -> str:
        return f"import os\ntry:\n    {what}; print('WROTE')\nexcept OSError:\n    print('DENIED')"

    default = home / ".config" / "bh-02" / "kernel.py"
    inputs = [
        attempt(f"open({str(person)!r}, 'w').write('HELPER = 2')"),
        attempt(f"os.symlink({str(key)!r}, 'planted'); os.replace('planted', {str(person)!r})"),
        attempt(
            f"os.makedirs({str(default.parent)!r}, exist_ok=True); os.symlink({str(key)!r}, {str(default)!r})"
        ),
        attempt(f"open({str(xdg / 'models.toml')!r}, 'w').write('[mine]')"),
        attempt(f"open({str(xdg / 'context.toml')!r}, 'w').write('[[section]]')"),
        attempt(f"os.rename({str(xdg.parent)!r}, 'moved')"),  # then a config directory of its own
        attempt(f"os.rename({str(home / '.config')!r}, 'moved-too')"),
    ]
    jail = BrigJail(BrigConfig(), _Layers(trusted=trusted))
    async with _python(jail, KernelConfig(root=str(home))) as kernel:  # session A, from home
        said = [await kernel.run(code) for code in inputs]
    assert said[0].startswith(f"({person} ran first and defined: HELPER)\n"), said[0]
    assert [s.rsplit("\n", 1)[-1] for s in said] == ["DENIED"] * len(inputs), said
    with contextlib.suppress(FileNotFoundError):
        (home / "planted").unlink()  # the link it made in the home, before the refused rename
    assert person.read_text() == "HELPER = 1\n" and not person.is_symlink()
    assert not default.exists() and not (xdg / "models.toml").exists()
    project = tmp_path / "work" / "project"  # session B, in another project
    project.mkdir(parents=True)
    async with _python(
        BrigJail(BrigConfig(), _Layers(trusted=trusted)), KernelConfig(root=str(project))
    ) as kernel:
        seen = await kernel.run(f"import linecache\n''.join(linecache.getlines({str(person)!r})), HELPER")
    assert seen == f"({person} ran first and defined: HELPER)\n('HELPER = 1\\n', 1)", seen
    assert "STAND-IN" not in seen


def _append_to(path: Path, mode: str = "a", text: str = "# planted by an input\n") -> str:
    """An input that tries to write `path`, and says whether it could."""
    return (
        "try:\n"
        f"    with open({str(path)!r}, {mode!r}) as f:\n"
        f"        f.write({text!r})\n"
        "    print('WROTE')\n"
        "except OSError as error:\n"
        "    print('DENIED', type(error).__name__)\n"
    )


async def _ended(group: int, within: float = 2.0) -> None:
    """Wait until the process group `group` has no process left, or `within` seconds pass."""
    for _ in range(int(within / 0.02)):
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.02)


def _group(state: Path) -> int:
    """The process group of the one running jail recorded under the state directory `state`."""
    (record,) = (state / "bh-02" / "jails").iterdir()
    group = recorded_group(record.read_text())
    assert group is not None
    return group


@pytest.mark.usefixtures("_needs_a_jail")
async def test_on_linux_a_host_rename_over_a_denied_path_ends_the_jail_and_the_next_holds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host `git config` saves `.git/config` by renaming a new file over it, which detaches the
    jail's read-only mount on that path. The jail sees it happen and ends itself, so the next
    input runs in a new jail, which holds the path again, and is told why its variables are gone."""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the mounts are bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    config = project / ".git" / "config"
    jail = BrigJail(BrigConfig(), _Layers())
    async with _python(jail, KernelConfig(root=str(project))) as kernel:
        assert "DENIED" in await kernel.run(_append_to(config))
        group = _group(tmp_path / "state")
        subprocess.run(["git", "config", "user.name", "Pat"], cwd=project, check=True)  # by rename
        await _ended(group)
        out = await kernel.run(_append_to(config))
        assert "DENIED" in out, out  # a new jail holds it again
        assert "started again" in out and str(config) in out, out  # and the input says why
    assert "planted" not in config.read_text() and "Pat" in config.read_text()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_an_input_can_t_put_its_own_git_config_in_place_by_moving_the_directory_it_is_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.git/config` is denied, `.git` is not (a jailed `git commit` writes in it). Renaming
    `.git` away and making a new one would put a config of the input's own (`core.hooksPath`)
    where the person's next host `git` reads it. On Linux the jail pins every directory between
    the project and a denied path (a mount point can't be renamed or removed); darwin's seatbelt
    denies the path whatever directory it ends up in."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    config = project / ".git" / "config"
    was = config.read_text()
    swap = (
        "import os\n"
        "for step in ('rename', 'mkdir', 'write'):\n"
        "    try:\n"
        "        if step == 'rename':\n"
        "            os.rename('.git', '.git-moved')\n"
        "        elif step == 'mkdir':\n"
        "            os.makedirs('.git', exist_ok=True)\n"
        "        else:\n"
        "            open('.git/config', 'a').write('[core]\\n\\thooksPath = /tmp/evil\\n')\n"
        "        print(step, 'DONE')\n"
        "    except OSError as error:\n"
        "        print(step, 'DENIED', type(error).__name__)\n"
    )
    async with _python(BrigJail(BrigConfig(), _Layers()), KernelConfig(root=str(project))) as kernel:
        out = await kernel.run(swap)
    assert "write DENIED" in out, out
    assert "hooksPath" not in config.read_text() if config.exists() else True
    if sys.platform == "linux":
        assert "rename DENIED" in out and config.read_text() == was, out  # .git stays where it is


async def test_on_darwin_a_host_rename_over_a_denied_path_lifts_nothing(tmp_path: Path) -> None:
    """seatbelt matches paths, not directory entries: after a host `git config` renames a new
    `.git/config` into place, the same jail still refuses an input's write, and nothing restarts."""
    if sys.platform != "darwin":
        pytest.skip("seatbelt is darwin's")
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    config = project / ".git" / "config"
    async with _python(BrigJail(BrigConfig(), _Layers()), KernelConfig(root=str(project))) as kernel:
        assert "DENIED" in await kernel.run("x = 1\n" + _append_to(config))
        subprocess.run(["git", "config", "user.name", "Pat"], cwd=project, check=True)
        out = await kernel.run("print(x)\n" + _append_to(config))
        assert "DENIED" in out and "started again" not in out and out.startswith("1"), out
    assert "planted" not in config.read_text()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_on_linux_an_input_running_when_the_host_renames_over_a_denied_path_ends_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The jail ends at once, a running input with it (a program in it could write the path from
    then on), and the input's answer, which the person sees, says what the host did."""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the mounts are bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    config = project / ".git" / "config"
    async with _python(BrigJail(BrigConfig(), _Layers()), KernelConfig(root=str(project))) as kernel:
        running = asyncio.ensure_future(kernel.run("import time\ntime.sleep(5)\nprint('slept')"))
        await asyncio.sleep(1.0)
        subprocess.run(["git", "config", "user.name", "Pat"], cwd=project, check=True)
        out = await asyncio.wait_for(running, 10)
        assert "slept" not in out and "ended during this input" in out and str(config) in out, out
        assert "DENIED" in await kernel.run(_append_to(config))


@pytest.mark.usefixtures("_needs_a_jail")
async def test_on_linux_a_layer_file_saved_by_rename_reloads_and_no_later_input_rewrites_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `--patch` layer inside the project, watched by a real loader. The person saves it the
    way an editor does (a new file renamed over it): the loader applies their change, and the
    jail, whose mount on the file that rename detached, ends; the next input's jail holds the
    new file, so its rewrite is refused and the loader never sees one."""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the mounts are bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    mine = project / "mine.toml"

    def row(name: str) -> str:
        return f'[[plugin]]\nid = "{name}"\nuse = "nowhere:{name}"\ndisabled = true\n'

    mine.write_text(row("one"))
    booted = await boot([mine], watch=0.05)
    try:
        jail = BrigJail(BrigConfig(), _Layers(paths=(str(mine.resolve()),)))
        async with _python(jail, KernelConfig(root=str(project))) as kernel:
            rewrite = _append_to(mine, "w", row("planted"))
            assert "DENIED" in await kernel.run(rewrite)
            group = _group(tmp_path / "state")
            saved = project / "mine.toml.tmp"
            saved.write_text(row("two"))
            saved.replace(mine)  # the person's save
            await _ended(group)
            for _ in range(100):
                if set(booted.loader.rows) == {"two"}:
                    break
                await asyncio.sleep(0.02)
            assert set(booted.loader.rows) == {"two"}  # the person's edit applies
            out = await kernel.run(rewrite)
            assert "DENIED" in out, out
            await asyncio.sleep(0.3)  # the loader looks every 0.05 s
            assert set(booted.loader.rows) == {"two"} and mine.read_text() == row("two")
    finally:
        await booted.runtime.shutdown()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_layer_file_in_a_directory_of_the_project_can_t_be_swapped_by_moving_that_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `--patch` layer at `conf/mine.toml`, watched by a real loader. The person's save by
    rename applies; an input can neither rewrite the file nor rename `conf` away and make a new
    `conf/mine.toml` for the loader to read (on Linux `conf` is pinned; on darwin the jail
    denies the path, whatever directory is there)."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    (project / "conf").mkdir(parents=True)
    mine = project / "conf" / "mine.toml"

    def row(name: str) -> str:
        return f'[[plugin]]\nid = "{name}"\nuse = "nowhere:{name}"\ndisabled = true\n'

    async def until(rows: set[str]) -> set[str]:
        for _ in range(100):
            if set(booted.loader.rows) == rows:
                break
            await asyncio.sleep(0.02)
        return set(booted.loader.rows)

    mine.write_text(row("one"))
    booted = await boot([mine], watch=0.05)
    swap = (
        "import os\n"
        "for step in ('rename', 'mkdir', 'write'):\n"
        "    try:\n"
        "        if step == 'rename':\n"
        "            os.rename('conf', 'conf-moved')\n"
        "        elif step == 'mkdir':\n"
        "            os.makedirs('conf', exist_ok=True)\n"
        "        else:\n"
        f"            open('conf/mine.toml', 'w').write({row('planted')!r})\n"
        "        print(step, 'DONE')\n"
        "    except OSError as error:\n"
        "        print(step, 'DENIED', type(error).__name__)\n"
    )
    try:
        jail = BrigJail(BrigConfig(), _Layers(paths=(str(mine.resolve()),)))
        async with _python(jail, KernelConfig(root=str(project))) as kernel:
            saved = project / "conf" / "mine.toml.tmp"
            saved.write_text(row("two"))
            saved.replace(mine)  # the person's save, by rename
            assert await until({"two"}) == {"two"}  # applies
            out = await kernel.run(swap)
            assert "write DENIED" in out, out
            await asyncio.sleep(0.3)  # the loader looks every 0.05 s
            assert set(booted.loader.rows) == {"two"}, out  # nothing of the input's applied
            if sys.platform == "linux":
                assert "rename DENIED" in out and mine.read_text() == row("two"), out
    finally:
        await booted.runtime.shutdown()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_linux_jailed_git_commit_carries_the_person_s_own_name_without_their_home(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Linux jail has no home directory, so `~/.gitconfig` isn't there; the person's name and
    email (as git resolves them on the host, for the project) reach a jailed `git commit` as
    `GIT_AUTHOR_*`/`GIT_COMMITTER_*`, and nothing else of the person's git config does. darwin's
    jail reads `~/.gitconfig` itself, and is unchanged."""
    git = shutil.which("git")
    if sys.platform != "linux" or git is None:
        pytest.skip("Linux's jail has no home directory; darwin's reads ~/.gitconfig itself")
    person = tmp_path / "person.gitconfig"  # the person's global config, a stand-in
    person.write_text("[user]\n\tname = Pat Person\n\temail = pat@example.invalid\n[alias]\n\tci = commit\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(person))
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run([git, "init", "-q"], cwd=project, check=True)  # no user.name of its own
    (project / "a.txt").write_text("a\n")
    commit = (
        "import subprocess\n"
        f"subprocess.run([{git!r}, 'add', 'a.txt'], check=True)\n"
        f"c = subprocess.run([{git!r}, 'commit', '-qm', 'a'], capture_output=True, text=True)\n"
        f"a = subprocess.run([{git!r}, 'ci', '-m', 'b', '--allow-empty'], capture_output=True, text=True)\n"
        f"who = subprocess.run([{git!r}, 'log', '-1', '--format=%an <%ae> / %cn <%ce>'],"
        " capture_output=True, text=True)\n"
        "print(c.returncode, a.returncode, who.stdout.strip())"
    )
    home = Path.home()
    patch = _inputs(
        composition,
        commit,
        f"import os\nprint(sorted(os.listdir({str(home)!r})) if os.path.isdir({str(home)!r}) else [])",
        extra=_jailed_in(project),
    )
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    # committed as the person; the alias of their config is not there (only the identity is)
    assert "[0] 0 1 Pat Person <pat@example.invalid> / Pat Person <pat@example.invalid>" in out, out
    # the home directory is not there: at most the way to an interpreter installed under it
    on_the_way = {
        Path(p).relative_to(home).parts[0]
        for p in (sys.base_prefix, sys.prefix)
        if Path(p).is_relative_to(home)
    }
    assert f"[1] {sorted(on_the_way)}" in out, out


@pytest.mark.usefixtures("_needs_a_jail")
async def test_the_model_is_told_what_a_linux_jail_reads_and_that_the_home_directory_is_absent(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The project context the model gets: on Linux, the trees the jail reads (the project among
    them) and that nothing else, the home directory included, is there, so it spends no steps
    on reads that can't succeed. darwin's jail reads everything but the secrets: nothing said."""
    import fragile

    project = tmp_path / "project"
    project.mkdir()
    patch = _inputs(composition, "print('hi')", extra=_jailed_in(project))
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    (told,) = fragile.SYSTEM
    if sys.platform == "linux":
        assert "The jail your code runs in reads only" in told, told
        assert str(project.resolve()) in told and "/usr" in told
        assert "home directory" in told and "~/.gitconfig" in told
    else:
        assert "reads only" not in told and "home directory" not in told


def test_the_credential_may_be_above_bh_02_s_install_its_environment_or_the_project() -> None:
    found = credential_files(
        [Path("/w/proj/local.env"), Path("/src/bh/app/bh_02/cli.py"), Path("/src/bh/.venv")]
    )
    assert found[0] == "/w/proj/local.env"  # beside the project
    assert "/src/bh/local.env" in found  # the workspace root, whatever the project
    assert len(found) == len(set(found))  # each once


def test_no_jailed_input_may_read_the_sessions_state_nor_the_credential() -> None:
    searched = credential_files([Path("/src/bh/.venv")])
    beside = [Path("/w/proj/local.env")]
    found = unreadable(searched, beside, ["/xdg/bh-02/sessions", "/home/me/.local/state/bh-02/sessions"])
    assert found[-2:] == ("/xdg/bh-02/sessions", "/home/me/.local/state/bh-02/sessions")
    assert "/src/bh/local.env" in found and "/w/proj/local.env" in found  # searched, and beside
    same = unreadable(searched, beside, ["/home/me/.local/state/bh-02/sessions"] * 2)
    assert same.count("/home/me/.local/state/bh-02/sessions") == 1  # no XDG_STATE_HOME: once
    both = (*searched, *credential_files(beside))
    assert unreadable(searched, beside, [""]) == tuple(dict.fromkeys(both))  # booted without sessions


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_input_cannot_read_under_the_sessions_state_directory(
    composition: Callable[..., Path],
    tmp_path: Path,
) -> None:
    """The sessions' state is a directory in `secrets`: an input can't list it nor open a file
    deep under it (the shape of the Claude Code child's peer-token file), in-process or from a
    program it starts; a sibling directory stays readable."""
    project, state, beside = tmp_path / "project", tmp_path / "state", tmp_path / "beside"
    project.mkdir()
    beside.mkdir()
    token = state / "20260101-000000-abcd" / "claude" / "config" / "sessions" / "1.x.key"
    token.parent.mkdir(parents=True)
    token.write_text('{"peerToken":"placeholder"}')  # a stand-in: never a real token
    (beside / "notes.txt").write_text("fine")

    def attempt(what: str) -> str:
        return f"try:\n    {what}; print('READ')\nexcept OSError:\n    print('DENIED')"

    patch = _inputs(
        composition,
        attempt(f"open({str(token)!r}).read()"),
        attempt(f"__import__('os').listdir({str(state)!r})"),
        attempt(f"open({str(beside / 'notes.txt')!r}).read()"),
        "import subprocess\n"
        f"r = subprocess.run(['/bin/cat', {str(token)!r}], capture_output=True, text=True)\n"
        "print('READ' if r.returncode == 0 else 'DENIED')",
        extra=_jailed_in(project),
    )
    _answers()
    secrets = unreadable([], [], [str(state.resolve())])
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})], secrets=secrets)
    out = _shown()
    assert "[0] DENIED" in out and "[1] DENIED" in out and "[3] DENIED" in out, out
    assert f"[2] {'READ' if _READS_EVERYWHERE_ELSE else 'DENIED'}" in out, out  # Linux: not allowlisted
    assert "placeholder" not in out, out


async def test_the_harness_owned_loop_offers_only_python_and_runs_the_input(
    composition: Callable[..., Path],
) -> None:
    """The shipped loop (agent:loop) with only the model scripted: the loop reads
    the kernel, so it is offered one tool, and the input runs there (asked about: unjailed)."""
    patch = composition(
        '[[plugin]]\nid = "model"\nuse = "fragile:one_input_model"\n',
        one_reply=True,
    )
    _answers(True)
    await run(
        [*layers(), patch],
        [Row("chat", config={"prompt": "go"})],
    )
    assert "offered ['python']; the input said 42" in _shown()
    assert _asked() == ["print(6 * 7)"]


async def test_an_input_that_opens_a_file_is_told_the_guidance_and_rules_for_it_once(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The shipped `notes` and memory rows, booted: the first input that opens a file under src/db
    gets its CLAUDE.md and the rule for it with its result; a later one does not, nor does one
    that reads it through a shell (a shell command's reads are not heard). The on-touch row asks
    the `memory` row, so the project and the home are set there, as a layer would."""
    project, home = tmp_path / "project", tmp_path / "home"
    (project / "src" / "db").mkdir(parents=True)
    (project / ".claude" / "rules").mkdir(parents=True)
    home.mkdir()
    (project / "src" / "db" / "models.py").write_text("X = 1\n")
    (project / "src" / "db" / "CLAUDE.md").write_text("Use the session.")
    (project / ".claude" / "rules" / "db.md").write_text("---\npaths: src/db/**\n---\nMigrations by hand.")
    inputs = (
        "len(open('src/db/models.py').read())",
        "len(open('src/db/models.py').read())",
        "import subprocess; subprocess.run(['cat', 'src/db/models.py'], capture_output=True).returncode",
    )
    patch = _inputs(
        composition,
        *inputs,
        extra=(
            f'[[plugin]]\nid = "python"\nconfig = {{ root = "{project}" }}\n'
            f'[[plugin]]\nid = "system"\nconfig = {{ root = "{project}" }}\n'
            f'[[plugin]]\nid = "memory"\nconfig = {{ root = "{project}", home = "{home}" }}\n'
        ),
    )
    _answers(True, True, True)
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] 6\n\nFrom src/db/CLAUDE.md, instructions for work under src/db/" in out
    assert out.endswith(
        "From .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand.\n[1] 6\n[2] 0\n"
    ), out
    assert out.count("Use the session.") == 1


async def test_a_write_to_a_file_with_untold_instructions_waits_until_they_are_told(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The shipped `access` and memory rows, booted: an input's first write to a file under
    src/db is refused (its CLAUDE.md and rule have not been told), and they follow with its
    result; the next input's write to it goes ahead. A program run through a shell is not asked
    about: what a tool does not hear, it cannot stop."""
    project, home = tmp_path / "project", tmp_path / "home"
    (project / "src" / "db").mkdir(parents=True)
    (project / ".claude" / "rules").mkdir(parents=True)
    home.mkdir()
    models = project / "src" / "db" / "models.py"
    models.write_text("X = 1\n")
    (project / "src" / "db" / "CLAUDE.md").write_text("Use the session.")
    (project / ".claude" / "rules" / "db.md").write_text("---\npaths: src/db/**\n---\nMigrations by hand.")
    inputs = (
        "import pathlib; pathlib.Path('src/db/models.py').write_text('X = 2\\n')",
        "pathlib.Path('src/db/models.py').write_text('X = 3\\n')",
        "import subprocess; subprocess.run(['sh', '-c', 'echo X = 4 > src/db/other.py']).returncode",
    )
    patch = _inputs(
        composition,
        *inputs,
        extra=(
            f'[[plugin]]\nid = "python"\nconfig = {{ root = "{project}" }}\n'
            f'[[plugin]]\nid = "system"\nconfig = {{ root = "{project}" }}\n'
            f'[[plugin]]\nid = "memory"\nconfig = {{ root = "{project}", home = "{home}" }}\n'
        ),
    )
    _answers(True, True, True)
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    refused = out[out.index("[0] ") : out.index("[1] ")]
    assert "PermissionError: [Errno 13] bh-02 refused to let this input write this file" in refused, out
    assert "From src/db/CLAUDE.md, instructions for work under src/db/:\n\nUse the session." in refused
    assert "Migrations by hand." in refused
    assert "[1] 6\n" in out and models.read_text() == "X = 3\n"  # told, so the second write went ahead
    assert "[2] 0" in out and (project / "src" / "db" / "other.py").exists()  # a shell's write: not asked
    assert out.count("Use the session.") == 1


async def test_a_session_whose_branch_switches_keeps_its_prompt_once_and_resumes(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The shipped loop, transcript and project context, booted twice over one transcript file:
    a session, then its resume. Each input that switches the git branch changes the prompt; the
    change is told with that input's result and kept as the edits from the reading before, so
    the file holds the prompt once. The resumed run's requests begin where the session's did,
    and it tells only the switch made since."""
    import fragile

    project, home = tmp_path / "project", tmp_path / "home"
    (project / ".git").mkdir(parents=True)
    home.mkdir()
    (project / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    history = tmp_path / "transcript.jsonl"
    branches = ("one", "two", "three")
    switches = [f"open('.git/HEAD', 'w').write('ref: refs/heads/{branch}\\n')" for branch in branches]
    rows = (
        f'[[plugin]]\nid = "python"\nconfig = {{ root = "{project}" }}\n'
        f'[[plugin]]\nid = "system"\nconfig = {{ root = "{project}" }}\n'
        f'[[plugin]]\nid = "memory"\nconfig = {{ root = "{project}", home = "{home}" }}\n'
        f'[[plugin]]\nid = "transcript"\nconfig = {{ path = "{history}" }}\n'
    )
    # the scripted model runs each input the transcript has no result for: the session runs two,
    # and its resume, scripted with all three, only the third
    for script, run_now in ((switches[:2], switches[:2]), (switches, switches[2:])):
        _answers(True, True, True)
        patch = _inputs(composition, *script, extra=rows)
        await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
        assert _asked() == run_now
    entries = [json.loads(line) for line in history.read_text().splitlines()]
    kept = [entry for entry in entries if entry["role"] == "system"]
    assert "Git branch: main" in kept[0]["content"]
    assert len(kept) == 4 and all(set(entry) == {"role", "edits"} for entry in kept[1:])
    results = [entry["content"] for entry in entries if entry["role"] == "tool"]
    for result, branch in zip(results, branches, strict=True):
        assert f"Git branch: {branch}\n" in result, result  # told with the input that switched it
    opening = json.dumps(kept[0]["content"].split("\n\n")[0])[1:-1]  # who the model is, as the file has it
    assert history.read_text().count(opening) == 1
    assert [kept[0]["content"]] == fragile.SYSTEM  # the resumed run's last request began as the first did


async def test_a_resumed_conversation_is_told_its_notes_once_and_clear_tells_them_afresh(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The shipped `notes` and memory rows over a session's transcript file. The first run's input that
    opens src/db/models.py is told the guidance and the rule for src/db, and its input that reads
    the file through a shell is told nothing (a shell command's reads are not heard); a resumed
    run (the same file, read back: `--resume`) whose inputs do both again is told none of them;
    after /clear (an empty conversation written over the file, the old kept as .bak, and the
    rows started afresh) the same inputs are told them again."""
    project, home = tmp_path / "project", tmp_path / "home"
    (project / "src" / "db").mkdir(parents=True)
    (project / ".claude" / "rules").mkdir(parents=True)
    home.mkdir()
    (project / "src" / "db" / "models.py").write_text("X = 1\n")
    (project / "src" / "db" / "CLAUDE.md").write_text("Use the session.")
    (project / ".claude" / "rules" / "db.md").write_text("---\npaths: src/db/**\n---\nMigrations by hand.")
    history = tmp_path / "transcript.jsonl"
    opens = "len(open('src/db/models.py').read())"
    cats = "import subprocess; subprocess.run(['cat', 'src/db/models.py'], capture_output=True).returncode"
    session = (
        f'[[plugin]]\nid = "python"\nconfig = {{ root = "{project}" }}\n'
        f'[[plugin]]\nid = "system"\nconfig = {{ root = "{project}" }}\n'
        f'[[plugin]]\nid = "memory"\nconfig = {{ root = "{project}", home = "{home}" }}\n'
        f'[[plugin]]\nid = "transcript"\nconfig = {{ path = "{history}" }}\n'
    )
    first = _inputs(composition, opens, cats, extra=session)
    _answers(True, True)
    await run([*layers(), first], [Row("chat", config={"prompt": "go"})])
    told = _shown()
    assert "[0] 6\n\nFrom src/db/CLAUDE.md, instructions for work under src/db/" in told
    assert told.endswith("Migrations by hand.\n[1] 0\n"), told

    import fragile

    fragile.SHOWN.clear()
    code = json.dumps([opens, cats, opens, cats])
    resumed = composition(
        f'[[plugin]]\nid = "model"\nuse = "fragile:input_model"\nconfig = {{ code = {code} }}\n'
        '[[plugin]]\nid = "ui"\nuse = "fragile:scripted_ui"\n' + session
    )
    fragile.script("go", "/clear", "go")
    _answers(*[True] * 6)
    await asyncio.wait_for(run([*layers(), resumed]), 30)
    again, afresh = fragile.SHOWN
    assert again.startswith(told) and again.endswith("\n[2] 6\n[3] 0\n"), again  # resumed: none again
    assert afresh.startswith(told) and afresh.endswith("\n[2] 6\n[3] 0\n"), afresh  # /clear: told afresh
    assert (
        f"the conversation was cleared (the old one is kept as {history}.bak); starting afresh: loop, "
        "transcript, python"
    ) in fragile.NOTES


async def test_a_resumed_session_reads_what_its_inputs_were_told_from_the_notes_on_their_entries(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    """The shipped loop, transcript, `notes` and memory rows, and a layer's own row adding to
    `notes` whose note sorts after memory's, booted twice over one transcript file: a session,
    then its resume. The loop keeps the notes it told with a result on its entry (`notes`), the
    result and the notes still the text the model reads. The resume reads them there, not in the
    text: the rule for src/db, which the other row's note followed, is not told again; the
    CLAUDE.md, cut back since after a paragraph in brackets, is."""
    project, home = tmp_path / "project", tmp_path / "home"
    (project / "src" / "db").mkdir(parents=True)
    (project / ".claude" / "rules").mkdir(parents=True)
    home.mkdir()
    (project / "src" / "db" / "models.py").write_text("X = 1\n")
    guidance = project / "src" / "db" / "CLAUDE.md"
    guidance.write_text("Use the session.\n\n(Never by script.)")
    (project / ".claude" / "rules" / "db.md").write_text("---\npaths: src/db/**\n---\nMigrations by hand.")
    history = tmp_path / "transcript.jsonl"
    opens = "len(open('src/db/models.py').read())"
    session = (
        f'[[plugin]]\nid = "python"\nconfig = {{ root = "{project}" }}\n'
        f'[[plugin]]\nid = "system"\nconfig = {{ root = "{project}" }}\n'
        f'[[plugin]]\nid = "memory"\nconfig = {{ root = "{project}", home = "{home}" }}\n'
        f'[[plugin]]\nid = "transcript"\nconfig = {{ path = "{history}" }}\n'
        '[[plugin]]\nid = "another-note"\nuse = "fragile:another_note"\n'
    )
    guide = "From src/db/CLAUDE.md, instructions for work under src/db/:"
    rule = "From .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand."
    other, trimmed = "Zebra: another row's note.", f"{guide}\n\nUse the session."
    _answers(True)
    await run([*layers(), _inputs(composition, opens, extra=session)], [Row("chat", config={"prompt": "go"})])

    guidance.write_text("Use the session.")  # cut back while no session runs
    _answers(True)  # the resume runs the second input only: the first has its result
    await run(
        [*layers(), _inputs(composition, opens, opens, extra=session)], [Row("chat", config={"prompt": "go"})]
    )
    out = _shown()
    assert out.endswith(f"\n[1] 6\n\n{trimmed}\n\n{other}\n"), out
    first, resumed = [
        entry for line in history.read_text().splitlines() if (entry := json.loads(line))["role"] == "tool"
    ]
    assert first["notes"] == [f"{guide}\n\nUse the session.\n\n(Never by script.)\n\n{rule}", other]
    assert resumed["notes"] == [trimmed, other]
    for entry in (first, resumed):
        assert entry["content"] == "\n\n".join(["6", *entry["notes"]])  # what the model reads, as before
