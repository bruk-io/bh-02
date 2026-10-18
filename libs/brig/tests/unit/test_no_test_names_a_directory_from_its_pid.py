"""No test names a directory from the process id.

A path made from `os.getpid()` is handed to a later process with the same pid: a pid space of
32768 wraps within a day of test runs, and nothing removed what the earlier process left in it.
The jail then starts over its files (a `proxy.port`, a `procs/` record), and `Jail.create` meets a
directory that is not empty. Measured on `test_connect_proxy_launch.py` under 8-way load before
TASK-0140 gave it a fresh directory: 3 of 160 runs failed on a reused directory, two with
`JailDirInUse` and one with `ConnectionRefusedError` (TASK-0151 moved every integration and e2e
file the same way). A test takes `jail_dir`, or `new_jail_dir` for several, from
`tests/conftest.py`: `tempfile.mkdtemp` makes a directory that did not exist, and the fixture
removes it after the test.

This replaces `test_jail_dir_infixes_are_unique.py`, which pinned the old naming
(`/tmp/bg{os.getpid()}<infix><counter>`, one infix per file, so no two files' counters made the
same path in one pytest process). With no pid in the name there is nothing for an infix to keep
apart.

WHAT IS FLAGGED, on the syntax tree of every `.py` under `tests/` (so a docstring or a comment
that names the old shape is not a finding, and a reformatting does not hide one):

- an f-string with `os.getpid()` (or a bare `getpid()`) in a replacement field and a `/` in its
  literal text -- the old shape, `f"/tmp/bg{os.getpid()}rh{n}"`;
- a `%` or `+` whose string operand has a `/`, or a `/` on paths, or a `"...".format(...)` whose
  string has a `/`, with `getpid()` in the other operand or the arguments;
- a call that builds or makes a path (`os.path.join`, `os.makedirs`, `os.mkdir`, `Path`,
  `tempfile.mkdtemp`, ...) with `getpid()` anywhere in its arguments.

WHAT IS NOT, said so that the claim is no bigger than the check: a pid reaching a path through a
name (`pid = os.getpid()` then `f"/tmp/bg{pid}"`; `harness_pid`, which `conftest.py` puts in the
name of the spawn registry's file) is not followed, and a pid in a message or a file's contents
(`print(f"pid={os.getpid()}")`) is not a path. Pure: reads source text only.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_TESTS_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Calls that build or make a path, by the last name in the call (`os.path.join` is `join`).
_PATH_CALLS = frozenset(
    {"join", "makedirs", "mkdir", "Path", "PurePath", "realpath", "abspath", "mkdtemp", "mkstemp"}
)


def _is_getpid(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Attribute) and func.attr == "getpid") or (
        isinstance(func, ast.Name) and func.id == "getpid"
    )


def _has_getpid(node: ast.AST) -> bool:
    return any(_is_getpid(child) for child in ast.walk(node))


def _has_slash(node: ast.AST) -> bool:
    """A string literal under `node` with a path separator in it."""
    return any(
        isinstance(child, ast.Constant) and isinstance(child.value, str) and "/" in child.value
        for child in ast.walk(node)
    )


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def pid_named_paths(source: str) -> list[int]:
    """The line of every expression in `source` that puts `os.getpid()` into a path, ascending."""
    lines: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.JoinedStr():
                fields = [part for part in node.values if isinstance(part, ast.FormattedValue)]
                literal = [part for part in node.values if isinstance(part, ast.Constant)]
                if any(_has_getpid(field) for field in fields) and any(
                    isinstance(part.value, str) and "/" in part.value for part in literal
                ):
                    lines.add(node.lineno)
            case ast.BinOp(op=ast.Div()):
                if _has_getpid(node):
                    lines.add(node.lineno)
            case ast.BinOp(op=ast.Mod() | ast.Add()):
                if _has_getpid(node) and _has_slash(node):
                    lines.add(node.lineno)
            case ast.Call():
                name = _call_name(node)
                if (
                    name in _PATH_CALLS
                    and any(
                        _has_getpid(arg) for arg in [*node.args, *(k.value for k in node.keywords)]
                    )
                    or (
                        name == "format"
                        and isinstance(node.func, ast.Attribute)
                        and _has_slash(node.func.value)
                        and any(
                            _has_getpid(arg)
                            for arg in [*node.args, *(k.value for k in node.keywords)]
                        )
                    )
                ):
                    lines.add(node.lineno)
    return sorted(lines)


def _test_files() -> list[pathlib.Path]:
    return sorted(path for path in _TESTS_ROOT.rglob("*.py") if "__pycache__" not in path.parts)


@pytest.mark.unit
def test_no_test_names_a_directory_from_the_process_id() -> None:
    files = _test_files()
    # The claim is about the integration and e2e files above all; a scan that found none of them
    # (a moved directory) would pass on nothing.
    scanned = {path.parent.name for path in files}
    assert {"unit", "integration", "e2e"} <= scanned, sorted(scanned)

    found = {
        str(path.relative_to(_TESTS_ROOT)): lines
        for path in files
        if (lines := pid_named_paths(path.read_text(encoding="utf-8")))
    }
    assert not found, (
        "a test names a path from os.getpid(), which a later process with the same pid is handed "
        "along with everything the earlier one left in it; take `jail_dir` (or `new_jail_dir`, "
        "for several) from tests/conftest.py instead: "
        + "; ".join(f"{name}: line {', '.join(map(str, lines))}" for name, lines in found.items())
    )


#: Each shape a pid-named path takes, as source. The first is the exact one the 43 files used.
_PLANTED = {
    "the old f-string": 'import os\nroot = f"/tmp/bg{os.getpid()}rh{next(counter)}"\n',
    "a bare getpid": 'from os import getpid\nroot = f"/tmp/bg{getpid()}"\n',
    "a directory beside a root": 'import os\nroot = f"{base}/bg{os.getpid()}"\n',
    "a % format": 'import os\nroot = "/tmp/bg%d" % os.getpid()\n',
    "a concatenation": 'import os\nroot = "/tmp/bg" + str(os.getpid())\n',
    "str.format": 'import os\nroot = "/tmp/bg{}".format(os.getpid())\n',
    "a join": 'import os\nroot = os.path.join("/tmp", f"bg{os.getpid()}")\n',
    "pathlib": 'import os\nfrom pathlib import Path\nroot = Path("/tmp") / f"bg{os.getpid()}"\n',
    "makedirs": 'import os\nos.makedirs(f"bg{os.getpid()}", exist_ok=True)\n',
    "mkdtemp": 'import os, tempfile\nroot = tempfile.mkdtemp(prefix=f"bg{os.getpid()}-")\n',
}

#: What a test may do with its pid: say it, compare it, send a signal to it.
_NOT_A_PATH = {
    "a message": 'import os\nprint(f"CLAIM: test pid={os.getpid()} helper pid={helper}")\n',
    "a comparison": "import os\nassert helper_pid != os.getpid()\n",
    "arithmetic": "import os\nfar = os.getpid() + 100000\n",
    "bytes": 'import os\nsock.sendall(b"hello from " + str(os.getpid()).encode())\n',
    "a name in /dev": 'import os\nprobe = f"brig-dev-probe-{os.getpid()}"\n',
    "a docstring": 'def f():\n    """names /tmp/bg{os.getpid()}rh the way the old files did"""\n',
    "a template": 'import os\nT = "import os; os.getpid()"\n',
}


@pytest.mark.unit
@pytest.mark.parametrize("source", _PLANTED.values(), ids=_PLANTED.keys())
def test_the_scan_sees_each_shape_a_pid_named_path_takes(source: str) -> None:
    assert pid_named_paths(source), source


@pytest.mark.unit
@pytest.mark.parametrize("source", _NOT_A_PATH.values(), ids=_NOT_A_PATH.keys())
def test_the_scan_leaves_alone_a_pid_that_is_not_in_a_path(source: str) -> None:
    assert pid_named_paths(source) == [], source
