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
