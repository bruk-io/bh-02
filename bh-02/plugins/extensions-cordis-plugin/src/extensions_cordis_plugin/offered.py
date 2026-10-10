"""What an extension may offer the model, decided as pure functions of what it sent.

The worker runs the model's code, so the host takes nothing it sends on trust: a tool's spec is
rebuilt from the three parts a provider offers (`offered_tool`), each checked, and refused with
why when it can't be one; and a call to one is put to the person by its name and its arguments
(`shown_tool_call`), since its code was approved when it loaded, not here.
"""

import json
import re
from collections.abc import Mapping, Set
from typing import Any

__all__ = ["RESERVED", "offered_tool", "shown_tool_call"]

# The shipped tool's name: never an extension's, even while the python row restarts.
RESERVED = frozenset({"python"})
# A name every provider takes, and the claude-code provider's `mcp__bh__` prefix keeps under 64.
_NAME = re.compile(r"[a-z][a-z0-9_]{0,47}")
_TYPES = frozenset({"string", "number", "integer", "boolean", "array", "object", "null"})
_MAX_DESCRIPTION = 4_000  # characters: the list of tools goes with every request
_MAX_SPEC = 16_384  # bytes of the whole spec as JSON


def offered_tool(spec: object, reserved: Set[str]) -> dict[str, Any]:
    """`spec` as bh-02 registers an extension's tool: its `name`, `description` and
    `parameters` (a JSON Schema object) and nothing else. Raises ValueError saying why it can't
    be one: a name that is not lowercase letters, digits and `_` (48 at most), or is in
    `reserved` (bh-02's own tools: the python tool's, a layer row's); a description that is not
    text, or longer than 4,000 characters; parameters that are not an object schema whose
    `properties` each have a JSON type and whose `required` names them; or a spec larger than
    16 KiB as JSON."""
    if not isinstance(spec, Mapping):
        raise ValueError("a tool's spec is a dict with `name`, `description` and `parameters`")
    name = spec.get("name")
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(
            "a tool's name is lowercase letters, digits and _, starting with a letter, 48 at most "
            f"('search_notes'); got {name!r}"
        )
    if name in reserved:
        raise ValueError(f"{name!r} is one of bh-02's own tools: give yours another name")
    description = spec.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"the tool {name!r} needs a `description`: what it does and when to call it")
    if len(description) > _MAX_DESCRIPTION:
        raise ValueError(
            f"the tool {name!r}'s description is {len(description):,} characters; keep it under "
            f"{_MAX_DESCRIPTION:,} (it goes with every request): say the rest in a prompt section"
        )
    parameters = _parameters(name, spec.get("parameters", {"type": "object", "properties": {}}))
    offered = {"name": name, "description": description, "parameters": parameters}
    try:
        size = len(json.dumps(offered).encode("utf-8"))
    except TypeError, ValueError:
        raise ValueError(
            f"the tool {name!r}'s spec is not plain JSON (dicts, lists, text, numbers)"
        ) from None
    if size > _MAX_SPEC:
        raise ValueError(
            f"the tool {name!r}'s spec is {size:,} bytes as JSON; keep it under {_MAX_SPEC:,}: "
            "fewer or plainer parameters"
        )
    loaded: dict[str, Any] = json.loads(json.dumps(offered))  # a copy of its own, plain JSON
    return loaded


def _parameters(name: str, schema: object) -> Mapping[str, Any]:
    """The tool's `parameters`, checked: an object schema, each property a schema with a JSON
    type, `required` naming properties. Raises ValueError saying which part is wrong."""
    shape = (
        f"the tool {name!r}'s `parameters` is a JSON Schema object: "
        '{"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}'
    )
    if not isinstance(schema, Mapping) or schema.get("type") != "object":
        raise ValueError(shape)
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ValueError(shape)
    for key, each in properties.items():
        kind = each.get("type") if isinstance(each, Mapping) else None
        kinds = kind if isinstance(kind, list) else [kind]
        if not isinstance(key, str) or not kinds or not all(k in _TYPES for k in kinds):
            raise ValueError(
                f"{shape}; its property {key!r} needs a `type`, one of {', '.join(sorted(_TYPES))}"
            )
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(r, str) and r in properties for r in required):
        raise ValueError(f"{shape}; `required` lists names of its properties, and has {required!r}")
    return schema


def shown_tool_call(extension: str, name: str, input: Mapping[str, Any]) -> dict[str, Any]:
    """How a call to an extension's tool is put to the person (CONTRACTS.md: tools, `show`): its
    name, whose it is, and its arguments as JSON."""
    return {
        "title": f"Run {name}, a tool of the extension {extension}, with these arguments?",
        "lines": json.dumps(dict(input), indent=2, ensure_ascii=False, default=str).splitlines(),
        "language": "json",
    }
