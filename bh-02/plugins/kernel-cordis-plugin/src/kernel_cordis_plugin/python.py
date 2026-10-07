"""The model's one tool, `python(code)`, and what the model is told about it.

CodeAct (Wang et al., arXiv:2402.01030) as ../harness/ARCHITECTURE.MD does it: one tool, over
the provider's standard tool calling, and it carries code. To the model the tool is a Python
REPL of its own that persists (the kernel): each call is one input to it, plain Python that
reads and writes files with `open` or `pathlib` and runs programs with `subprocess`, and the
jail decides what it may touch.

What the model is told follows the jail (`confined`): a confined REPL is contained, so its
inputs run without asking; an unconfined one can do anything the person can, so the loop shows
each input to the person and runs it only on a yes.

A model trained on shell tools tends to use the REPL as one: each input a single `cat`, `sed`
or `ls` through subprocess, its output printed whole. `programs` is what an input runs,
`shelled` the part of it Python does itself, and `shell_note` how Python does that work here,
where the result stays in a variable for the next input. `ShellHints` is the `memory` function
that tells the model so with that input's result, once for each kind of work in a conversation,
a resumed one too: it reads what the conversation's transcript says the model was told.
"""

import ast
import itertools
import os
import re
import shlex
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "PYTHON",
    "Memory",
    "ShellHints",
    "Transcript",
    "instructions_for",
    "programs",
    "shell_note",
    "shelled",
]

PYTHON: Mapping[str, Any] = {
    "name": "python",
    "description": (
        "Your own Python REPL, which persists: `code` runs as if typed at its prompt, in the "
        "project directory, and variables, imports and functions stay for later calls. Work in "
        "Python, not through a shell: read, search and edit files with pathlib and re, keep what "
        "you find in variables, and do several steps in one input. Run programs (tests, git, "
        "builds) with subprocess.run([...], capture_output=True, text=True, timeout=...) and work "
        "with what they print. print() what you want to see; a last expression is shown too."
    ),
    "parameters": {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "The Python to run."}},
        "required": ["code"],
    },
}

_REPL = (
    "Your one tool is `python`: a Python REPL of your own, the CodeAct tool bh-02 ships with. "
    "Each call sends it `code`, as if you typed it at the prompt, and you get back what it "
    "printed. It is one process, whose working directory is the project, and it persists for "
    "this run of bh-02: the variables, imports and functions an input defines are there for "
    "every later one, in this turn and later ones, and across a /model switch. It starts empty "
    "when bh-02 starts (a resumed session too: the conversation comes back, the variables do "
    "not), after /clear, and if the process dies (the next input says so): then define again "
    "what you need rather than assume it."
)
_EXAMPLE = """    import re, subprocess
    from pathlib import Path
    files = subprocess.run(["git", "ls-files", "*.py"], capture_output=True, text=True).stdout.split()
    uses = [(f, n, line.strip()) for f in files
            for n, line in enumerate(Path(f).read_text().splitlines(), 1)
            if re.search(r"\\bretries\\b", line)]
    print(len(uses), "lines in", len({f for f, _, _ in uses}), "files"); print(*uses[:20], sep="\\n")

and a later input, with `uses` still there, edits one of those files:

    p = Path(uses[0][0])
    text = p.read_text()
    assert text.count("retries = 3") == 1, text.count("retries = 3")
    p.write_text(text.replace("retries = 3", "retries = 5"))"""
_USE = (
    "How to use it:",
    "- Work in Python, not through a shell: there is no shell tool, and an input that only runs "
    "cat, grep, sed or ls through subprocess and prints what it said leaves the REPL unused. "
    "Read a file with Path(p).read_text(), list files with Path(d).rglob('*.py') (or `git "
    "ls-files`, which leaves out what git ignores), search with re over the lines, and edit by "
    "replacing text you checked occurs once. Do several steps in one input, and keep what they "
    "found in variables for the next. One input finds every line that names `retries`:",
    "",
    _EXAMPLE,
    "",
    "- Build up state: define a helper once (a function that runs the tests and prints only the "
    "failures, say) and call it later. A variable holds what was read, not the file: read a "
    "file again after you change it.",
    "- It is plain Python, not IPython or a notebook: no `!command` or `%magic`, and no "
    "top-level `await` (use asyncio.run). os.chdir() moves every later input too, so prefer "
    "paths (and subprocess's cwd=).",
    "- print() what you need to see; an input's last expression is shown too, as at a REPL "
    "prompt. Output over 20,000 characters keeps its start and its end, and is saved whole to a "
    "file the cut names: print what matters, and read the file for the middle.",
    "- Run the programs Python can't replace (tests, git, a build) with subprocess.run([...], "
    "capture_output=True, text=True, timeout=...), and treat what they print as data: keep it, "
    "filter it, print what matters. A program's own output (os.system, a subprocess not "
    "captured) never reaches you, and an input runs until it ends, so give anything slow a "
    "timeout.",
    "- There is no stdin (input() fails). An input that raises answers with its traceback, each "
    "frame with its source line and the input it is in (`<input 3>`, the REPL's third): read it "
    "and fix the code. The person can interrupt a running input (KeyboardInterrupt); what the "
    "REPL holds stays as it was.",
    "- Several calls in one message run in order, one input each. The person sees every input "
    "and its output as it runs, so say what a result means rather than repeat it.",
)


def instructions_for(
    confined: bool,
    startup: Sequence[str] = (".bh-02/kernel.py",),
    reads: Sequence[str] = (),
    *,
    theirs: Sequence[str] = (),
) -> str:
    """What the model is told about acting in code: the one tool, its REPL and how long that
    lasts, the startup files (`startup`, the project's, which are the model's to write; `theirs`,
    the person's own, which run before them and are not), how to use it, and where its code
    runs. `reads`, the trees the jail lets code read when it reads by allowlist (a Linux jail), is
    said plainly, so the model spends no steps on reads that can't succeed."""
    where = (
        "Your code runs in a jail: it can write only inside the project directory, cannot reach "
        "the network, and cannot read credentials. Inside the project it also cannot write what "
        "could run code later (.git/hooks, .git/config, .claude, shell rc files) or bh-02's own "
        "files, so `git init` fails there; ask the person instead. Inputs run without asking."
        if confined
        else "Your code runs unjailed, with the person's own permissions: each input is shown to "
        "the person and runs only if they approve it, so keep inputs small and say what they do."
    )
    if reads:
        where += (
            f" The jail your code runs in reads only these trees: {', '.join(reads)}. Nothing else "
            "exists in it, the person's home directory included (at most the path to an "
            "interpreter installed under it): no ~/.gitconfig, ~/.ssh, dotfiles or caches, so don't "
            "look for files outside these. git commits carry the person's name and email when git "
            "on their machine knows them."
        )
    keep = _keep(confined, (startup,) if isinstance(startup, str) else startup, theirs)
    return "\n".join([f"{_REPL} {keep}".rstrip(), "", *_USE, "", where])


def _keep(confined: bool, startup: Sequence[str], theirs: Sequence[str]) -> str:
    """What the model is told of the startup files: the project's (`startup`) are its own to
    write and grow; the person's (`theirs`), which come first, are theirs and not its to edit."""
    runs = (
        "a new REPL runs it before your first input and says what it defined."
        if confined
        else "when it is there, a new REPL says so, and you run it as an input of your own (here "
        "every input is put to the person, so it does not run unasked)."
    )
    said = []
    if startup:
        said.append(
            f"Helpers worth having in every session go in {' and '.join(startup)}, the project's "
            f"startup file, which you can write and grow: {runs}"
        )
    if theirs and startup:
        said.append(
            "Only the project's startup file is yours to edit: the person may keep helpers of "
            f"their own in {' and '.join(theirs)}, which comes before it, and that file is theirs."
        )
    elif theirs:
        said.append(
            f"The person may keep helpers of their own in {' and '.join(theirs)}: {runs} That file "
            "is theirs, not yours to edit."
        )
    return " ".join(said)


# The shell commands an input may run for work Python does itself, by kind of work, and how
# Python does each kind here. Searching (grep, rg) is not one: a program that knows what git
# ignores is fair to run, and its hits are data for the next step.
_KINDS = {
    "read": ("cat", "head", "tail", "wc"),
    "edit": ("sed", "awk"),
    "write": ("tee",),
    "list": ("ls", "find", "tree"),
    "files": ("mkdir", "touch", "cp", "mv", "rm"),
}
_KIND_OF = {command: kind for kind, commands in _KINDS.items() for command in commands}
_INSTEAD = {
    "read": "read a file with Path(p).read_text(), and slice its .splitlines() for a part",
    "edit": "edit a file with text = Path(p).read_text(), check text.count(old) == 1, then "
    "Path(p).write_text(text.replace(old, new))",
    "write": "write a file with Path(p).write_text(text), or open(p, 'a') to append",
    "list": "list files with Path(d).iterdir() or Path(d).rglob('*.py')",
    "files": "make, copy, move and remove files with Path(d).mkdir(parents=True, exist_ok=True), "
    "shutil.copy, Path.rename and Path.unlink (shutil.rmtree for a directory)",
}
_RUNNERS = {
    "subprocess": {"run", "call", "check_call", "check_output", "Popen", "getoutput", "getstatusoutput"},
    "os": {"system", "popen"},
}
_SHELLS = {"sh", "bash", "zsh"}
_SEPARATORS = {"|", "||", "&&", ";", "&", "(", ")"}
# What an input that did such work is told (`shell_note`): the commands it ran, and the way
# Python does each kind of work they did, joined by "; ".
_HINT = (
    "(this input ran {commands} through a shell. Python does that itself here, and keeps the "
    "result in a variable for the next input: {ways}. Keep subprocess for programs such as "
    "tests, git and builds.)"
)
# That note, told after a result in a transcript's `tool` entry: the loop puts each note after a
# blank line, and another note or the entry's end follows it. Its ways are caught.
_HINTED = re.compile(
    r"\n\n"
    + re.escape(_HINT).replace(re.escape("{commands}"), r"[^\n]*?").replace(re.escape("{ways}"), r"([^\n]*?)")
    + r"(?=\n\n|\Z)"
)


def programs(code: str) -> tuple[tuple[str, bool], ...]:
    """Each program `code` runs through subprocess or os (each command of a shell line), by
    name, with whether its output is sent to a file, in the order they appear: () for none, and
    for code that does not parse."""
    try:
        tree = ast.parse(code)
    except SyntaxError, ValueError:
        return ()
    return tuple(found for line in _command_lines(tree) for found in _split(line))


def shelled(code: str) -> tuple[tuple[str, str], ...]:
    """The shell commands `code` runs for work Python does itself, as (command, kind of work),
    each command once, in the order they appear."""
    found: dict[str, str] = {}
    for name, redirected in programs(code):
        kind = "write" if redirected else _KIND_OF.get(name)
        if kind is not None:
            found.setdefault(name, kind)
    return tuple(found.items())


def shell_note(found: Sequence[tuple[str, str]]) -> str:
    """What follows the output of an input that ran `found` (from `shelled`): how Python does
    that work here. '' for none."""
    if not found:
        return ""
    names = [f"`{command}`" for command, _ in found]
    commands = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    ways = "; ".join(dict.fromkeys(_INSTEAD[kind] for _, kind in found))
    return _HINT.format(commands=commands, ways=ways)


def _hinted(messages: Iterable[Mapping[str, Any]]) -> set[str]:
    """The kinds of work a conversation's transcript (`messages`) says the model was told Python
    does: each shell note (`shell_note`) told after an input's result names its kinds by their
    ways. A note is told when its exact text follows the result in a `tool` entry, not when a
    result or the person quotes it."""
    kinds = {way: kind for kind, way in _INSTEAD.items()}
    told = (str(m.get("content") or "") for m in messages if m.get("role") == "tool")
    return {
        kinds[way]
        for content in told
        for ways in _HINTED.findall(content)
        for way in ways.split("; ")
        if way in kinds
    }


@runtime_checkable
class Memory(Protocol):
    """What the shell-hints row needs of the `memory` value (CONTRACTS.md: memory): a function
    added, and its remover back."""

    def add(self, fn: Callable[[Mapping[str, Any]], str]) -> Callable[[], None]: ...


@runtime_checkable
class Transcript(Protocol):
    """What the shell-hints row needs of the `transcript` value (CONTRACTS.md: transcript): the
    conversation so far, whose `tool` entries carry each input's result and the notes told with
    it."""

    @property
    def messages(self) -> Sequence[Mapping[str, Any]]: ...


class ShellHints:
    """A `memory` function: given an input (`code`, ...), how Python does the shell work it ran
    (`shell_note`), for each kind of work the first time this conversation sees it; '' after.

    What the conversation was told before this began (a resumed session's, or this one's before
    the row reloaded) is in its `transcript`, read once, at the first input: a kind a shell note
    there named is told already."""

    def __init__(self, transcript: Transcript) -> None:
        self._transcript = transcript
        # the kinds of work the model has been told Python does; None until the first input reads
        # them from the transcript. Called on the loop's `executor`, one call at a time, so it
        # takes no lock.
        self._told: set[str] | None = None

    def __call__(self, input: Mapping[str, Any]) -> str:
        if self._told is None:
            self._told = _hinted(self._transcript.messages)
        told = self._told
        new = [(command, kind) for command, kind in shelled(str(input.get("code", ""))) if kind not in told]
        told.update(kind for _, kind in new)
        return shell_note(new)


def _command_lines(tree: ast.AST) -> Iterator[str]:
    """Each command an input runs through subprocess or os, as shell text: a string as written
    (an f-string up to its first field), a list's leading words quoted, `sh -c`'s script."""
    modules = {"subprocess": "subprocess", "os": "os"}  # a name in the input -> the module
    functions: dict[str, tuple[str, str]] = {}  # an imported function's name -> (module, function)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.asname or a.name: a.name for a in node.names if a.name in _RUNNERS}
        elif isinstance(node, ast.ImportFrom) and node.module in _RUNNERS:
            functions |= {a.asname or a.name: (node.module, a.name) for a in node.names}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module, name = modules.get(func.value.id, ""), func.attr
        elif isinstance(func, ast.Name) and func.id in functions:
            module, name = functions[func.id]
        else:
            continue
        if name not in _RUNNERS.get(module, ()):
            continue
        given = node.args[0] if node.args else None
        given = given or next((k.value for k in node.keywords if k.arg in ("args", "cmd", "command")), None)
        if isinstance(given, ast.List | ast.Tuple):
            words: list[str] = []
            for element in given.elts:
                if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
                    break
                words.append(element.value)
            if len(words) > 2 and os.path.basename(words[0]) in _SHELLS and words[1] in ("-c", "-lc"):
                yield words[2]
            elif words:
                yield shlex.join(words)
        elif isinstance(given, ast.Constant) and isinstance(given.value, str):
            yield given.value
        elif isinstance(given, ast.JoinedStr):
            parts = []
            for part in given.values:
                if not (isinstance(part, ast.Constant) and isinstance(part.value, str)):
                    break
                parts.append(part.value)
            yield "".join(parts)


def _split(text: str) -> Iterator[tuple[str, bool]]:
    """Each command in shell text, by name, and whether its output is sent to a file (`>` or
    `>>`, not to /dev/null). A here-document's lines are its text, not commands."""
    ending: str | None = None  # the line that ends the here-document being read
    for line in text.splitlines():
        if ending is not None:
            ending = None if line.strip() == ending else ending
            continue
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            words = list(lexer)
        except ValueError:  # an unclosed quote: the words as they split
            words = line.split()
        ending = next(
            (after.lstrip("-") for before, after in itertools.pairwise(words) if before == "<<"), None
        )
        segment: list[str] = []
        for word in [*words, ";"]:
            if word not in _SEPARATORS:
                segment.append(word)
                continue
            names = [w for w in segment if not (w.partition("=")[0].isidentifier() and "=" in w)]
            if names:
                targets = [after for before, after in itertools.pairwise(segment) if before in (">", ">>")]
                yield os.path.basename(names[0]), any(t != "/dev/null" for t in targets)
            segment = []
