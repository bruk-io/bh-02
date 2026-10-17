"""Every Python interpreter brig starts on the host runs isolated (`-I`): SPEC.md section 8,
decision-169 (TASK-0075).

brig's own programs outside the jail run in the workload's working directory, which the
workload can write, and `-c` and `-m` put that directory first on the import path. `-I` takes
it off (with `PYTHON*` variables and the user site), so a module the workload leaves there is
never imported by brig.

**The list is found, not remembered.** `_interpreter_launches` reads brig's source (and the
exit wrapper's, which is a string the launcher hands to `python -c`) for every argv display
whose first element is an interpreter brig resolved itself (`sys.executable`, or the `python`
a mechanism was constructed with) and which runs `-c` or `-m`. A new one fails
`test_every_interpreter_brig_starts_on_the_host_is_listed` until it is added to `_ON_THE_HOST`,
and is then held to `-I` like the rest. A probe's `python3 -c` is the jail's own workload,
resolved inside the jail: a literal first element, so the scan does not count it.

The behaviour tests below call each producer and read the argv it renders, so the claim is
also checked where it is made, not only in its source text. That the flag keeps a planted
module out of a real launch is `tests/integration/test_host_interpreters_isolated.py`'s.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from brig.core import Limits, NetworkPolicy, Spec
from brig.mech import CompileCtx
from brig.mech.connect_proxy import ConnectProxy
from brig.mech.rlimits import rlimits
from brig.run._exit_status import WRAPPER_SOURCE, wrapper_argv

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[2] / "src"

#: The first elements that name an interpreter brig resolved on the host.
_INTERPRETERS = frozenset({"sys.executable", "python"})

#: Every interpreter brig starts on the host, as (module, the function or constant that
#: renders its argv). The exit wrapper, its tether's watcher (inside the wrapper's source),
#: the rlimits trampoline (outermost in every stack, so on the host) and the egress proxy.
_ON_THE_HOST = frozenset(
    {
        ("brig.run._exit_status", "wrapper_argv"),
        ("brig.run._exit_status", "WRAPPER_SOURCE"),
        ("brig.mech.rlimits", "_render_wrap"),
        ("brig.mech.connect_proxy", "_render_helper_argv"),
    }
)


class _Launches(ast.NodeVisitor):
    """Each argv display that starts an interpreter with `-c` or `-m`, named by its enclosing
    top-level function (or `owner` at module level), with whether `-I` comes first."""

    def __init__(self, owner: str) -> None:
        self._owner = [owner]
        self.found: list[tuple[str, bool]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._owner.append(node.name if len(self._owner) == 1 else self._owner[-1])
        self.generic_visit(node)
        self._owner.pop()

    def _display(self, node: ast.List | ast.Tuple) -> None:
        elements = node.elts
        modes = [
            i
            for i, e in enumerate(elements)
            if isinstance(e, ast.Constant) and e.value in ("-c", "-m")
        ]
        if modes and ast.unparse(elements[0]) in _INTERPRETERS:
            first = elements[1]
            isolated = isinstance(first, ast.Constant) and first.value == "-I"
            self.found.append((self._owner[-1], isolated))
        self.generic_visit(node)

    def visit_List(self, node: ast.List) -> None:
        self._display(node)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self._display(node)


def _interpreter_launches() -> dict[tuple[str, str], bool]:
    """(module, owner) -> whether every launch it renders starts with `-I`."""
    sources: list[tuple[str, str, str]] = []
    for path in sorted((_SRC / "brig").rglob("*.py")):
        module = ".".join(path.relative_to(_SRC).with_suffix("").parts).removesuffix(".__init__")
        sources.append((module, "<module>", path.read_text(encoding="utf-8")))
    sources.append(("brig.run._exit_status", "WRAPPER_SOURCE", WRAPPER_SOURCE))
    launches: dict[tuple[str, str], bool] = {}
    for module, owner, source in sources:
        visitor = _Launches(owner)
        visitor.visit(ast.parse(source))
        for name, isolated in visitor.found:
            launches[(module, name)] = launches.get((module, name), True) and isolated
    return launches


def test_every_interpreter_brig_starts_on_the_host_is_listed() -> None:
    """The scan finds exactly the four: a fifth fails here until it is listed (and so held to
    `-I`); one that is gone fails here until it is taken off the list."""
    assert set(_interpreter_launches()) == _ON_THE_HOST


def test_every_interpreter_brig_starts_on_the_host_runs_isolated() -> None:
    not_isolated = sorted(key for key, isolated in _interpreter_launches().items() if not isolated)
    assert not_isolated == [], f"start these with `-I` (SPEC.md decision-169): {not_isolated}"


def test_the_scan_sees_a_launch_without_the_flag_and_one_with_it() -> None:
    """THE CONTROL: the scan is not blind. The same visitor, over two planted displays, tells
    `-I` from its absence, and passes over a shell's `-c` and a jailed `python3 -c`."""
    visitor = _Launches("<module>")
    visitor.visit(
        ast.parse(
            "def bare(python):\n    return (python, '-m', 'x')\n"
            "def isolated():\n    return [sys.executable, '-I', '-c', 'pass']\n"
            "def shell():\n    return ('/bin/sh', '-c', 'true')\n"
            "def probe():\n    return ('python3', '-c', 'pass')\n"
        )
    )
    assert visitor.found == [("bare", False), ("isolated", True)]


def test_the_exit_wrapper_and_its_tether_s_watcher_run_isolated() -> None:
    argv = wrapper_argv("/usr/bin/python3", "/tmp/j", 5, ("true",), tether_fd=6)
    assert argv[:3] == ("/usr/bin/python3", "-I", "-c")
    assert '[sys.executable, "-I", "-c", TETHER, str(tether_fd)]' in WRAPPER_SOURCE


def test_the_rlimits_trampoline_runs_isolated() -> None:
    ctx = CompileCtx(jail_dir="/tmp/j", platform=sys.platform)
    wrapped = rlimits.compile(Spec(limits=Limits(cpu_seconds=5)), ctx).wrap(("true",))
    assert wrapped[:4] == (sys.executable, "-I", "-m", "brig.trampoline")


def test_the_egress_proxy_runs_isolated() -> None:
    ctx = CompileCtx(jail_dir=os.path.realpath("/tmp"), platform=sys.platform)
    spec = Spec(network=NetworkPolicy(allowed_domains=("example.com",)))
    (helper,) = ConnectProxy("/usr/bin/python3").compile(spec, ctx).helpers
    assert helper.argv[:4] == ("/usr/bin/python3", "-I", "-m", "brig.proxy")
