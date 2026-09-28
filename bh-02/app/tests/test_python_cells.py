"""The one tool booted from the shipped layers: a real loop, kernel and jail; only the model
is a fake, which calls scripted cells. A cell is plain Python: it reads and writes files and
runs programs itself, the jail decides what it may touch, and unjailed every cell is asked about."""

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from bh_02.bootstrap import credential_files, layers, run, unreadable
from cordis import Row

# darwin's jail (seatbelt) reads by denylist: everything but the secrets. Linux's (bubblewrap)
# reads by allowlist: the system, the interpreter and the project, so a file anywhere else is
# absent there, not merely hidden.
_READS_EVERYWHERE_ELSE = sys.platform == "darwin"
_BWRAP = "/usr/bin/bwrap"


@pytest.fixture
def _needs_a_jail() -> None:
    """brig:jail runs on darwin (seatbelt) and on Linux with bubblewrap installed. A fixture,
    not `skipif`: looking for the binary at import time is an import-time side effect."""
    if sys.platform not in ("darwin", "linux"):
        pytest.skip(f"brig:jail runs on darwin and Linux; this is {sys.platform}")
    if sys.platform == "linux" and not Path(_BWRAP).exists():
        pytest.skip(f"brig:jail on Linux needs bubblewrap at {_BWRAP}; install the `bubblewrap` package")


def _shown() -> str:
    import fragile  # the module the fixture wrote, imported by the composition

    return str(fragile.shown())


def _asked() -> list[str]:
    """The code of every cell the person was asked about."""
    import fragile

    return [str(request["input"]["code"]) for request in fragile.ASKED]


def _answers(*these: bool) -> None:
    import fragile

    fragile.answers(*these)


def _cells(composition: Callable[..., Path], *cells: str, extra: str = "") -> Path:
    code = json.dumps(list(cells))
    return composition(
        f'[[plugin]]\nid = "model"\nuse = "fragile:cell_model"\nconfig = {{ code = {code} }}\n' + extra,
        one_reply=True,
    )


def _jailed_in(project: Path) -> str:
    """Layer rows that put the kernel in `project`, inside brig's jail (the fixture's layers
    default to no jail)."""
    return (
        f'[[plugin]]\nid = "kernel"\nconfig = {{ root = "{project}" }}\n'
        '[[plugin]]\nid = "jail"\nuse = "brig:jail"\n'
    )


async def test_unjailed_cells_share_a_namespace_of_plain_python_and_each_is_asked_about(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    (tmp_path / "note.txt").write_text("read with open()")
    cells = (
        "x = 6 * 7",
        "x",
        f"open({str(tmp_path / 'note.txt')!r}).read()",
        "sorted(n for n in globals() if not n.startswith('__'))",
        "undefined_name",
        f"open({str(tmp_path / 'declined.txt')!r}, 'w').write('x')",
    )
    patch = _cells(composition, *cells)
    _answers(True, True, True, True, True, False)
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert _asked() == list(cells)  # every cell, with its code, before it ran
    assert "[1] 42" in out  # the namespace outlived the cell that set it
    assert "[2] 'read with open()'" in out  # a file, read with plain Python
    assert "[3] ['x']" in out  # nothing in the namespace but what cells put there
    assert "[4] Traceback" in out and "NameError" in out
    assert "[5] denied: the person said no to this cell" in out
    assert not (tmp_path / "declined.txt").exists()  # a no ran nothing


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_cell_does_coding_work_in_the_project_without_asking(
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
    cells = [
        "from pathlib import Path\nPath('new.py').write_text('X = 1\\n')\n"
        "print(sorted(p.name for p in Path('.').glob('*.py')))",
        "p = Path('greet.py')\np.write_text(p.read_text().replace(\"'hi'\", \"'hello'\"))\n"
        "print(p.read_text())",
        "import subprocess, sys\n"
        "print(subprocess.run([sys.executable, '-B', '-c', 'import greet; print(greet.greet())'],"
        " capture_output=True, text=True, check=True).stdout)",
    ]
    if git:
        cells.append(
            f"s = subprocess.run([{git!r}, 'status', '--short'], capture_output=True, text=True)\n"
            f"a = subprocess.run([{git!r}, 'add', '-A'], capture_output=True, text=True)\n"
            f"c = subprocess.run([{git!r}, 'commit', '-qm', 'edit'], capture_output=True, text=True)\n"
            f"n = subprocess.run([{git!r}, 'rev-list', '--count', 'HEAD'], capture_output=True, text=True)\n"
            "print(sorted(s.stdout.split()), a.returncode, c.returncode, c.stderr.strip(), n.stdout.strip())"
        )
    patch = _cells(composition, *cells, extra=_jailed_in(project))
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert _asked() == []  # confined: no cell was asked about
    assert "[0] ['greet.py', 'new.py']" in out, out
    assert "return 'hello'" in out and (project / "greet.py").read_text().endswith("return 'hello'\n")
    assert "[2] hello" in out, out  # a program the cell started, in the jail, ran the edited code
    assert (project / "new.py").read_text() == "X = 1\n"
    if git:
        assert "[3] ['??', '??', 'greet.py', 'new.py'] 0 0  1" in out, out  # status, add, commit


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_cell_cannot_rewrite_the_composition_or_leave_the_project(
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
    patch = _cells(
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
async def test_a_jailed_cell_may_edit_the_project_s_guidance_but_not_what_runs_code_later(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / ".claude").mkdir()
    cells = _writes(
        project / "CLAUDE.md",
        project / "AGENTS.md",
        project / ".git" / "config",
        project / ".claude" / "x.json",
    )
    patch = _cells(composition, *cells, extra=_jailed_in(project))
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] WROTE" in out and "[1] WROTE" in out, out  # guidance files: `allow`'s default
    assert "[2] DENIED" in out and "[3] DENIED" in out, out  # git config and Claude settings stay denied
    assert (project / "CLAUDE.md").read_text() == "x" and not (project / ".git" / "config").exists()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_the_jail_row_s_allow_lets_a_cell_write_one_more_self_modification_path(
    composition: Callable[..., Path], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    (project / ".git" / "hooks").mkdir(parents=True)
    cells = _writes(
        project / ".git" / "config", project / ".git" / "hooks" / "pre-commit", project / "CLAUDE.md"
    )
    jail = _jailed_in(project) + 'config = { allow = [".git/config"] }\n'
    patch = _cells(composition, *cells, extra=jail)
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] WROTE" in out, out  # the one it allowed
    assert "[1] DENIED" in out, out  # hooks still denied
    assert "[2] DENIED" in out, out  # an `allow` replaces the default: CLAUDE.md is denied again


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_cell_cannot_read_the_credential_file_bh_02_names_from_another_directory(
    composition: Callable[..., Path],
    tmp_path: Path,
) -> None:
    """bh-02 runs in a project far from the workspace whose `local.env` holds its credential: a
    cell can't open that file, nor have a program it starts read it."""
    project, workspace = tmp_path / "project", tmp_path / "workspace"
    project.mkdir()
    workspace.mkdir()
    secret = workspace / "local.env"
    secret.write_text("NOT_A_REAL_CREDENTIAL=placeholder\n")  # a stand-in: never the real file
    readable = workspace / "notes.txt"
    readable.write_text("fine")

    def attempt(path: Path) -> str:
        return f"try:\n    open({str(path)!r}).read(); print('READ')\nexcept OSError:\n    print('DENIED')"

    patch = _cells(
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
    mine.write_text('[[plugin]]\nid = "jail"\nuse = "brig:jail"\n')
    patch = _cells(
        composition,
        *_writes(project / "ok.txt", mine, project / ".git" / "hooks" / "pre-commit"),
        extra=_jailed_in(project),
    )
    _answers()
    await run([*layers(), patch, mine], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] WROTE" in out and "[1] DENIED" in out and "[2] DENIED" in out, out
    assert mine.read_text().endswith('"brig:jail"\n') and (project / ".git").is_file()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_cell_cannot_read_the_project_s_own_local_env_but_reads_beside_it(
    composition: Callable[..., Path],
    tmp_path: Path,
) -> None:
    """The credential inside the project, where a cell may write: the one case an allowlist
    alone can't hide, so on Linux it is a mask over the file. Nor can a cell overwrite, append
    to, remove or rename over it. A sibling reads in the same run,
    in-process and from a program the cell starts; the host's file is untouched; and nothing
    the jail made in the project outlives it."""
    project = tmp_path / "project"
    project.mkdir()
    secret = project / "local.env"
    secret.write_text("NOT_A_REAL_CREDENTIAL=placeholder\n")  # a stand-in: never the real file
    (project / "notes.txt").write_text("fine")

    def attempt(what: str) -> str:
        return f"try:\n    {what}; print('READ')\nexcept OSError:\n    print('DENIED')"

    patch = _cells(
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


def test_the_credential_may_be_above_bh_02_s_install_its_environment_or_the_project() -> None:
    found = credential_files(
        [Path("/w/proj/local.env"), Path("/src/bh/app/bh_02/cli.py"), Path("/src/bh/.venv")]
    )
    assert found[0] == "/w/proj/local.env"  # beside the project
    assert "/src/bh/local.env" in found  # the workspace root, whatever the project
    assert len(found) == len(set(found))  # each once


def test_no_jailed_cell_may_read_the_sessions_state_nor_the_credential() -> None:
    anchors = [Path("/w/proj/local.env"), Path("/src/bh/.venv")]
    found = unreadable(anchors, ["/xdg/bh-02/sessions", "/home/me/.local/state/bh-02/sessions"])
    assert found[-2:] == ("/xdg/bh-02/sessions", "/home/me/.local/state/bh-02/sessions")
    assert "/src/bh/local.env" in found  # every session's claude/, this run's and the default's
    same = unreadable(anchors, ["/home/me/.local/state/bh-02/sessions"] * 2)
    assert same.count("/home/me/.local/state/bh-02/sessions") == 1  # no XDG_STATE_HOME: once
    assert unreadable(anchors, [""]) == credential_files(anchors)  # booted without sessions


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_cell_cannot_read_under_the_sessions_state_directory(
    composition: Callable[..., Path],
    tmp_path: Path,
) -> None:
    """The sessions' state is a directory in `secrets`: a cell can't list it nor open a file
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

    patch = _cells(
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
    secrets = unreadable([], [str(state.resolve())])
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})], secrets=secrets)
    out = _shown()
    assert "[0] DENIED" in out and "[1] DENIED" in out and "[3] DENIED" in out, out
    assert f"[2] {'READ' if _READS_EVERYWHERE_ELSE else 'DENIED'}" in out, out  # Linux: not allowlisted
    assert "placeholder" not in out, out


async def test_the_harness_owned_loop_offers_only_python_and_runs_the_cell(
    composition: Callable[..., Path],
) -> None:
    """The shipped loop (agent:loop) with only the model scripted: the loop reads
    the kernel, so it is offered one tool, and the cell runs there (asked about: unjailed)."""
    patch = composition(
        '[[plugin]]\nid = "model"\nuse = "fragile:one_cell_model"\n',
        one_reply=True,
    )
    _answers(True)
    await run(
        [*layers(), patch],
        [Row("chat", config={"prompt": "go"})],
    )
    assert "offered ['python']; the cell said 42" in _shown()
    assert _asked() == ["print(6 * 7)"]
