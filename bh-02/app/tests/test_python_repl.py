"""The one tool booted from the shipped layers: a real loop, kernel and jail; only the model
is a fake, which calls scripted inputs. An input is plain Python: it reads and writes files and
runs programs itself, the jail decides what it may touch, and unjailed every input is asked about."""

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from bh_02.bootstrap import credential_files, layers, run, unreadable
from cordis import Row

_JAILED = sys.platform == "darwin"  # brig:jail uses seatbelt, darwin only here


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
        f'[[plugin]]\nid = "kernel"\nconfig = {{ root = "{project}" }}\n'
        '[[plugin]]\nid = "jail"\nuse = "brig:jail"\n'
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
    assert "[5] denied: the person said no to this input" in out
    assert not (tmp_path / "declined.txt").exists()  # a no ran nothing


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
    assert "[0] denied: the person said no to this input" in _shown()
    status = json.loads((plugins / "status.json").read_text())
    assert status["todo"]["error"] == "the person declined to load it"


@pytest.mark.skipif(not _JAILED, reason="brig:jail uses seatbelt, darwin only here")
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


@pytest.mark.skipif(not _JAILED, reason="brig:jail uses seatbelt, darwin only here")
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


@pytest.mark.skipif(not _JAILED, reason="brig:jail uses seatbelt, darwin only here")
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


@pytest.mark.skipif(not _JAILED, reason="brig:jail uses seatbelt, darwin only here")
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


@pytest.mark.skipif(not _JAILED, reason="brig:jail uses seatbelt, darwin only here")
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
        attempt(readable),  # the jail reads the rest of the filesystem: only the secret is hidden
        "import subprocess\n"
        f"r = subprocess.run(['/bin/cat', {str(secret)!r}], capture_output=True, text=True)\n"
        "print('READ' if r.returncode == 0 else 'DENIED')",
        extra=_jailed_in(project),
    )
    _answers()
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})], secrets=[str(secret)])
    out = _shown()
    assert "[0] DENIED" in out and "[1] READ" in out and "[2] DENIED" in out, out
    assert "placeholder" not in out, out


def test_the_credential_may_be_above_bh_02_s_install_its_environment_or_the_project() -> None:
    found = credential_files(
        [Path("/w/proj/local.env"), Path("/src/bh/app/bh_02/cli.py"), Path("/src/bh/.venv")]
    )
    assert found[0] == "/w/proj/local.env"  # beside the project
    assert "/src/bh/local.env" in found  # the workspace root, whatever the project
    assert len(found) == len(set(found))  # each once


def test_no_jailed_input_may_read_the_sessions_state_nor_the_credential() -> None:
    anchors = [Path("/w/proj/local.env"), Path("/src/bh/.venv")]
    found = unreadable(anchors, ["/xdg/bh-02/sessions", "/home/me/.local/state/bh-02/sessions"])
    assert found[-2:] == ("/xdg/bh-02/sessions", "/home/me/.local/state/bh-02/sessions")
    assert "/src/bh/local.env" in found  # every session's claude/, this run's and the default's
    same = unreadable(anchors, ["/home/me/.local/state/bh-02/sessions"] * 2)
    assert same.count("/home/me/.local/state/bh-02/sessions") == 1  # no XDG_STATE_HOME: once
    assert unreadable(anchors, [""]) == credential_files(anchors)  # booted without sessions


@pytest.mark.skipif(not _JAILED, reason="brig:jail uses seatbelt, darwin only here")
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
    secrets = unreadable([], [str(state.resolve())])
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})], secrets=secrets)
    out = _shown()
    assert "[0] DENIED" in out and "[1] DENIED" in out and "[2] READ" in out and "[3] DENIED" in out, out
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
    """The shipped `memory` rows, booted: the first input that opens a file under src/db gets its
    CLAUDE.md and the rule for it with its result; a later one does not; one that reads through
    a shell is told how Python does that."""
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
            f'[[plugin]]\nid = "kernel"\nconfig = {{ root = "{project}" }}\n'
            f'[[plugin]]\nid = "on-touch"\nconfig = {{ root = "{project}", home = "{home}" }}\n'
        ),
    )
    _answers(True, True, True)
    await run([*layers(), patch], [Row("chat", config={"prompt": "go"})])
    out = _shown()
    assert "[0] 6\n\nFrom src/db/CLAUDE.md, guidance for work under src/db/" in out
    assert "From .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand.\n[1] 6\n[2] 0\n\n" in out
    assert out.count("Use the session.") == 1
    assert "[2] 0\n\n(this input ran `cat` through a shell." in out
