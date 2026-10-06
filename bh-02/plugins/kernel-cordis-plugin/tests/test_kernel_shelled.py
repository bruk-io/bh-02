"""`shelled` and `shell_note`: the shell commands an input runs for work Python does itself, and
what the model is told about them."""

import re
import textwrap

import pytest

from kernel_cordis_plugin import instructions_for, programs, shell_note, shelled


@pytest.mark.parametrize(
    ("code", "found"),
    [
        (  # the shape a shell-trained model writes most: a pipeline, printed whole
            'import subprocess\nprint(subprocess.run("cat a.py | head -50", shell=True,'
            " capture_output=True, text=True).stdout)",
            (("cat", "read"), ("head", "read")),
        ),
        ('subprocess.run(["sed", "-i", "s/a|b/c/", "f.py"])', (("sed", "edit"),)),  # a quoted | is a word
        ("subprocess.run(\"cat > notes.md << 'EOF'\\nhello\\nEOF\", shell=True)", (("cat", "write"),)),
        ("import os\nos.system(\"ls -la && find . -name '*.py'\")", (("ls", "list"), ("find", "list"))),
        ('subprocess.run(["bash", "-lc", "mkdir -p out && cp a b"])', (("mkdir", "files"), ("cp", "files"))),
        (  # an alias, and a function imported by name, in the same input
            "import subprocess as sp\nfrom subprocess import check_output as co\n"
            'sp.run(["tail", "-n", "5", "log"])\nco("wc -l x", shell=True)',
            (("tail", "read"), ("wc", "read")),
        ),
        ('subprocess.run(f"cat {path}", shell=True)', (("cat", "read"),)),  # up to the first field
        ('subprocess.run("LC_ALL=C /bin/ls > /dev/null 2>&1", shell=True)', (("ls", "list"),)),
    ],
)
def test_an_input_that_does_file_work_through_a_shell_is_found(
    code: str, found: tuple[tuple[str, str], ...]
) -> None:
    assert shelled(code) == found


@pytest.mark.parametrize(
    "code",
    [
        'print(subprocess.run("grep -rn foo src", shell=True, capture_output=True, text=True).stdout)',
        'subprocess.run(["uv", "run", "pytest", "-q"]); subprocess.run(["git", "status"])',
        "subprocess.run(['echo', 'hi'])",  # printing is not writing a file
        'from pathlib import Path\nprint(Path("a").read_text())',
        'run("cat a")',  # a function of the input's own, not subprocess's
        "def (",
    ],
)
def test_programs_python_cannot_replace_and_plain_python_are_not(code: str) -> None:
    """Searching is fair to run (a program that knows what git ignores), and so are tests, git
    and builds: only work Python does itself is pointed out."""
    assert shelled(code) == ()


def test_programs_are_every_command_an_input_runs_and_whether_it_writes_a_file() -> None:
    """What `scripts/model-friction` reads an input by, searching and all."""
    code = 'r = subprocess.run("grep -rn x src | head > out.txt", shell=True)\nos.system("pytest -q")'
    assert programs(code) == (("grep", False), ("head", True), ("pytest", False))
    assert programs("print(1)") == () == programs("def (")
    heredoc = "subprocess.run(\"cat > run.sh << 'EOF'\\nrm -rf build\\nEOF\\nchmod +x run.sh\", shell=True)"
    assert programs(heredoc) == (("cat", True), ("chmod", False))  # the document's lines are text


def test_the_note_names_the_commands_and_how_python_does_each_kind_of_work() -> None:
    note = shell_note((("cat", "read"), ("head", "read"), ("sed", "edit")))
    assert note.startswith("(this input ran `cat`, `head` and `sed` through a shell.")
    assert note.count("Path(p).read_text()") == 2  # once for reading, once in how to edit
    assert "text.count(old) == 1" in note and "Keep subprocess for programs such as tests" in note
    assert shell_note(()) == ""


def test_the_example_the_model_is_shown_is_python() -> None:
    """The instructions show a CodeAct input and a later one that uses what it kept: each must
    compile as written, or the model learns from a broken example."""
    blocks = re.findall(r"((?:^    .*\n?)+)", instructions_for(True), re.M)
    assert len(blocks) == 2 and "uses = [" in blocks[0] and "uses[0][0]" in blocks[1]
    for block in blocks:
        compile(textwrap.dedent(block), "<example>", "exec")
