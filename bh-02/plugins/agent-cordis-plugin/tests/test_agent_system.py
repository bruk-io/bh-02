"""The system prompt as a function, and the project it is read from, in a temporary directory."""

import datetime
import os
from pathlib import Path

from agent_cordis_plugin import SystemConfig, SystemPrompt, branch_of, describe, system
from cordis.testing import drive


def test_the_prompt_says_where_the_model_is_working() -> None:
    text = describe("/src/app", "main")
    assert text.endswith("Working directory: /src/app\nGit branch: main")
    assert "Git branch" not in describe("/src/app", None)
    assert "CLAUDE.md" not in text  # the project's instructions are the memory row's section


def test_the_prompt_reads_the_same_every_day(tmp_path: Path) -> None:
    """The date would make the prompt differ from the one a conversation began with every
    midnight, and the loop tell the model its instructions changed: the loop tells the date with
    the person's message instead."""
    text = SystemPrompt(SystemConfig(root=str(tmp_path))).text()
    assert "Today" not in text and datetime.date.today().isoformat() not in text


def test_the_prompt_says_the_model_is_in_bh_02_and_names_no_other_harness() -> None:
    text = describe("/src/app", None)
    first = text.split("\n\n")[0]
    assert first.startswith("You are the model in bh-02, a coding harness")
    assert "Claude Code" not in text
    assert "bh-02 is a cordis composition" in text  # what it is made of, and that it changes live


def test_the_prompt_names_no_tool_the_rows_that_register_tools_tell_of_them() -> None:
    """The tools are the rows' that register them (`tools`), so bh-02's own part of the prompt
    names none: the python tool's row says what the model should know of it in a section."""
    told = describe("/src/app", "main")
    assert "python" not in told.lower() and "REPL" not in told and "your code" not in told
    assert "runs your tool calls, each tool and where it runs" in told


def test_sections_are_told_by_name_whatever_order_rows_added_them(tmp_path: Path) -> None:
    """A broker's entries must commute: a row that adds its section again (memory:auto on every
    /clear) keeps its place, so the prompt does not read as changed. Two of one name go by their
    text."""
    first, second = (
        SystemPrompt(SystemConfig(root=str(tmp_path))),
        SystemPrompt(SystemConfig(root=str(tmp_path))),
    )
    first.add("memory", lambda: "M")
    remove = first.add("memory: auto", lambda: "A")
    first.add("extensions", lambda: "E")
    second.add("extensions", lambda: "E")
    second.add("memory: auto", lambda: "A")
    second.add("memory", lambda: "M")
    assert first.text() == second.text() and first.text().endswith("E\n\nM\n\nA")
    remove()
    first.add("memory: auto", lambda: "A")  # added again, as after a restart: the same place
    assert first.text() == second.text()
    first.add("extensions: b", lambda: "2")
    first.add("extensions: b", lambda: "1")
    assert first.text().endswith("E\n\n1\n\n2\n\nM\n\nA")


def test_a_detached_head_names_no_branch() -> None:
    assert branch_of("ref: refs/heads/feature/x\n") == "feature/x"
    assert branch_of("3f1c0de\n") is None


def test_the_branch_is_read_fresh_from_the_project(tmp_path: Path) -> None:
    prompt = SystemPrompt(SystemConfig(root=str(tmp_path)))
    assert "Git branch" not in prompt.text()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    assert "Git branch: main" in prompt.text()


def test_a_head_the_model_made_a_link_is_not_read(tmp_path: Path) -> None:
    """The model can write `.git/HEAD`: a link there, or `.git` linked elsewhere, or a second
    name for another file, could lead the prompt to a file the model may not read."""
    project, outside = tmp_path / "project", tmp_path / "outside"
    (project / ".git").mkdir(parents=True)
    (outside / ".git").mkdir(parents=True)
    secret = outside / ".git" / "HEAD"
    secret.write_text("ref: refs/heads/secret\n")
    prompt = SystemPrompt(SystemConfig(root=str(project)))
    (project / ".git" / "HEAD").symlink_to(secret)
    assert "secret" not in prompt.text()
    (project / ".git" / "HEAD").unlink()
    os.link(secret, project / ".git" / "HEAD")  # a second name
    assert "secret" not in prompt.text()
    (project / ".git" / "HEAD").unlink()
    (project / ".git").rmdir()
    (project / ".git").symlink_to(outside / ".git")
    assert "secret" not in prompt.text()


def test_a_row_adds_a_section_read_fresh_and_its_remover_takes_it_out(tmp_path: Path) -> None:
    prompt = SystemPrompt(SystemConfig(root=str(tmp_path)))
    said = ["first"]
    remove = prompt.add("a", lambda: said[-1])
    prompt.add("b", lambda: "")  # a section with nothing to say adds nothing
    assert prompt.text().endswith("\n\nfirst")
    said.append("second")
    assert prompt.text().endswith("\n\nsecond")  # read each time, not when added
    remove()
    assert "second" not in prompt.text() and not prompt.text().endswith("\n")


async def test_the_row_binds_the_prompt_under_system() -> None:
    effects = await drive(system(config=SystemConfig()))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "system")]
    assert isinstance(effects[0].args[1], SystemPrompt)
