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

from collections.abc import Mapping
from typing import Any

__all__ = ["PYTHON", "instructions_for"]

PYTHON: Mapping[str, Any] = {
    "name": "python",
    "description": (
        "Your own Python REPL, which persists: `code` runs as if typed at its prompt, in the "
        "project directory, and variables, imports and functions stay for later calls. print() "
        "what you want to see; a last expression is shown too. Read and write files with open() "
        "or pathlib; run programs with subprocess.run([...], capture_output=True, text=True) and "
        "print what they said."
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
_USE = (
    "How to use it:",
    "- Build up state: define a helper once (a function that runs the tests and prints only the "
    "failures, say) and call it later. A variable holds what was read, not the file: read a "
    "file again after you change it.",
    "- It is plain Python, not IPython or a notebook: no `!command` or `%magic`, and no "
    "top-level `await` (use asyncio.run). Read and edit files with open() or pathlib; there is "
    "no other file tool. os.chdir() moves every later input too, so prefer paths (and "
    "subprocess's cwd=).",
    "- print() what you need to see; an input's last expression is shown too, as at a REPL "
    "prompt. Output over 20,000 characters keeps its start and its end, and is saved whole to a "
    "file the cut names: print what matters, and read the file for the middle.",
    "- Run programs with subprocess.run([...], capture_output=True, text=True, timeout=...) and "
    "print what they said: a program's own output (os.system, a subprocess not captured) never "
    "reaches you, and an input runs until it ends, so give anything slow a timeout.",
    "- There is no stdin (input() fails). An input that raises answers with its traceback, each "
    "frame with its source line and the input it is in (`<input 3>`, the REPL's third): read it "
    "and fix the code. The person can interrupt a running input (KeyboardInterrupt); what the "
    "REPL holds stays as it was.",
    "- Several calls in one message run in order, one input each. The person sees every input "
    "and its output as it runs, so say what a result means rather than repeat it.",
)


def instructions_for(confined: bool, startup: str = ".bh-02/kernel.py") -> str:
    """What the model is told about acting in code: the one tool, its REPL and how long that
    lasts, the project's startup file (`startup`), how to use it, and where its code runs."""
    keep = f"Helpers worth having in every session go in {startup}, which you can write and grow: " + (
        "a new REPL runs it before your first input and says what it defined."
        if confined
        else "when it is there, a new REPL says so, and you run it as an input of your own (here "
        "every input is put to the person, so it does not run unasked)."
    )
    where = (
        "Your code runs in a jail: it can write only inside the project directory, cannot reach "
        "the network, and cannot read credentials. Inside the project it also cannot write what "
        "could run code later (.git/hooks, .git/config, .claude, shell rc files) or bh-02's own "
        "files, so `git init` fails there; ask the person instead. Inputs run without asking."
        if confined
        else "Your code runs unjailed, with the person's own permissions: each input is shown to "
        "the person and runs only if they approve it, so keep inputs small and say what they do."
    )
    return "\n".join([f"{_REPL} {keep}", "", *_USE, "", where])
