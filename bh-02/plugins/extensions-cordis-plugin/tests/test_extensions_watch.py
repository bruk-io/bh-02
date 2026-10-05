"""The decisions, as pure functions: names, changes, confinement, and what is said."""

import json

from extensions_cordis_plugin import Status, changes, extension_name, instructions, is_confined
from extensions_cordis_plugin.watch import status_file, status_forms


def test_an_extension_is_a_lowercase_python_module() -> None:
    assert extension_name("todo.py") == "todo" and extension_name("run_tests2.py") == "run_tests2"
    assert [extension_name(f) for f in ("Todo.py", "_x.py", "todo.txt", "status.json", "a-b.py", ".py")] == [
        None
    ] * 6


def test_what_to_load_is_what_is_new_or_changed_and_what_to_unload_is_what_is_gone() -> None:
    before = {"a": (1, 10), "b": (1, 10), "c": (1, 10)}
    after = {"a": (1, 10), "b": (2, 11), "d": (1, 3)}
    assert changes(before, after) == (("b", "d"), ("c",))
    assert changes(after, after) == ((), ())


def test_extensions_load_without_asking_exactly_when_cells_run_without_asking() -> None:
    assert is_confined({"fs_write": "enforced", "network": "enforced", "fs_read": "best_effort"})
    assert not is_confined({"fs_write": "enforced", "network": "unenforced"})
    assert not is_confined({})


def test_the_model_is_told_how_to_extend_bh_02_and_how_each_extension_is() -> None:
    told = instructions(".bh-02/plugins", True, {})
    assert told.startswith("You can extend bh-02 yourself, while it runs.")
    assert ".bh-02/plugins/NAME.py" in told and "Nobody is asked first" in told
    for offered in ("commands.register(spec, run)", "frame.status(field, text)", "system.add(text)"):
        assert offered in told
    assert "Extensions now" not in told
    unjailed = instructions(".bh-02/plugins", False, {})
    assert "each is shown to the person, who decides whether it loads" in unjailed
    statuses = {
        "todo": Status(rows={"todo.todo": "active"}, commands=("/todo",)),
        "notes": Status(error="Traceback ...\nSyntaxError: '(' was never closed"),
        "half": Status(rows={"half.a": "active", "half.b": "waiting on: x"}),
        "slow": Status(loading=True),
    }
    lines = instructions(".bh-02/plugins", True, statuses).split("Extensions now:\n")[1].splitlines()
    assert lines == [
        "- half: loaded, but not all of it is up; .bh-02/plugins/status.json has why",
        "- notes: not loaded (SyntaxError: '(' was never closed); .bh-02/plugins/status.json has why",
        "- slow: loading",
        "- todo: active (/todo)",
    ]


def test_the_status_bar_and_the_status_file_say_how_each_one_is() -> None:
    assert status_forms({}) == ()
    statuses = {"todo": Status(rows={"todo.todo": "active"}), "notes": Status(error="boom")}
    assert status_forms(statuses) == ("ext: notes ✗ todo ✓", "ext: 2, 1 ✗")
    written = json.loads(json.dumps(status_file(statuses)))
    assert written["notes"] == {
        "state": "failed",
        "rows": {},
        "error": "boom",
        "commands": [],
        "problems": [],
    }
    assert written["todo"]["state"] == "active"
    refused = Status(rows={"x.x": "active"}, problems=("/model was not added: taken",))
    assert not refused.ok and status_file({"x": refused})["x"]["state"] == "partly up"


def test_the_model_is_told_the_part_of_cordis_an_extension_uses_and_how_to_try_one() -> None:
    told = instructions(".bh-02/plugins", True, {}, "/src/libs/cordis/README.md")
    assert "It runs only while every key it needs is bound" in told
    for effect in ("`acquire(fn, *args)`", "`bind(key, value)`", "`enter(cm)`", "`background(coro)`"):
        assert effect in told
    assert "asyncio.run(cordis.testing.drive(todo(commands=fake, system=fake)))" in told
    assert "cordis's design in full is /src/libs/cordis/README.md" in told
    assert "design in full" not in instructions(".bh-02/plugins", True, {})  # nothing to point at
