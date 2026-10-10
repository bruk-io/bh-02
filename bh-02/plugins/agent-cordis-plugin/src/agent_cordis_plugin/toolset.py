"""The tools a conversation is offered, and what the model is told when they change.

A request sends the tool list first (before the system prompt), so a model server reuses its
work on a conversation only while that list reads the same: a tool added partway through (an
extension's, a layer's row) would make the whole conversation new to it again. So the loop
keeps the list a conversation began with in its transcript, as a `tools` entry (`begun`), and
each later change as another, what was added, removed or redefined (`changed`), and tells the
model what changed on the next message it reads (`told`), as it does a changed prompt.

What a request offers is each provider's choice (CONTRACTS.md: model, `tool_changes`): `fixed`,
the list the conversation began with, for its life, so the cache holds (a change is told, and an
added tool waits for the next conversation to be offered); or `listed`, the list as it reads
now (`listed`), for a provider whose cache a changed list does not cost, or that tells a change
its own way. Either way the transcript says which list each request offered, so a resumed
session rebuilds the same requests.

Everything here is pure.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

__all__ = ["FIXED", "LISTED", "begun", "changed", "listed", "removed", "told"]

type Json = Mapping[str, Any]

FIXED: Final = "fixed"  # the list a conversation began with, for its life
LISTED: Final = "listed"  # the list as it reads now

_DESCRIBED = 200  # how much of a tool's description the model is told with its name


def _named(specs: Iterable[Json]) -> dict[str, Json]:
    return {str(spec["name"]): spec for spec in specs}


def begun(entries: Iterable[Json]) -> list[Json] | None:
    """The tools the conversation began with: its first `tools` entry's list; None when the
    transcript records none (a new conversation, or one begun before the loop kept its tools)."""
    first = next((entry for entry in entries if entry.get("role") == "tools" and "tools" in entry), None)
    return None if first is None else [dict(spec) for spec in first["tools"]]


def listed(entries: Iterable[Json]) -> list[Json] | None:
    """The tools as the transcript last recorded them: the list the conversation began with,
    then each change after it applied in turn, in name order; None when it records none. An
    entry the loop could not have written (a person's edit of the file) is passed over."""
    tools: dict[str, Json] | None = None
    for entry in entries:
        if entry.get("role") != "tools":
            continue
        if "tools" in entry and tools is None:
            tools = _named(entry["tools"])
        elif tools is not None and "tools" not in entry:
            for name in _strings(entry.get("removed")):
                tools.pop(name, None)
            for key in ("added", "redefined"):
                tools.update(_named(spec for spec in _specs(entry.get(key))))
    return None if tools is None else [tools[name] for name in sorted(tools)]


def removed(entries: Iterable[Json]) -> frozenset[str]:
    """The tools the transcript records as removed since the conversation began, and not added
    again since."""
    gone: set[str] = set()
    for entry in entries:
        if entry.get("role") == "tools" and "tools" not in entry:
            gone |= set(_strings(entry.get("removed")))
            gone -= {str(spec["name"]) for key in ("added", "redefined") for spec in _specs(entry.get(key))}
    return frozenset(gone)


def changed(before: Sequence[Json], after: Sequence[Json]) -> dict[str, Any] | None:
    """The `tools` entry that records `after` following `before`: the tools `added`, the names
    `removed`, and the tools `redefined` (named alike, specified differently), each in name
    order and only when there are any; None when the two lists are the same."""
    old, new = _named(before), _named(after)
    change: dict[str, Any] = {
        "added": [new[name] for name in sorted(new.keys() - old.keys())],
        "removed": sorted(old.keys() - new.keys()),
        "redefined": [new[name] for name in sorted(new.keys() & old.keys()) if new[name] != old[name]],
    }
    kept = {key: value for key, value in change.items() if value}
    return {"role": "tools", **kept} if kept else None


def told(change: Json, mode: str) -> str:
    """What the model is told with the next message it reads after `change` (a `changed` entry):
    each tool added or redefined by name, with the start of its description and the input it
    takes, and each tool removed by name; then what that means for this conversation, which
    depends on whether the provider offers the list as it reads now (`listed`) or as the
    conversation began (`fixed`)."""
    parts = ["(bh-02: your tools have changed since this conversation began."]
    for key, said in (("added", "Added"), ("redefined", "Redefined")):
        for spec in _specs(change.get(key)):
            parts.append(f"{said}: {_described(spec)}.")
    if names := list(_strings(change.get("removed"))):
        parts.append(f"Removed: {', '.join(f'`{name}`' for name in names)}; a call to one does not run.")
    if mode == LISTED:
        parts.append("Your tool list reads as they are now.)")
    elif _specs(change.get("added")) or _specs(change.get("redefined")):
        parts.append(
            "Your tool list stays as this conversation began, so the model server's work on it "
            "is kept: an added tool is offered to you from the next conversation (/clear or "
            "/compact), and a redefined one takes the input it reads now.)"
        )
    else:
        parts.append("Your tool list stays as this conversation began.)")
    return " ".join(parts)


def _described(spec: Json) -> str:
    """A tool by name, the start of its description, and the names of its input's properties."""
    description = " ".join(str(spec.get("description") or "").split())
    if len(description) > _DESCRIBED:
        description = description[: _DESCRIBED - 1] + "…"
    parameters = spec.get("parameters") or spec.get("input_schema") or {}
    properties = parameters.get("properties") if isinstance(parameters, Mapping) else None
    takes = ", ".join(f"`{key}`" for key in properties) if isinstance(properties, Mapping) else ""
    said = f"`{spec['name']}`"
    if description:
        said += f" ({description})"
    return f"{said}, taking {takes}" if takes else said


def _specs(value: object) -> list[Json]:
    """The tool specs in a `tools` entry's field, each a mapping with a name; [] for anything else."""
    if not isinstance(value, list):
        return []
    return [spec for spec in value if isinstance(spec, Mapping) and isinstance(spec.get("name"), str)]


def _strings(value: object) -> list[str]:
    """The names in a `tools` entry's `removed`; [] for anything else."""
    return [str(name) for name in value if isinstance(name, str)] if isinstance(value, list) else []
