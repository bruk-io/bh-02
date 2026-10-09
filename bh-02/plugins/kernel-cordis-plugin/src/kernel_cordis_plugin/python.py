"""The model's one tool, `python(code)`, and what the model is told about it.

CodeAct (Wang et al., arXiv:2402.01030) as ../harness/ARCHITECTURE.MD does it: one tool, over
the provider's standard tool calling, and it carries code. To the model the tool is a Python
REPL of its own that persists (the kernel): each call is one input to it, plain Python that
reads and writes files with `open` or `pathlib` and runs programs with `subprocess`, and the
jail decides what it may touch.

What the model is told follows the jail (`confined`): a confined REPL is contained, so its
inputs run without asking; an unconfined one can do anything the person can, so the loop shows
each input to the person and runs it only on a yes.
"""

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["PYTHON", "instructions_for"]

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
    "every later one, in this turn and later ones, and across a /model switch or a /compact. It "
    "starts empty when bh-02 starts (a resumed session too: the conversation comes back, the "
    "variables do not), after /clear, and if the process dies (the next input says so): then "
    "define again what you need rather than assume it."
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
    elsewhere: Sequence[str] = (),
) -> str:
    """What the model is told about acting in code: the one tool, its REPL and how long that
    lasts, the startup files (`startup`, the project's, which are the model's to write; `theirs`,
    the person's own, which run before them and are not), how to use it, and where its code
    runs. `reads`, the trees the jail lets code read when it reads by allowlist (a Linux jail), is
    said plainly, so the model spends no steps on reads that can't succeed, and so is how to see
    a helper of the person's, whose file is usually not among them. `elsewhere`, the directories
    outside the project the jail lets code write (a row's, such as the project's auto memory),
    is named with the project, so the model knows its code can write there too."""
    writes = " and ".join(["the project directory", *elsewhere])
    where = (
        f"Your code runs in a jail: it can write only inside {writes}, cannot reach "
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
        if confined and theirs:
            where += (
                " The person's startup file runs in the REPL even where your code finds no such "
                "file (bh-02 reads it for the REPL): inspect.getsource(helper) shows one of its "
                "helpers."
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
