"""The supervisor's program, as text (decision-190, decision-191, TASK-0079.06).

The program can't be imported (it is a string, delivered to an interpreter inside a jail), so the
unit tier holds what can be said about it as data. That it does what it says is
`tests/e2e/test_supervised_jail.py`'s and `tests/integration/test_supervisor_requests.py`'s, in a
real jail; this file holds the promises a reader of its text can check and a change to the text
can break without any jail starting:

- it parses as Python 3.9, the oldest it supports, and the formatter that rewrites a `.py` file to
  the workspace's 3.15 never saw it;
- it imports the standard library and nothing else, and every import is at the top of the
  module: "every import done before any process starts" read off the syntax tree, with a program
  that imports late as the control that the check can fail;
- the protocol it says it speaks is the one the host expects;
- its argv is the interpreter, isolated, and the program's own path.
"""

from __future__ import annotations

import ast
import re
import sys

import pytest

from brig.core.runtime import SUPERVISOR_SOURCE_PATH, SupervisorPlan
from brig.run._supervisor_program import PROTOCOL, SUPERVISOR_SOURCE, supervisor_argv

pytestmark = pytest.mark.unit


def _imports_outside_the_module_body(source: str) -> list[str]:
    """Each import that is not a statement of the module itself, as `module:line`: one in a
    function, a method or a class body, which runs when something calls it, not before."""
    tree = ast.parse(source)
    toplevel = {id(node) for node in tree.body}
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and id(node) not in toplevel:
            names = [alias.name for alias in node.names]
            found.append(f"{getattr(node, 'module', None) or ','.join(names)}:{node.lineno}")
    return found


def _imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def test_the_program_parses_as_the_oldest_python_it_supports() -> None:
    ast.parse(SUPERVISOR_SOURCE, feature_version=(3, 9))
    compile(SUPERVISOR_SOURCE, "<brig-supervisor>", "exec")


def test_every_import_is_a_statement_of_the_module_and_the_standard_library() -> None:
    assert _imports_outside_the_module_body(SUPERVISOR_SOURCE) == []
    modules = _imported_modules(SUPERVISOR_SOURCE)
    assert modules and modules <= set(sys.stdlib_module_names), modules - set(
        sys.stdlib_module_names
    )
    assert "brig" not in modules


def test_a_program_that_imports_late_is_found_by_the_same_check() -> None:
    """The control: the scan finds what it is for. `array` is the real case: newer Pythons'
    `socket.send_fds` imports it inside the function, which is why the program imports it
    itself, first."""
    late = SUPERVISOR_SOURCE.replace(
        "    def op_start(self, rid, message, fds):\n",
        "    def op_start(self, rid, message, fds):\n        import colorsys\n",
        1,
    )
    assert late != SUPERVISOR_SOURCE
    assert [found.split(":")[0] for found in _imports_outside_the_module_body(late)] == ["colorsys"]
    assert re.search(r"^import array\b", SUPERVISOR_SOURCE, re.MULTILINE)


def test_the_protocol_the_program_speaks_is_the_one_the_host_expects() -> None:
    declared = re.search(r"^PROTOCOL = (\d+)$", SUPERVISOR_SOURCE, re.MULTILINE)
    assert declared is not None and int(declared.group(1)) == PROTOCOL


def test_the_argv_is_the_interpreter_isolated_the_program_and_the_control_descriptor() -> None:
    plan = SupervisorPlan("/opt/py/bin/python3")
    assert supervisor_argv(plan, 7) == (
        "/opt/py/bin/python3",
        "-I",
        SUPERVISOR_SOURCE_PATH,
        "7",
    )


def test_a_plan_names_an_absolute_interpreter() -> None:
    with pytest.raises(ValueError, match="absolute path"):
        SupervisorPlan("python3")


def test_the_exit_wrapper_is_told_which_descriptors_its_child_keeps() -> None:
    """decision-191: the supervisor's control socket is a descriptor the exit wrapper and its
    child keep and nothing else does. The argv says which, `-` for none, and never the wrapper's
    own ready pipe or tether."""
    from brig.run._exit_status import wrapper_argv

    none = wrapper_argv("/py", "/exit", 5, ("true",), tether_fd=6)
    kept = wrapper_argv("/py", "/exit", 5, ("true",), tether_fd=6, keep_fds=(9, 11))
    assert none[4:8] == ("/exit", "5", "6", "-")
    assert kept[4:8] == ("/exit", "5", "6", "9,11")
    assert none[8:] == kept[8:] == ("true",)
