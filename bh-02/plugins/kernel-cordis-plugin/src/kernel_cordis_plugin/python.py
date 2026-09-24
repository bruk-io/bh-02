"""The model's one tool, `python(code)`, and what the model is told about it.

CodeAct (Wang et al., arXiv:2402.01030) as ../harness/ARCHITECTURE.MD does it: one tool, over
the provider's standard tool calling, and it carries code. Inside a cell there is only Python:
a cell reads and writes files with `open` or `pathlib` and runs programs with `subprocess`, and
the jail decides what it may touch.

What the model is told follows the jail (`confined`): a confined cell is contained, so it runs
without asking; an unconfined one can do anything the person can, so the loop shows each one
to the person and runs it only on a yes.
"""

from collections.abc import Mapping
from typing import Any

__all__ = ["PYTHON", "instructions_for"]

PYTHON: Mapping[str, Any] = {
    "name": "python",
    "description": (
        "Run Python in a persistent namespace, in the project directory: variables, imports and "
        "functions stay for later calls. print() what you want to see; a last expression is shown "
        "too. Read and write files with open() or pathlib, run programs with subprocess."
    ),
    "parameters": {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "The Python to run."}},
        "required": ["code"],
    },
}


def instructions_for(confined: bool) -> str:
    """What the model is told about acting in code: the one tool, and where its code runs."""
    where = (
        "Your code runs in a jail: it can write only inside the project directory, cannot reach "
        "the network, and cannot read credentials. Inside the project it also cannot write what "
        "could run code later (.git/hooks, .git/config, .claude, shell rc files) or bh-02's own "
        "files, so `git init` fails there; ask the person instead. Cells run without asking."
        if confined
        else "Your code runs unjailed, with the person's own permissions: each cell is shown to "
        "the person and runs only if they approve it, so keep cells small and say what they do."
    )
    return "\n".join(
        [
            "You act by writing Python: your one tool is `python`, and its `code` runs in a "
            "persistent namespace whose working directory is the project. There is nothing in the "
            "namespace but Python: read and edit files with open() or pathlib, run programs with "
            "subprocess, keep results in variables, and print what you need to see. Read a "
            "traceback and fix the code.",
            "",
            where,
        ]
    )
