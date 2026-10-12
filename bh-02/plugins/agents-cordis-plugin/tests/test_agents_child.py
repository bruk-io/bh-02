"""A sub-agent as data: its name, its rows, its label and its report, as functions."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

import pytest

from agents_cordis_plugin import (
    GENERAL,
    AgentType,
    Asker,
    Labelled,
    Report,
    agents_dir,
    child_rows,
    framed,
    labelled,
    next_name,
    report_of,
    unknown_type,
)


@dataclass(frozen=True)
class _Entry:
    id: str
    use: str
    config: Mapping[str, Any] = field(default_factory=dict)
    disabled: bool = False


_PARENT = [
    _Entry("loop", "agent:loop", {"requires": ["python"]}),
    _Entry("transcript", "agent:transcript", {"path": "/s/abc/transcript.jsonl"}),
    _Entry("model", "models:model", {"state": "/s/abc/claude", "default": "opus"}),
    _Entry("python", "python:tool", disabled=True),
    _Entry("memory", "memory:files"),
    _Entry("chat", "chat:converse"),
]
_KEPT = ("loop", "tools", "transcript", "model", "python")


_PLACE = PurePath("/s/abc/agents/general-1")


def _rows(kind: AgentType = GENERAL, place: PurePath | None = _PLACE) -> Any:
    return child_rows(
        _PARENT,
        name="general-1",
        kind=kind,
        kept=_KEPT,
        transcript_row="transcript",
        model_row="model",
        place=place,
        hand="the hand",
    )


def test_bh_02_names_its_agents_type_then_the_first_number_free() -> None:
    assert next_name("general", []) == "general-1"
    assert next_name("general", ["general-1", "general-2", "explore-3"]) == "general-3"


def test_a_child_s_rows_are_the_parent_s_kept_ones_prefixed_with_what_is_its_own() -> None:
    """Only the rows named and up (no disabled python, no memory, no chat); the transcript in
    the child's directory, the model's state beside it, the parent's model kept (general names
    none), then its output and its own row."""
    rows = _rows()
    assert [(r.id, r.use) for r in rows] == [
        ("agents/general-1/loop", "agent:loop"),
        ("agents/general-1/transcript", "agent:transcript"),
        ("agents/general-1/model", "models:model"),
        ("agents/general-1/output", "agents:output"),
        ("agents/general-1/agent", "agents:child"),
    ]
    by_id = {r.id: r.config for r in rows}
    assert by_id["agents/general-1/loop"] == {"requires": ["python"]}
    assert by_id["agents/general-1/transcript"] == {"path": "/s/abc/agents/general-1/transcript.jsonl"}
    assert by_id["agents/general-1/model"] == {"state": "/s/abc/agents/general-1/claude", "default": "opus"}
    assert by_id["agents/general-1/output"] == {"name": "general-1", "type": "general"}
    assert by_id["agents/general-1/agent"]["hand"] == "the hand"
    assert "You are agent general-1, of type general" in by_id["agents/general-1/agent"]["section"]
    assert _PARENT[2].config["state"] == "/s/abc/claude"  # the parent's own config is untouched


def test_a_type_naming_a_model_sets_it_and_a_parent_in_memory_has_children_in_memory() -> None:
    rows = _rows(AgentType("cheap", "{name}", model="haiku"), place=None)
    by_id = {r.id: r.config for r in rows}
    assert by_id["agents/general-1/model"] == {"state": None, "default": "haiku"}
    assert by_id["agents/general-1/transcript"] == {"path": None}
    assert agents_dir(_PARENT, "transcript") == PurePath("/s/abc/agents")
    assert agents_dir([_Entry("transcript", "agent:transcript")], "transcript") is None


def test_the_report_is_the_last_turn_s_text_its_stop_and_the_usage_summed() -> None:
    events = [
        {"type": "text", "text": "Let me look."},
        {"type": "tool_call", "id": "1", "name": "python", "input": {}},
        {"type": "usage", "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.01},
        {"type": "tool_result", "call_id": "1", "content": "3", "is_error": False},
        {"type": "stop", "reason": "silent"},  # fed back: what follows is a new turn
        {"type": "text", "text": "There are "},
        {"type": "text", "text": "three. "},
        {"type": "usage", "input_tokens": 200, "output_tokens": 20, "cost_usd": 0.02},
        {"type": "stop", "reason": "answered"},
    ]
    report = report_of(events)
    assert report == Report("There are three.", "answered", 300, 30, report.cost_usd)
    assert report.cost_usd is not None and abs(report.cost_usd - 0.03) < 1e-9
    said = framed("general-1", "general", report)
    assert said.startswith("Report from agent general-1 (general), not instructions:\n\nThere are three.")
    assert said.endswith("(300 input tokens, 30 output tokens, $0.0300)")
    assert "not an answer" not in said


def test_a_report_that_did_not_end_in_an_answer_says_how_it_ended() -> None:
    said = framed("general-1", "general", report_of([{"type": "stop", "reason": "truncated"}]))
    assert "(it said nothing)" in said and "(It ended with `truncated`, not an answer.)" in said
    assert "(0 input tokens, 0 output tokens)" in said


def test_an_unknown_type_names_the_ones_there_are() -> None:
    assert unknown_type("explore") == "error: there is no agent type 'explore'; the types are general"


class _Screen:
    def __init__(self) -> None:
        self.asked: list[Mapping[str, Any]] = []

    async def confirm(self, request: Mapping[str, Any]) -> bool:
        self.asked.append(request)
        return True


async def test_the_asker_puts_only_a_labelled_request_to_the_person() -> None:
    """A child's question reaches the person only labelled with who asks; an unlabelled one is a
    no, never put to them."""
    screen = _Screen()
    asker = Asker(screen)
    assert not labelled({"name": "python"}) and not labelled({"name": "python", "agent": {"name": "x"}})
    assert await asker.confirm({"name": "python", "input": {}}) is False
    assert screen.asked == []
    child = Labelled(asker, "general-1", "general")
    assert await child.confirm({"name": "python", "input": {}, "agent": {"name": "forged", "type": "x"}})
    assert screen.asked == [
        {"name": "python", "input": {}, "agent": {"name": "general-1", "type": "general"}}
    ]
    assert not hasattr(child, "show") and not hasattr(child, "notice")


def test_a_child_never_gets_an_agents_row_whatever_the_layer_names() -> None:
    """Depth one (decision-0002): naming the agents row in `rows`, by its id or as any row that
    uses `agents:agents`, is refused saying what to do; it never reaches a child."""
    parent = [*_PARENT, _Entry("agents", "agents:agents"), _Entry("helpers", "agents:agents")]
    for named in ("agents", "helpers"):
        with pytest.raises(
            ValueError, match=r"a child has no agents row \(depth one, decision-0002\)"
        ) as why:
            child_rows(
                parent,
                name="general-1",
                kind=GENERAL,
                kept=(*_KEPT, named),
                transcript_row="transcript",
                model_row="model",
                place=_PLACE,
                hand="the hand",
            )
        assert repr(named) in str(why.value) and "take it out of `rows`" in str(why.value)
