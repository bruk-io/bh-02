import re
from pathlib import Path

_LAB = Path(__file__).resolve().parents[2]


def test_every_entry_point_is_the_last_thing_in_its_module():
    """Code after `if __name__ == "__main__":` is not defined yet when the module runs as a script
    (it broke `./lab needle` once, while imports and tests passed)."""
    late = []
    for path in sorted(_LAB.glob("*/*.py")):
        lines = path.read_text().rstrip().splitlines()
        starts = [i for i, line in enumerate(lines) if line.startswith('if __name__ == "__main__":')]
        if starts and any(line and not line.startswith((" ", "\t")) for line in lines[starts[-1] + 1 :]):
            late.append(str(path.relative_to(_LAB)))
    assert not late, f"move the __main__ block to the end of: {', '.join(late)}"


_IO_IN_A_UNIT_TEST = re.compile(  # matched per line
    r"\b(tmp_path|capsys|capfd|monkeypatch)\b|^import subprocess"
    r"|\.(read_text|write_text|open)\("
    # the registry, directly or through l2's job list (not jq's select, which takes a path)
    r"|from evals\.tasks import|\b(tasks|task)\(|\bselect\((?!\.)"
)


def test_unit_tests_touch_no_files_processes_or_the_task_registry():
    """tests/unit is the pure core's tests; whatever reads or writes files, starts processes, patches
    the environment or builds the registry (it reads real files on this host) is in tests/functional."""
    found = [
        f"{path.name}:{n}: {m[0]}"
        for path in sorted((_LAB / "tests/unit").glob("*.py"))
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if (m := _IO_IN_A_UNIT_TEST.search(line))
    ]
    assert not found, "move these tests to tests/functional: " + "; ".join(found)
