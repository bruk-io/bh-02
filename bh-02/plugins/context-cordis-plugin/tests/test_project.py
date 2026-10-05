"""The prompt as a function, and the files it is read from, in a temporary project."""

from pathlib import Path

from context_cordis_plugin import ContextConfig, ProjectContext, branch_of, describe, project
from cordis.testing import drive


def test_the_prompt_says_where_and_carries_the_project_s_guidance() -> None:
    text = describe("/src/app", "main", "2026-09-22", ("CLAUDE.md", "Use uv.\n"))
    assert "Working directory: /src/app" in text and "Git branch: main" in text
    assert "The project's own instructions (CLAUDE.md), written for whichever agent" in text
    assert text.endswith("do the same in Python.\n\nUse uv.")
    bare = describe("/src/app", None, "2026-09-22", None)
    assert "Git branch" not in bare and "instructions" not in bare


def test_the_prompt_says_the_model_is_in_bh_02_and_not_in_claude_code() -> None:
    # A CLAUDE.md is often addressed to Claude Code, and the claude-code provider's prompt opens
    # with Claude Code's own line: the prompt says first where the model really is.
    text = describe("/src/app", None, "2026-09-22", ("CLAUDE.md", "Guidance to Claude Code.\n"))
    first = text.split("\n\n")[0]
    assert first.startswith("You are the model in bh-02, a coding harness")
    assert "You are not Claude Code and not running inside it" in first
    assert "bh-02 is a cordis composition" in text  # what it is made of, and that it changes live
    assert "where they name Claude Code or another agent, they mean you" in text


def test_a_detached_head_names_no_branch() -> None:
    assert branch_of("ref: refs/heads/feature/x\n") == "feature/x"
    assert branch_of("3f1c0de\n") is None


def test_the_context_is_read_fresh_from_the_project(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    context = ProjectContext(ContextConfig(root=str(tmp_path), max_chars=10))
    assert "instructions" not in context.text()
    (tmp_path / "AGENTS.md").write_text("agents")
    assert "(AGENTS.md)" in context.text()
    (tmp_path / "CLAUDE.md").write_text("claude first, and long enough to cut")
    text = context.text()
    assert "(CLAUDE.md)" in text and "claude fir\n... [26 more chars]" in text  # the first found, capped
    assert "Git branch: main" in text


async def test_the_row_binds_the_context_under_system() -> None:
    effects = await drive(project(config=ContextConfig()))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "system")]
    assert isinstance(effects[0].args[1], ProjectContext)
