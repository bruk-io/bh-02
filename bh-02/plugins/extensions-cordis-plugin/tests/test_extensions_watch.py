"""The decisions, as pure functions: names, changes, and what is said."""

import json
import stat

from extensions_cordis_plugin import Status, changes, extension_name, instructions
from extensions_cordis_plugin.watch import linked, refusal, status_file, status_forms


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


def test_bh_02_reads_an_extension_only_from_a_regular_file_with_one_name() -> None:
    """The model writes the directory from the jail and bh-02 reads it on the host: what it
    opened there (following no link) must be the model's own file, or a link could hand the
    model a file the jail hides. Each refusal says what to write instead."""
    file = ".bh-02/plugins/todo.py"
    assert refusal(file, stat.S_IFREG | 0o644, 1) is None
    assert refusal(file, stat.S_IFLNK | 0o777, 1) == (
        ".bh-02/plugins/todo.py is a link, which bh-02 does not follow there (it could lead to a "
        "file the jail hides): write the extension itself at .bh-02/plugins/todo.py, not a link to it"
    )
    assert refusal(file, stat.S_IFREG | 0o644, 3) == (
        ".bh-02/plugins/todo.py has 3 names (a hard link), and bh-02 does not read one there (another "
        "name could be a file the jail hides): write the extension at .bh-02/plugins/todo.py as a "
        "file of its own"
    )
    for other in (stat.S_IFIFO, stat.S_IFDIR, stat.S_IFSOCK):
        assert refusal(file, other | 0o644, 1) == (
            ".bh-02/plugins/todo.py is not a regular file: write the extension at "
            ".bh-02/plugins/todo.py as a file of its own"
        )


def test_a_link_on_the_way_to_the_extensions_is_told_in_the_model_s_prompt() -> None:
    """Nothing is written through such a link, status.json included, so the prompt says it."""
    why = linked(".bh-02/plugins", ".bh-02")
    assert why == (
        ".bh-02 is a link, so bh-02 loads no extension from .bh-02/plugins (a link could lead to "
        "files the jail hides): make .bh-02 a directory in the project, not a link, and write the "
        "extensions in .bh-02/plugins"
    )
    told = instructions(".bh-02/plugins", True, {}, None, why)
    assert told == instructions(".bh-02/plugins", True, {}) + "\n\n" + why


def test_the_model_is_told_how_to_extend_bh_02_and_how_each_extension_is() -> None:
    told = instructions(".bh-02/plugins", True, {})
    assert told.startswith("You can extend bh-02 yourself, while it runs.")
    assert ".bh-02/plugins/NAME.py" in told and "Nobody is asked first" in told
    for offered in ("commands.register(spec, run)", "frame.status(field, text)", "system.add(text)"):
        assert offered in told
    assert "Extensions here" not in told
    unjailed = instructions(".bh-02/plugins", False, {})
    assert "each is shown to the person, who decides whether it loads" in unjailed
    statuses = {
        "todo": Status(rows={"todo.todo": "active"}, commands=("/todo",)),
        "notes": Status(error="Traceback ...\nSyntaxError: '(' was never closed"),
        "slow": Status(loading=True),
    }
    told = instructions(".bh-02/plugins", True, statuses)
    assert told.endswith(
        "Extensions here: notes, slow, todo. How each one is, is in .bh-02/plugins/status.json."
    )
    # names only: an extension loading, failing or coming up leaves the prompt as it was
    assert told == instructions(".bh-02/plugins", True, dict.fromkeys(statuses, Status()))


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
        "tools": [],
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
