"""What an extension's tool spec must be for bh-02 to offer it, and how a call to one is shown."""

from typing import Any

import pytest

from extensions_cordis_plugin import offered_tool, shown_tool_call

_SPEC: dict[str, Any] = {
    "name": "search_notes",
    "description": "Search the project's notes.",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": ["integer", "null"]}},
        "required": ["query"],
    },
}


def test_a_spec_is_rebuilt_from_its_three_parts_and_nothing_else() -> None:
    offered = offered_tool({**_SPEC, "run": "not offered", "cache_control": {}}, frozenset())
    assert offered == _SPEC and offered is not _SPEC
    assert offered["parameters"] is not _SPEC["parameters"]  # a copy of its own
    bare = offered_tool({"name": "now", "description": "The time."}, frozenset())
    assert bare["parameters"] == {"type": "object", "properties": {}}  # no arguments


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"name": "Search"}, "a tool's name is lowercase letters, digits and _"),
        ({"name": "search-notes"}, "a tool's name is lowercase letters, digits and _"),
        ({"name": "x" * 49}, "48 at most"),
        ({"name": "python"}, "'python' is one of bh-02's own tools: give yours another name"),
        ({"description": ""}, "needs a `description`"),
        ({"description": "x" * 4_001}, "keep it under 4,000"),
        ({"parameters": {"type": "array"}}, "is a JSON Schema object"),
        ({"parameters": {"type": "object", "properties": {"q": {}}}}, "its property 'q' needs a `type`"),
        ({"parameters": {"type": "object", "properties": {"q": {"type": "text"}}}}, "needs a `type`"),
        (
            {"parameters": {**_SPEC["parameters"], "required": ["q"]}},
            "`required` lists names of its properties",
        ),
        ({"parameters": {**_SPEC["parameters"], "default": object()}}, "is not plain JSON"),
    ],
)
def test_a_spec_bh_02_cannot_offer_is_refused_saying_why(change: dict[str, Any], said: str) -> None:
    with pytest.raises(ValueError) as refused:
        offered_tool({**_SPEC, **change}, frozenset({"python"}))
    assert said in str(refused.value)


def test_a_name_a_row_of_bh_02_s_own_registered_is_refused_and_a_large_spec_too() -> None:
    with pytest.raises(ValueError, match="'search_notes' is one of bh-02's own tools"):
        offered_tool(_SPEC, frozenset({"search_notes"}))
    many = {f"p{n}": {"type": "string", "description": "x" * 200} for n in range(100)}
    with pytest.raises(ValueError, match=r"spec is [\d,]+ bytes as JSON; keep it under 16,384"):
        offered_tool({**_SPEC, "parameters": {"type": "object", "properties": many}}, frozenset())
    with pytest.raises(ValueError, match="a tool's spec is a dict"):
        offered_tool(["search_notes"], frozenset())


def test_a_call_is_shown_by_its_name_whose_it_is_and_its_arguments() -> None:
    assert shown_tool_call("notes", "search_notes", {"query": "café", "limit": 3}) == {
        "title": "Run search_notes, a tool of the extension notes, with these arguments?",
        "lines": ["{", '  "query": "café",', '  "limit": 3', "}"],
        "language": "json",
    }
