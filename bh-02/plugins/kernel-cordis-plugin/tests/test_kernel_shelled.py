"""`shelled` and `shell_note`: the shell commands an input runs for work Python does itself, and
what the model is told about them; `ShellHints`, which tells it through `memory`, once for each
kind of work a conversation, a resumed one too."""

import re
import textwrap
import time
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from cordis.testing import drive
from cordis_helpers import Hooks
from kernel_cordis_plugin import (
    ShellHints,
    Transcript,
    instructions_for,
    programs,
    shell_hints,
    shell_note,
    shelled,
)


class _Kept:
    """A `transcript` value over the messages given, counting how often they are read."""

    def __init__(self, *messages: Mapping[str, Any]) -> None:
        self._messages = messages
        self.reads = 0

    @property
    def messages(self) -> tuple[Mapping[str, Any], ...]:
        self.reads += 1
        return self._messages


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


def test_shell_hints_tell_each_kind_of_shell_work_once_a_conversation() -> None:
    hints = ShellHints(_Kept())
    shown = (
        "import subprocess\nprint(subprocess.run(['cat', 'a.txt'], capture_output=True, text=True).stdout)"
    )
    first = hints({"code": shown, "result": "one", "touched": ()})
    assert first.startswith("(this input ran `cat` through a shell.") and "Path(p).read_text()" in first
    assert hints({"code": shown.replace("cat", "head")}) == ""  # reading was said: once a kind
    assert hints({"code": "subprocess.run(['ls'])"}).startswith("(this input ran `ls` through a shell.")
    assert hints({"code": "subprocess.run(['git', '--version'])"}) == ""


def test_a_resumed_conversation_from_before_the_loop_kept_notes_is_searched_for_what_it_told() -> None:
    """A resumed session (or the row reloaded) starts a new `ShellHints`, but the transcript
    holds what the model was told. An entry from before the loop kept `notes` holds it only in
    its text: a kind a shell note there named, after a blank line, is told already. One the
    person quoted, or one an entry starts with (an input printed it), is not. The transcript is
    read once, at the first input; an empty one (a new conversation, after /clear) tells every
    kind afresh."""
    read = "subprocess.run(['cat', 'a.txt'])"
    transcript = _Kept(
        {"role": "user", "content": f"why this?\n\n{shell_note((('sed', 'edit'),))}"},
        {"role": "assistant", "content": "", "tool_calls": []},
        {
            "role": "tool",
            "content": f"one\n\n{shell_note((('cat', 'read'), ('ls', 'list')))}\n\nA.",
            "call_id": "c0",
        },
        {"role": "tool", "content": shell_note((("rm", "files"),)), "call_id": "c1"},
    )
    assert isinstance(transcript, Transcript)
    hints = ShellHints(transcript)
    assert hints({"code": read.replace("cat", "head")}) == ""  # reading was told before the resume
    assert hints({"code": "subprocess.run(['find', '.'])"}) == ""  # and listing
    assert hints({"code": "subprocess.run(['sed', '-i', 's/a/b/', 'f'])"}).startswith("(this input ran `sed`")
    assert hints({"code": "subprocess.run(['rm', 'f'])"}).startswith("(this input ran `rm`")
    assert hints({"code": "subprocess.run(['sed', 'p', 'f'])"}) == ""  # told now: once
    assert transcript.reads == 1
    assert ShellHints(_Kept())({"code": read}).startswith("(this input ran `cat` through a shell.")


def test_a_resumed_conversation_reads_the_shell_notes_the_loop_kept_on_each_entry() -> None:
    """The loop keeps the notes it told with a result on its entry (`notes`), so a kind is told
    already when a shell note there names it, wherever the notes sorted and whatever the result
    printed: a note the result printed (after a blank line, as one told would be) is not one told.
    An entry without `notes` (written before the loop kept them) is searched as before."""
    other = "Zebra: another row's note, sorted after the shell note."
    told = shell_note((("cat", "read"),))
    printed = shell_note((("ls", "list"),))
    transcript = _Kept(
        {"role": "tool", "content": f"one\n\n{told}\n\n{other}", "call_id": "c0", "notes": [told, other]},
        {"role": "tool", "content": f"two\n\n{printed}", "call_id": "c1", "notes": []},
        {"role": "tool", "content": f"three\n\n{shell_note((('rm', 'files'),))}", "call_id": "c2"},
    )
    hints = ShellHints(transcript)
    assert hints({"code": "subprocess.run(['head', 'a.txt'])"}) == ""  # in the entry's notes
    assert hints({"code": "subprocess.run(['cp', 'a', 'b'])"}) == ""  # an entry from before them
    assert hints({"code": "subprocess.run(['find', '.'])"}).startswith("(this input ran `find`")


def test_a_transcript_from_before_the_memory_broker_tells_its_shell_notes_too() -> None:
    """Before `memory`, the kernel put the note after the result's last line, one newline and
    no blank line, at the entry's end: a session resumed from then was told them all the same."""
    transcript = _Kept(
        {"role": "assistant", "content": "", "tool_calls": []},
        {"role": "tool", "content": f"one\n{shell_note((('cat', 'read'),))}", "call_id": "c0"},
        {"role": "tool", "content": f"(no output)\n{shell_note((('ls', 'list'),))}", "call_id": "c1"},
    )
    hints = ShellHints(transcript)
    assert hints({"code": "subprocess.run(['head', 'a.txt'])"}) == ""
    assert hints({"code": "subprocess.run(['find', '.'])"}) == ""
    assert hints({"code": "subprocess.run(['rm', 'f'])"}).startswith("(this input ran `rm`")


@pytest.mark.parametrize("before", ["\n\n", "\n"])
def test_a_long_result_line_costs_the_search_for_told_notes_little(before: str) -> None:
    """The model's code makes a result whatever it likes, up to a line of 1 MiB. The search of a
    resumed transcript for the shell notes it told takes time in proportion to an entry, not its
    square: a 500 KB line repeating a note's pieces took 11 seconds, in the loop's thread, which
    a reply and a stop wait for. So after a blank line, or the one newline of an older one."""
    note = shell_note((("cat", "read"),))
    through, keep = note[note.index(" through") : note.index("read a file")], note[note.index(". Keep") :]
    crafted = f"one{before}(this input ran " + (through + keep) * 3_000 + "x"
    hints = ShellHints(_Kept({"role": "tool", "content": crafted, "call_id": "c0"}))
    started = time.perf_counter()
    assert hints({"code": "subprocess.run(['cat', 'f'])"}).startswith("(this input ran `cat`")
    assert time.perf_counter() - started < 1.0


async def test_the_shell_hints_row_adds_its_function_to_memory() -> None:
    memory: Hooks[Callable[[Mapping[str, Any]], str]] = Hooks()
    effects = await drive(shell_hints(memory=memory, transcript=_Kept()))
    assert [e.name for e in effects] == ["acquire"]
    assert effects[0].args[0] == memory.add and isinstance(effects[0].args[1], ShellHints)


def test_on_linux_the_model_is_told_what_the_jail_reads_and_that_the_home_directory_is_absent() -> None:
    """A jail that reads by allowlist (Linux) says which trees: the model spends no steps on reads
    that can't succeed. One that reads everything but the secrets (darwin) says nothing of it."""
    text = instructions_for(True, reads=("/usr", "/etc", "/src/app"))
    assert "The jail your code runs in reads only these trees: /usr, /etc, /src/app." in text
    assert "the person's home directory included" in text and "no ~/.gitconfig, ~/.ssh" in text
    assert "reads only these trees" not in instructions_for(True)
