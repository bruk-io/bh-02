"""The prompt as a function, and the files it is read from, in a temporary project."""

from pathlib import Path

from context_cordis_plugin import ContextConfig, ProjectContext, branch_of, describe, project
from cordis.testing import drive


class _Kernel:
    """The `kernel` value, as far as the context reads it: what its jail can read."""

    def __init__(self, *trees: str) -> None:
        self._trees = trees

    def reads(self) -> tuple[str, ...]:
        return self._trees


def test_the_prompt_says_where_and_carries_the_project_s_guidance() -> None:
    text = describe("/src/app", "main", "2026-09-22", ("CLAUDE.md", "Use uv.\n"))
    assert "Working directory: /src/app" in text and "Git branch: main" in text
    assert text.endswith("The project's own instructions (CLAUDE.md):\n\nUse uv.")
    bare = describe("/src/app", None, "2026-09-22", None)
    assert "Git branch" not in bare and "instructions" not in bare
    assert "jail" not in bare  # a jail that reads everything but the secrets (darwin): nothing said


def test_on_linux_the_prompt_says_what_the_jail_reads_and_that_the_home_directory_is_absent() -> None:
    text = describe("/src/app", None, "2026-09-22", None, ("/usr", "/etc", "/src/app"))
    assert "The jail your code runs in reads only these trees: /usr, /etc, /src/app." in text
    assert "the person's home directory included" in text and "no ~/.gitconfig, ~/.ssh" in text


def test_a_detached_head_names_no_branch() -> None:
    assert branch_of("ref: refs/heads/feature/x\n") == "feature/x"
    assert branch_of("3f1c0de\n") is None


def test_the_context_is_read_fresh_from_the_project(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    context = ProjectContext(ContextConfig(root=str(tmp_path), max_chars=10), _Kernel())
    assert "instructions" not in context.text()
    (tmp_path / "AGENTS.md").write_text("agents")
    assert "(AGENTS.md)" in context.text()
    (tmp_path / "CLAUDE.md").write_text("claude first, and long enough to cut")
    text = context.text()
    assert "(CLAUDE.md)" in text and "claude fir\n... [26 more chars]" in text  # the first found, capped
    assert "Git branch: main" in text


async def test_the_row_binds_the_context_under_system() -> None:
    effects = await drive(project(config=ContextConfig(), kernel=_Kernel("/usr")))
    assert [(e.name, e.args[0]) for e in effects] == [("bind", "system")]
    assert isinstance(effects[0].args[1], ProjectContext)
    assert "reads only these trees: /usr." in effects[0].args[1].text()  # read from the kernel
