"""The one tool booted from the shipped layers: a real loop, kernel and jail; only the model
is a fake, which calls scripted cells. A cell is plain Python: it reads and writes files and
runs programs itself, the jail decides what it may touch, and unjailed every cell is asked about."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from bh_02.bootstrap import credential_files, layers, run, unreadable
from brig_cordis_plugin import BrigConfig, BrigJail, recorded_group
from cordis import Row
from cordis.loader import boot
from kernel_cordis_plugin import Kernel, KernelConfig
from models_cordis_plugin.local_env import token_file

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


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_jailed_cell_cannot_plant_a_credential_where_the_model_row_looks(
    composition: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bh-02 run inside its own workspace: every place the model row looks for `local.env`
    (`credentials`, nearest first) is under the project, where a cell may write. A cell can't
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
    cells = [
        *(attempt(f"open({p!r}, 'w').write('X=1')") for p in absent),
        *(attempt(f"open('mine.env', 'w').write('X=1'); os.replace('mine.env', {p!r})") for p in absent),
        *(attempt(f"os.symlink('/tmp/elsewhere.env', {p!r})") for p in absent),
        attempt(f"open({str(real)!r}, 'w').write('X=1')"),
        attempt(f"open('mine.env', 'w').write('X=1'); os.replace('mine.env', {str(real)!r})"),
    ]
    before = sorted(str(p) for p in project.rglob("*"))
    patch = _cells(composition, *cells, extra=_jailed_in(project))
    _answers()
    secrets = unreadable(credentials, [], [])
    await run(
        [*layers(), patch], [Row("chat", config={"prompt": "go"})], credentials=credentials, secrets=secrets
    )
    out = _shown()
    assert all(f"[{n}] DENIED" in out for n in range(len(cells))), out
    (project / "mine.env").unlink(missing_ok=True)  # the renames' source, left when each is refused
    assert sorted(str(p) for p in project.rglob("*")) == before  # no file planted, no placeholder left
    assert real.read_text() == "NOT_A_REAL_CREDENTIAL=placeholder\n"
    assert token_file(None, credentials) == real


@dataclass(frozen=True)
class _Layers:
    paths: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()


async def test_on_linux_release_frees_where_the_model_row_looks_until_the_next_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/release` (the kernel's `release()`): the jail holding an absent `local.env` where the
    model row looks ends, and with it the hold, so the person can create the file. A cell run
    before they do holds it again (that is all `/restart kernel` would have given them); after
    they do, the next cell's jail masks it: it can neither read nor rewrite it."""
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
    async with Kernel(jail, KernelConfig(root=str(project))) as kernel:
        assert credential.is_dir()  # held: the person can't create it
        (record,) = (tmp_path / "state" / "bh-02" / "jails").iterdir()
        group = recorded_group(record.read_text())
        assert group is not None
        said = await kernel.release()
        assert f"Nothing holds {credential}" in said, said
        assert not credential.exists()
        with pytest.raises(ProcessLookupError):
            os.killpg(group, 0)  # the jail is gone, not only its worker
        await kernel.run("1")
        assert credential.is_dir()  # a cell came first: held again
        await kernel.release()
        await kernel.__aexit__(None, None, None)  # `/restart kernel`: stops the jail ...
        await kernel.__aenter__()  # ... and starts one at once, which holds the path again
        assert credential.is_dir()
        await kernel.release()
        credential.write_text("CLAUDE_CODE_OAUTH_TOKEN=stand-in-not-a-token\n")  # never a real one
        out = await kernel.run(reach)
        assert "r PermissionError" in out and "w PermissionError" in out, out
        assert str(credential) in kernel.notice()
    assert credential.read_text() == "CLAUDE_CODE_OAUTH_TOKEN=stand-in-not-a-token\n"
    assert token_file(None, [str(credential)]) == credential


def _append_to(path: Path, mode: str = "a", text: str = "# planted by a cell\n") -> str:
    """A cell that tries to write `path`, and says whether it could."""
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
    cell runs in a new jail, which holds the path again, and is told why its variables are gone."""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the mounts are bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    config = project / ".git" / "config"
    jail = BrigJail(BrigConfig(), _Layers())
    async with Kernel(jail, KernelConfig(root=str(project))) as kernel:
        assert "DENIED" in await kernel.run(_append_to(config))
        group = _group(tmp_path / "state")
        subprocess.run(["git", "config", "user.name", "Pat"], cwd=project, check=True)  # by rename
        await _ended(group)
        out = await kernel.run(_append_to(config))
        assert "DENIED" in out, out  # a new jail holds it again
        assert "started again" in out and str(config) in out, out  # and the cell says why
    assert "planted" not in config.read_text() and "Pat" in config.read_text()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_a_cell_can_t_put_its_own_git_config_in_place_by_moving_the_directory_it_is_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.git/config` is denied, `.git` is not (a jailed `git commit` writes in it). Renaming
    `.git` away and making a new one would put a config of the cell's own (`core.hooksPath`)
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
    async with Kernel(BrigJail(BrigConfig(), _Layers()), KernelConfig(root=str(project))) as kernel:
        out = await kernel.run(swap)
    assert "write DENIED" in out, out
    assert "hooksPath" not in config.read_text() if config.exists() else True
    if sys.platform == "linux":
        assert "rename DENIED" in out and config.read_text() == was, out  # .git stays where it is


async def test_on_darwin_a_host_rename_over_a_denied_path_lifts_nothing(tmp_path: Path) -> None:
    """seatbelt matches paths, not directory entries: after a host `git config` renames a new
    `.git/config` into place, the same jail still refuses a cell's write, and nothing restarts."""
    if sys.platform != "darwin":
        pytest.skip("seatbelt is darwin's")
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    config = project / ".git" / "config"
    async with Kernel(BrigJail(BrigConfig(), _Layers()), KernelConfig(root=str(project))) as kernel:
        assert "DENIED" in await kernel.run("x = 1\n" + _append_to(config))
        subprocess.run(["git", "config", "user.name", "Pat"], cwd=project, check=True)
        out = await kernel.run("print(x)\n" + _append_to(config))
        assert "DENIED" in out and "started again" not in out and out.startswith("1"), out
    assert "planted" not in config.read_text()


@pytest.mark.usefixtures("_needs_a_jail")
async def test_on_linux_a_cell_running_when_the_host_renames_over_a_denied_path_ends_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The jail ends at once, a running cell with it (a program in it could write the path from
    then on), and the cell's answer, which the person sees, says what the host did."""
    if sys.platform != "linux" or not Path(_BWRAP).exists():
        pytest.skip("the mounts are bubblewrap's: Linux with /usr/bin/bwrap only")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    config = project / ".git" / "config"
    async with Kernel(BrigJail(BrigConfig(), _Layers()), KernelConfig(root=str(project))) as kernel:
        running = asyncio.ensure_future(kernel.run("import time\ntime.sleep(5)\nprint('slept')"))
        await asyncio.sleep(1.0)
        subprocess.run(["git", "config", "user.name", "Pat"], cwd=project, check=True)
        out = await asyncio.wait_for(running, 10)
        assert "slept" not in out and "ended during this cell" in out and str(config) in out, out
        assert "DENIED" in await kernel.run(_append_to(config))


@pytest.mark.usefixtures("_needs_a_jail")
async def test_on_linux_a_layer_file_saved_by_rename_reloads_and_no_later_cell_rewrites_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `--patch` layer inside the project, watched by a real loader. The person saves it the
    way an editor does (a new file renamed over it): the loader applies their change, and the
    jail, whose mount on the file that rename detached, ends; the next cell's jail holds the
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
        async with Kernel(jail, KernelConfig(root=str(project))) as kernel:
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
    patch = _cells(
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
    patch = _cells(composition, "print('hi')", extra=_jailed_in(project))
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


def test_no_jailed_cell_may_read_the_sessions_state_nor_the_credential() -> None:
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
    secrets = unreadable([], [], [str(state.resolve())])
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
