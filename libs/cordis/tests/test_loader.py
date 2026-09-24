"""Composition: rows, layers, and the loader that turns them into fibers."""

import asyncio
import importlib.metadata
import sys
from pathlib import Path
from typing import Any

import pytest

from cordis import Effects, Inspection, Row, Runtime, State, background, boot, component
from cordis.composition import Entry, Mount, Unmount, compose, format_layer, parse_layer, plan
from cordis.loader import Disabled, Live, Unresolved, describe, read_layer, resolve

BASE = """
[[plugin]]
id = "subprocess"
use = "git_plugin:subprocess"
config = { reply = "clean\\n" }

[[plugin]]
id = "git"
use = "git_plugin:git"

[[plugin]]
id = "git_tools"
use = "git_plugin:git_tools"
"""


def layer(path: Path, text: str) -> str:
    path.write_text(text)
    return str(path)


# -- composition -------------------------------------------------------------------------


def test_a_patch_replaces_a_rows_whole_config_and_keeps_order() -> None:
    base = [Row("a", "m:a", {"x": 1, "y": 2}), Row("b", "m:b")]
    patch = [Row("b", disabled=True), Row("a", config={"x": 9}), Row("c", "m:c")]
    entries = compose([base, patch])
    assert [e.id for e in entries] == ["a", "b", "c"]
    assert entries[0] == Entry("a", "m:a", {"x": 9})  # replaced whole: y is gone
    assert entries[1].disabled is True
    assert entries[2] == Entry("c", "m:c", {})


def test_a_row_that_inserts_must_say_what_to_mount() -> None:
    with pytest.raises(ValueError, match="no `use`"):
        compose([[Row("a")]])


def test_a_layer_is_rows() -> None:
    rows = parse_layer(BASE)
    assert [r.id for r in rows] == ["subprocess", "git", "git_tools"]
    assert rows[0] == Row("subprocess", "git_plugin:subprocess", {"reply": "clean\n"})
    assert rows[1] == Row("git", "git_plugin:git")  # config and disabled left out stay None
    assert parse_layer("") == []


def test_a_layer_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match=r"here: row 'a' has unknown fields \['name'\]"):
        parse_layer('[[plugin]]\nid = "a"\nuse = "m:a"\nname = "nope"\n', "here")


def test_a_layer_file_is_named_in_its_errors(tmp_path: Path) -> None:
    path = layer(tmp_path / "l.toml", '[[plugin]]\nid = "a"\nuse = "m:a"\nname = "nope"\n')
    with pytest.raises(ValueError, match="l.toml: row 'a'"):
        read_layer(path)


A, B, C = Entry("a", "m:a", {}), Entry("b", "m:b", {}), Entry("c", "m:c", {})


def test_a_plan_leaves_an_unchanged_row_alone() -> None:
    assert plan({"a": A, "b": B}, [A, B]) == ()
    assert plan({}, []) == ()


def test_a_plan_mounts_what_is_new_and_unmounts_what_went() -> None:
    assert plan({"a": A}, [A, C]) == (Mount(C),)
    assert plan({"a": A, "b": B}, [A]) == (Unmount("b", "removed"),)


def test_a_plan_unmounts_a_changed_row_before_mounting_its_replacement() -> None:
    changed = Entry("a", "m:a", {"x": 1})
    assert plan({"a": A}, [changed]) == (Unmount("a", "changed"), Mount(changed))
    assert plan({"a": A}, [Entry("a", "m:a", {}, disabled=True)]) == (
        Unmount("a", "changed"),
        Mount(Entry("a", "m:a", {}, disabled=True)),
    )


def test_every_unmount_precedes_every_mount() -> None:
    """Two changed rows: neither replacement may mount while the other's old row still holds its keys."""
    steps = plan({"a": A, "b": B, "c": C}, [Entry("a", "m:a", {"x": 1}), Entry("b", "m:b", {"y": 2})])
    assert steps == (
        Unmount("c", "removed"),
        Unmount("a", "changed"),
        Unmount("b", "changed"),
        Mount(Entry("a", "m:a", {"x": 1})),
        Mount(Entry("b", "m:b", {"y": 2})),
    )
    kinds = [type(s) for s in steps]
    assert kinds.index(Mount) > max(i for i, k in enumerate(kinds) if k is Unmount)


def test_applying_a_plan_yields_the_rows_wanted() -> None:
    current = {"a": A, "b": B}
    wanted = [Entry("a", "m:a", {"x": 1}), C]
    for step in plan(current, wanted):
        match step:
            case Unmount(id=rid):
                del current[rid]
            case Mount(entry=entry):
                assert entry.id not in current  # never mounted over a live row
                current[entry.id] = entry
    assert current == {e.id: e for e in wanted}


def test_describe_names_each_outcome() -> None:
    assert describe(Disabled(A)) == "disabled"
    assert (
        describe(Unresolved(A, "ImportError: no module named m"))
        == "unresolved: ImportError: no module named m"
    )


async def test_describe_reports_active_work_failed_when_background_work_dies() -> None:
    @component
    async def worker() -> Effects:
        async def boom() -> None:
            raise RuntimeError("bang")

        yield background(boom())

    rt = Runtime()
    f = rt.mount(worker)
    await rt.settle()
    with pytest.raises(RuntimeError, match="bang"):
        await asyncio.wait_for(rt.idle(), 2)
    assert describe(Live(A, f)) == "active, work failed: RuntimeError('bang')"


@component
async def _boom_worker() -> Effects:
    async def boom() -> None:
        raise RuntimeError("bang")

    yield background(boom())


async def test_loader_status_reports_active_work_failed_through_a_real_row() -> None:
    booted = await boot([], overrides=[Row("worker", f"{__name__}:_boom_worker")])
    with pytest.raises(RuntimeError, match="bang"):
        await asyncio.wait_for(booted.runtime.idle(), 2)
    assert booted.loader.status()["worker"] == "active, work failed: RuntimeError('bang')"


def test_resolve_finds_a_component_by_module_and_attribute() -> None:
    assert resolve("cordis.loader:loader").name == "loader"
    with pytest.raises(LookupError, match="no attribute"):
        resolve("cordis.loader:absent")
    with pytest.raises(TypeError, match="is not a component"):
        resolve("cordis.loader:Loader")
    with pytest.raises(ValueError, match="plugin:component"):
        resolve("cordis.loader")


def test_resolve_finds_a_component_by_plugin_entry_point(
    plugin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`plugin:component` scans the package an installed `cordis.plugins` entry point names."""

    class Point:
        name = "vcs"

        def load(self) -> object:
            return plugin

    monkeypatch.setattr(importlib.metadata, "entry_points", lambda group: [Point()])
    assert resolve("vcs:git_tools").name == "git_tools"
    with pytest.raises(LookupError, match="git_tools"):  # lookup lists what the package has
        resolve("vcs:absent")
    with pytest.raises(ModuleNotFoundError) as raised:
        resolve("no_such_plugin:thing")
    assert "installed plugins: vcs" in "".join(raised.value.__notes__)


# -- the loader as a component ---------------------------------------------------------------


async def test_a_composition_boots_and_its_rows_activate(plugin: Any, tmp_path: Path) -> None:
    booted = await boot([layer(tmp_path / "base.toml", BASE)])
    assert booted.loader.status() == {"subprocess": "active", "git": "active", "git_tools": "active"}
    assert await Inspection(booted.runtime).bindings["git_status"].value() == "clean\n"


async def test_reload_swaps_only_the_rows_that_changed(plugin: Any, tmp_path: Path) -> None:
    base = layer(tmp_path / "base.toml", BASE)
    patch = tmp_path / "patch.toml"
    layer(patch, "")
    booted = await boot([base, str(patch)])
    before = {rid: m.fiber.uid for rid, m in booted.loader.rows.items() if isinstance(m, Live)}

    layer(patch, '[[plugin]]\nid = "subprocess"\nconfig = { reply = "dirty\\n" }\n')
    await booted.loader.reload()
    await booted.runtime.settle()

    after = {rid: m.fiber.uid for rid, m in booted.loader.rows.items() if isinstance(m, Live)}
    assert after["subprocess"] != before["subprocess"]  # its config changed
    assert after["git"] == before["git"] and after["git_tools"] == before["git_tools"]
    # the rows were not remounted, but they reloaded against the replaced seam
    assert await Inspection(booted.runtime).bindings["git_status"].value() == "dirty\n"


async def test_a_patch_can_disable_a_row(plugin: Any, tmp_path: Path) -> None:
    base = layer(tmp_path / "base.toml", BASE)
    patch = layer(tmp_path / "patch.toml", '[[plugin]]\nid = "git_tools"\ndisabled = true\n')
    booted = await boot([base, patch])
    assert booted.loader.status()["git_tools"] == "disabled"
    assert booted.loader.status()["git"] == "active"  # its siblings are unaffected
    assert "git_status" not in Inspection(booted.runtime).bindings


async def test_an_override_row_patches_the_composition_from_the_bootstrap(
    plugin: Any, tmp_path: Path
) -> None:
    base = layer(tmp_path / "base.toml", BASE)
    booted = await boot([base], overrides=[Row("subprocess", config={"reply": "from argv\n"})])
    assert await Inspection(booted.runtime).bindings["git_status"].value() == "from argv\n"


async def test_an_unresolvable_row_is_reported_and_its_siblings_run(plugin: Any, tmp_path: Path) -> None:
    base = layer(tmp_path / "base.toml", BASE + '\n[[plugin]]\nid = "x"\nuse = "no.such:thing"\n')
    booted = await boot([base])
    status = booted.loader.status()
    assert status["git"] == "active"
    assert status["x"].startswith("unresolved: ModuleNotFoundError")


async def test_a_row_whose_module_fails_to_import_is_unresolved_not_fatal(
    plugin: Any, tmp_path: Path
) -> None:
    """Importing runs the module: a SyntaxError (or anything else it raises) is that row's
    failure to resolve, reported like a missing module, and never takes the loader down."""
    (tmp_path / "broken_plugin.py").write_text("def component(:\n")
    (tmp_path / "raising_plugin.py").write_text("raise RuntimeError('not today')\n")
    rows = '\n[[plugin]]\nid = "x"\nuse = "broken_plugin:thing"\n'
    rows += '\n[[plugin]]\nid = "y"\nuse = "raising_plugin:thing"\n'
    try:
        booted = await boot([layer(tmp_path / "base.toml", BASE + rows)])
        status = booted.loader.status()
        assert status["git"] == "active"
        assert status["x"].startswith("unresolved: SyntaxError")
        assert status["y"] == "unresolved: RuntimeError: not today"
    finally:
        sys.modules.pop("broken_plugin", None)
        sys.modules.pop("raising_plugin", None)


async def test_boot_reports_a_row_whose_inject_nothing_declares_provides_for(
    plugin: Any, tmp_path: Path
) -> None:
    # "git" is dropped, so nothing declares `provides=("git",)`; subprocess and git_tools still run
    no_git = '\n[[plugin]]\nid = "subprocess"\nuse = "git_plugin:subprocess"\n\n'
    no_git += '[[plugin]]\nid = "git_tools"\nuse = "git_plugin:git_tools"\n'
    base = layer(tmp_path / "base.toml", no_git)
    reports: list[str] = []
    booted = await boot([base], report=reports.append)
    assert reports == ["git_tools needs git; no row provides it"]
    assert booted.loader.status()["subprocess"] == "active"


async def test_unloading_the_loader_unwinds_the_composition(plugin: Any, tmp_path: Path) -> None:
    booted = await boot([layer(tmp_path / "base.toml", BASE)])
    assert len(Inspection(booted.runtime).fibers) == 4  # the loader and its three rows
    await booted.runtime.shutdown()
    assert Inspection(booted.runtime).fibers == []
    assert Inspection(booted.runtime).bindings == {}


async def test_the_loader_reloads_on_its_own_when_a_layer_file_changes(plugin: Any, tmp_path: Path) -> None:
    layer = tmp_path / "base.toml"
    layer.write_text(
        '[[plugin]]\nid = "subprocess"\nuse = "git_plugin:subprocess"\nconfig = { reply = "first\\n" }\n'
        '[[plugin]]\nid = "git"\nuse = "git_plugin:git"\nconfig = { binary = "git" }\n'
        '[[plugin]]\nid = "tools"\nuse = "git_plugin:git_tools"\n'
    )
    reports: list[str] = []
    booted = await boot([layer], watch=0.02, report=reports.append)
    try:
        view = Inspection(booted.runtime)
        assert await view.bindings["git_status"].value() == "first\n"
        git_before = view.fiber("git")

        layer.write_text(layer.read_text().replace("first", "second"))  # only subprocess's config changed
        await _until(lambda: view.fiber("subprocess") is not None and view.fiber("subprocess").uid > 3)
        await booted.runtime.settle()
        assert await view.bindings["git_status"].value() == "second\n"
        assert view.fiber("git") is git_before  # git depends on subprocess: reloaded in place, not remounted
        assert reports == []

        layer.write_text("[[plugin]]\nid = \n")  # a broken edit: reported, and nothing changes
        await _until(lambda: bool(reports))
        assert reports[0].startswith("reload failed: ")
        assert await view.bindings["git_status"].value() == "second\n"
    finally:
        await booted.runtime.shutdown()


async def test_watching_can_be_turned_off(plugin: Any, tmp_path: Path) -> None:
    layer = tmp_path / "base.toml"
    layer.write_text('[[plugin]]\nid = "subprocess"\nuse = "git_plugin:subprocess"\n')
    booted = await boot([layer], watch=None)
    try:
        before = Inspection(booted.runtime).fiber("subprocess")
        layer.write_text(
            '[[plugin]]\nid = "subprocess"\nuse = "git_plugin:subprocess"\nconfig = { reply = "x" }\n'
        )
        await asyncio.sleep(0.1)
        assert Inspection(booted.runtime).fiber("subprocess") is before
    finally:
        await booted.runtime.shutdown()


async def _until(condition: Any, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


async def test_rows_are_named_by_their_id_in_diagnostics(plugin: Any, tmp_path: Path) -> None:
    base = layer(tmp_path / "base.toml", '[[plugin]]\nid = "tools"\nuse = "git_plugin:git_tools"\n')
    booted = await boot([base])  # its dependency is not in this composition
    assert "waiting on: git" in Inspection(booted.runtime).explain("tools")
    assert booted.loader.status()["tools"] == "inactive"


async def test_restart_gives_a_row_a_fresh_fiber_and_its_dependents_reload(
    plugin: Any, tmp_path: Path
) -> None:
    booted = await boot([layer(tmp_path / "base.toml", BASE)], watch=None)
    view = Inspection(booted.runtime)
    git, tools = view.fiber("git"), view.fiber("git_tools")
    await booted.loader.restart("git")
    await booted.runtime.settle()
    assert view.fiber("git") is not git and view.fiber("git").state is State.ACTIVE  # a new fiber
    assert view.fiber("git_tools") is tools and tools.state is State.ACTIVE  # reloaded in place
    assert await view.bindings["git_status"].value() == "clean\n"
    with pytest.raises(LookupError, match="no row 'nope'; the rows are git, git_tools, subprocess"):
        await booted.loader.restart("nope")
    await booted.runtime.shutdown()


async def test_restarting_rows_together_reloads_a_row_depending_on_them_once(
    plugin: Any, tmp_path: Path
) -> None:
    booted = await boot([layer(tmp_path / "base.toml", BASE)], watch=None)
    await booted.runtime.settle()
    view = Inspection(booted.runtime)
    heard: list[str] = []
    booted.runtime.listeners.append(lambda e: heard.append(e.fiber) if e.kind == "active" else None)
    subprocess, git = view.fiber("subprocess"), view.fiber("git")
    await booted.loader.restart("subprocess", "git")  # git_tools depends on git, git on subprocess
    await booted.runtime.settle()
    assert view.fiber("subprocess") is not subprocess and view.fiber("git") is not git
    assert heard.count("git_tools") == 1  # once, not once per restarted row
    assert await view.bindings["git_status"].value() == "clean\n"
    with pytest.raises(LookupError, match="no row 'nope'"):
        await booted.loader.restart("git", "nope")
    assert view.fiber("git").state is State.ACTIVE  # nothing restarted when one is missing
    await booted.runtime.shutdown()


async def test_explain_gives_cordis_s_diagnosis_of_a_row(plugin: Any, tmp_path: Path) -> None:
    rows = BASE + '\n[[plugin]]\nid = "x"\nuse = "no.such:thing"\n'
    rows += '\n[[plugin]]\nid = "off"\nuse = "git_plugin:git"\ndisabled = true\n'
    booted = await boot([layer(tmp_path / "base.toml", rows)], watch=None)
    assert booted.loader.explain("git").startswith("git#") and "binds: git" in booted.loader.explain("git")
    assert booted.loader.explain("x").startswith("x: unresolved: ModuleNotFoundError")
    assert booted.loader.explain("off") == "off: disabled"
    assert booted.loader.explain("nope").startswith("nope: no such row")
    await booted.runtime.shutdown()


async def test_a_row_can_depend_on_the_loader_it_was_mounted_by(tmp_path: Path) -> None:
    """The loader binds its handle after mounting its rows; a row injecting `loader` waits for
    it like any dependency, and boot does not report it as unsatisfiable."""
    (tmp_path / "operator_plugin.py").write_text(
        "from typing import Any\n"
        "from cordis import Effects, bind, component\n\n"
        "@component(provides=('rows_seen',))\n"
        "async def operator(*, loader: Any) -> Effects:\n"
        "    yield bind('rows_seen', sorted(loader.rows))\n"
    )
    sys.path.insert(0, str(tmp_path))
    try:
        reports: list[str] = []
        base = layer(tmp_path / "base.toml", '[[plugin]]\nid = "op"\nuse = "operator_plugin:operator"\n')
        booted = await boot([base], watch=None, report=reports.append)
        await booted.runtime.settle()
        assert reports == []
        assert booted.runtime.root.get("rows_seen") == ["op"]
        await booted.runtime.shutdown()
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("operator_plugin", None)


def test_format_layer_is_parse_layer_s_inverse() -> None:
    rows = [
        Row("llm", "provider:model", {"model": "haiku", "session_file": '/tmp/a "b"/c'}),
        Row("jail", "kernel:unjailed"),
        Row("approve", disabled=True),
        Row("x", "p:c", {"n": 3, "on": False, "names": ["a", "b"], "nested": {"k": 1.5}}),
    ]
    text = format_layer(rows, header="written by a test\nsecond line")
    assert text.startswith("# written by a test\n# second line\n")
    assert parse_layer(text) == rows
    with pytest.raises(TypeError, match="can't hold a object"):
        format_layer([Row("bad", "p:c", {"thing": object()})])


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (
            '[plugin]\nid = "a"\n',
            r"here: 'plugin' is one table \(\[plugin\], single brackets\); write each row",
        ),
        ('plugin = ["a"]\n', r"here: 'plugin' is an array of values"),
        ("plugin = 3\n", r"here: 'plugin' is a number \(3\)"),
        (
            '[[plugin]]\nid = "a"\nconfig = "x"\n',
            r"here: row 'a': 'config' is a string \(\"x\"\); it must be a table",
        ),
        ('[[plugin]]\nid = "a"\nuse = 3\n', r"here: row 'a': 'use' is a number \(3\); it must be a string"),
        ("[[plugin]]\nid = 3\n", r"here: row '\?': 'id' is a number \(3\); it must be a string"),
        ('[[plugin]]\nuse = "x:y"\n', r"here: a \[\[plugin\]\] row \(use = \"x:y\"\) has no 'id'; add id = "),
        ("[[plugin]]\ndisabled = true\n", r"here: a \[\[plugin\]\] row has no 'id'; add id = "),
        (
            '[[plugin]]\nid = "a"\ndisabled = "no"\n',
            r"here: row 'a': 'disabled' is a string \(\"no\"\); it must be true or false",
        ),
    ],
)
def test_a_layer_whose_fields_are_the_wrong_toml_says_what_to_write(text: str, said: str) -> None:
    with pytest.raises(ValueError, match=said):
        parse_layer(text, "here")
