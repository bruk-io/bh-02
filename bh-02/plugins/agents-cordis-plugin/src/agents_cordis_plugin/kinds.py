"""Agent types: what kind of sub-agent a call starts. Data, never rows: a name, its section of
the child's prompt, the model it runs on, how many model steps it may take, and which of the
tool rows a child's conversation has it gets.

Two are shipped, `general` and `explore`. The person's own are TOML files in bh-02's config
directories (`host.trusted`: `~/.config/bh-02/agents/NAME.toml`, the file's name the type's),
one table of four fields:

    prompt = \"\"\"You are agent {name}, a reviewer: ...\"\"\"   # its section of the prompt
    model = "haiku"                                       # optional: the session's model
    steps = 30                                            # optional: model steps it may take
    tools = ["python"]                                    # optional: every row it may be given

A type chooses a model and so the spend, which is the person's to decide, so a type file is read
only from where the model can't write: bh-02's config directories, and never one whose reading
passes through the project (`host_paths.passes`, as the models file is judged). A type grants only
the agents row's grantable tool rows (its `tools`), never the agents row (depth one) and never
extensions or MCP.

Everything here is pure but `type_files`, which lists and reads the directories, and
`read_types` and `type_names`, which run it (the first off the event loop).
"""

import asyncio
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from host_paths import passes, roots

__all__ = [
    "EXPLORE",
    "GENERAL",
    "SHIPPED",
    "STEPS",
    "AgentType",
    "TypeFile",
    "known_types",
    "parsed_type",
    "read_types",
    "type_files",
    "type_names",
]

# How many model steps a type may take when it does not say.
STEPS: Final = 30


@dataclass(frozen=True, slots=True)
class AgentType:
    """What a kind of sub-agent is: its name, its section of the child's prompt (`{name}` is
    the agent's), the model it runs on (None: the session's), how many model steps it may take,
    and the tool rows it is given (row ids, among the agents row's grantable ones)."""

    name: str
    section: str
    model: str | None = None
    steps: int = STEPS
    tools: tuple[str, ...] = ("python",)


GENERAL = AgentType(
    "general",
    "## You are a sub-agent\n\n"
    "You are agent {name}, of type general, started by another agent to do the one task in "
    "the message you are given. You can't ask it anything, and it sees nothing you do but your "
    "last answer, which is your report: say what you found or did, with the evidence it needs "
    "(paths, names, what you ran and what it said), and what you could not do. The person may "
    "be asked to approve your calls.",
)
EXPLORE = AgentType(
    "explore",
    "## You are a sub-agent\n\n"
    "You are agent {name}, of type explore, started by another agent to find something out: the "
    "one question in the message you are given. Read, search and run what only reads; change "
    "nothing (no file written, moved or deleted, no command that changes state): other agents "
    "may be working on these files. You can't ask the agent that started you anything, and it "
    "sees nothing you do but your last answer, which is your report: what you found, with the "
    "evidence (paths, line numbers, names, what you ran and what it said), and what you could "
    "not find. The person may be asked to approve your calls.",
)
SHIPPED: frozendict[str, AgentType] = frozendict({kind.name: kind for kind in (EXPLORE, GENERAL)})

# A type's name: a file's, an agent's (`TYPE-N`) and a label's, so nothing a path or a terminal
# would read otherwise.
_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")
_FIELDS = ("prompt", "model", "steps", "tools")
_EXAMPLE = 'prompt = """You are agent {name}, ..."""'


def parsed_type(name: str, text: str, source: str, grantable: Sequence[str]) -> AgentType:
    """The type `name` a type file's `text` (read from `source`) says, its tools among
    `grantable` (the agents row's tool rows; every one of them when the file names none).

    Raises:
        ValueError: what is wrong with the file, naming it, the field and what to write there.
    """
    where = f"the agent type file {source}"
    if not _NAME.fullmatch(name):
        raise ValueError(
            f"{where}: {name!r} is not a type's name; name the file for its type: lower-case "
            "letters, digits, `_` and `-`, starting with a letter, at most 32 (such as reviewer.toml)"
        )
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{where} is not TOML ({error}); fix it") from None
    if unknown := sorted(set(data) - set(_FIELDS)):
        raise ValueError(
            f"{where}: there is no field {unknown[0]!r}; a type has `prompt`, `model`, `steps` and "
            "`tools`: take it out"
        )
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        said = "missing" if prompt is None else repr(prompt)
        raise ValueError(
            f"{where}: `prompt` is {said}; write the type's section of a sub-agent's prompt there, "
            f"such as {_EXAMPLE} ({{name}} is the agent's name)"
        )
    model = data.get("model")
    if model is not None and (not isinstance(model, str) or not model):
        raise ValueError(
            f"{where}: `model` is {model!r}, not a model's name; write one, such as "
            'model = "haiku", or take it out for the session\'s model'
        )
    steps = data.get("steps", STEPS)
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise ValueError(
            f"{where}: `steps` is {steps!r}; write how many model steps it may take, a whole number "
            f"of at least 1, such as steps = {STEPS}"
        )
    tools = data.get("tools", list(grantable))
    if not isinstance(tools, list) or not all(isinstance(tool, str) for tool in tools):
        raise ValueError(
            f"{where}: `tools` is {tools!r}; write the rows it may use as a list of names, such as "
            'tools = ["python"]'
        )
    for tool in tools:
        if tool == "agents":
            raise ValueError(
                f"{where}: `tools` names 'agents', but a sub-agent can't start one of its own (depth "
                "one, decision-0002): take it out"
            )
        if tool not in grantable or tool in ("extensions", "mcp"):
            raise ValueError(
                f"{where}: `tools` names {tool!r}, which a type can't grant: only bh-02's own tool "
                f"rows a sub-agent's conversation has ({', '.join(grantable) or 'none'}), never "
                "extensions or MCP; take it out"
            )
    return AgentType(name, prompt, model, steps, tuple(tools))


@dataclass(frozen=True, slots=True)
class TypeFile:
    """One type file found in a trusted directory: its type's name, where it is, and its text,
    or why it was not read (`refused`)."""

    name: str
    source: str
    text: str | None
    refused: str | None = None


def type_files(trusted: Iterable[str], project: Path) -> tuple[TypeFile, ...]:
    """Every `agents/*.toml` in the `trusted` directories (bh-02's config directories, the
    `host` value's `trusted`), the first of a name kept. One whose reading passes through the
    `project`, which the model's code can write, is not read: `refused` says why."""
    found: dict[str, TypeFile] = {}
    for directory in dict.fromkeys(trusted):
        place = Path(directory) / "agents"
        try:
            paths = sorted(path for path in place.glob("*.toml") if path.is_file())
        except OSError:
            continue
        for path in paths:
            if path.stem in found:
                continue
            if passes(path, roots(project)):
                found[path.stem] = TypeFile(path.stem, str(path), None, _in_project(path, project))
                continue
            try:
                found[path.stem] = TypeFile(path.stem, str(path), path.read_text(encoding="utf-8"))
            except OSError as error:
                why = f"can't read the agent type file {path} ({error.strerror}); fix it or remove it"
                found[path.stem] = TypeFile(path.stem, str(path), None, why)
    return tuple(found.values())


def _in_project(path: Path, project: Path) -> str:
    return (
        f"the agent type file {path} is not read: reading it passes through the project ({project}), "
        "which the model's code can write, and a type chooses a model and so what is spent. Keep "
        "your types in bh-02's config directory outside the project, and not a link into it"
    )


def known_types(files: Iterable[TypeFile], grantable: Sequence[str]) -> dict[str, AgentType | str]:
    """Every type there is, by name: the shipped ones, then each file's (a person's type of a
    shipped name replaces it), or why a file's can't be used."""
    known: dict[str, AgentType | str] = dict(SHIPPED)
    for each in files:
        if each.text is None:
            known[each.name] = each.refused or f"the agent type file {each.source} was not read"
            continue
        try:
            known[each.name] = parsed_type(each.name, each.text, each.source, grantable)
        except ValueError as error:
            known[each.name] = str(error)
    return known


async def read_types(trusted: Sequence[str], grantable: Sequence[str]) -> Mapping[str, AgentType | str]:
    """`known_types` over the files `type_files` finds (the project: the working directory),
    read off the event loop."""
    files = await asyncio.to_thread(type_files, trusted, Path.cwd())
    return known_types(files, grantable)


def type_names(trusted: Sequence[str], grantable: Sequence[str]) -> list[str]:
    """The names of the types that can be used, in order, read here (on the caller's thread)."""
    known = known_types(type_files(trusted, Path.cwd()), grantable)
    return sorted(name for name, kind in known.items() if isinstance(kind, AgentType))
