"""The on-touch row: what the context files' `on_touch` sections say about the files an input
opened, told with its result, each once a conversation."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from context_cordis_plugin import ContextConfig, OnTouch, on_touch, parse
from cordis.testing import drive
from cordis_helpers import Hooks

_OWN = "context_cordis_plugin.sections:"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _project(tmp_path: Path) -> tuple[OnTouch, Path, Path]:
    home, root = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    root.mkdir()
    return OnTouch(ContextConfig(root=str(root), home=str(home))), root.resolve(), home


def test_a_file_opened_brings_the_guidance_and_rules_for_it_once(tmp_path: Path) -> None:
    told, root, _ = _project(tmp_path)
    _write(root / "AGENTS.md", "Root guidance.")
    _write(root / "src/db/CLAUDE.md", "Use the session.")
    rule = _write(root / ".claude/rules/db.md", "---\npaths: src/db/**\n---\nMigrations by hand.")
    _write(root / ".claude/rules/web.md", "---\npaths: web/**\n---\nWeb.")
    first = told({"code": "...", "result": "...", "touched": (str(root / "src/db/models.py"),)})
    assert first == (
        "From src/db/CLAUDE.md, guidance for work under src/db/, where it wins over the guidance "
        "before it:\n\nUse the session.\n\n"
        "From .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand."
    )
    assert told({"touched": (str(root / "src/db/other.py"),)}) == ""  # told once
    assert told({"touched": ()}) == "" and told({"touched": (str(root / "README.md"),)}) == ""
    rule.write_text("---\npaths: src/db/**\n---\nMigrations by script.")
    assert told({"touched": (str(root / "src/db/x.py"),)}).endswith("Migrations by script.")  # changed


def test_the_project_s_file_may_add_an_on_touch_of_bh_02_s_own_only(tmp_path: Path) -> None:
    sections, _ = parse(
        '[[section]]\nfiles = ["docs/*.md"]\non_touch = "context_cordis_plugin.sections:place_touched"\n',
        ".bh-02/context.toml",
        trusted=False,
    )
    assert (sections[0].function, sections[0].on_touch) == (
        "",
        "context_cordis_plugin.sections:place_touched",
    )
    with pytest.raises(ValueError, match="may name only bh-02's own functions"):
        parse('[[section]]\nfiles = ["x"]\non_touch = "os:system"\n', ".bh-02/context.toml", trusted=False)
    with pytest.raises(ValueError, match="and may have `on_touch`"):
        parse('[[section]]\nfiles = ["x"]\n', "mine.toml", trusted=True)  # neither function


def test_an_on_touch_of_yours_that_fails_says_so_once(tmp_path: Path) -> None:
    told, root, home = _project(tmp_path)
    _write(
        home / ".config/bh-02/context.toml",
        'replace = true\n[[section]]\nfiles = ["x.md"]\non_touch = "context_cordis_plugin.sections:nope"\n',
    )
    said = told({"touched": (str(root / "a.py"),)})
    assert said.startswith("(bh-02 could not make the section context_cordis_plugin.sections:nope:")
    assert told({"touched": (str(root / "a.py"),)}) == ""


def test_the_on_touch_row_reads_your_file_where_the_prompt_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It has `context:project`'s config, so the same files: yours in `$XDG_CONFIG_HOME` when that
    is set, and then not ~/.config's."""
    told, root, home = _project(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    for where, name in ((tmp_path / "xdg", "from_xdg"), (home / ".config", "from_dot_config")):
        _write(
            where / "bh-02/context.toml",
            f'replace = true\n[[section]]\nfiles = ["x.md"]\non_touch = "{_OWN}{name}"\n',
        )
    said = told({"touched": (str(root / "a.py"),)})
    assert f"{_OWN}from_xdg" in said and "from_dot_config" not in said


async def test_the_row_adds_its_function_to_memory() -> None:
    memory: Hooks[Callable[[Mapping[str, Any]], str]] = Hooks()
    effects = await drive(on_touch(memory=memory, transcript=object(), config=ContextConfig()))
    assert [e.name for e in effects] == ["acquire"]
    assert effects[0].args[0] == memory.add and isinstance(effects[0].args[1], OnTouch)
