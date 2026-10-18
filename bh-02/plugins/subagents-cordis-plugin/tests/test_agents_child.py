"""A sub-agent as data: its name, its rows, its label and its report, as functions."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

import pytest

from subagents_cordis_plugin import (
    GENERAL,
    AgentsConfig,
    AgentType,
    Asker,
    Labelled,
    Report,
    agents_dir,
    background_flag,
    child_rows,
    framed,
    labelled,
    next_name,
    report_of,
    timeout_seconds,
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
    _Entry("memory", "memory:files", {"root": "/p"}),
    _Entry("chat", "chat:converse"),
]
_KEPT = ("loop", "tools", "transcript", "model", "python")


_PLACE = PurePath("/s/abc/agents/general-1")


def _rows(kind: AgentType = GENERAL, place: PurePath | None = _PLACE, kept: Any = _KEPT) -> Any:
    return child_rows(
        _PARENT,
        name="general-1",
        kind=kind,
        kept=kept,
        tools=("python",),
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
        ("agents/general-1/output", "subagents:output"),
        ("agents/general-1/agent", "subagents:child"),
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


def test_the_report_is_the_last_step_s_text_its_stop_and_the_usage_summed() -> None:
    events = [
        {"type": "text", "text": "Let me look."},
        {"type": "tool_call", "id": "1", "name": "python", "input": {}},
        {"type": "usage", "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.01},
        {"type": "tool_result", "call_id": "1", "content": "3", "is_error": False},
        {"type": "stop", "reason": "silent"},  # fed back: what follows is a new step
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
    assert unknown_type("nosuch", ["general", "explore"]) == (
        "error: there is no agent type 'nosuch'; the types are explore, general"
    )


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
    uses `subagents:parent`, is refused saying what to do; it never reaches a child."""
    parent = [*_PARENT, _Entry("agents", "subagents:parent"), _Entry("helpers", "subagents:parent")]
    for named in ("agents", "helpers"):
        with pytest.raises(
            ValueError, match=r"a child has no agents row \(depth one, decision-0002\)"
        ) as why:
            child_rows(
                parent,
                name="general-1",
                kind=GENERAL,
                kept=(*_KEPT, named),
                tools=("python",),
                transcript_row="transcript",
                model_row="model",
                place=_PLACE,
                hand="the hand",
            )
        assert repr(named) in str(why.value) and "take it out of `rows`" in str(why.value)


# the shipped layer's rows that give a conversation the project's guidance (bh-02.toml)
_GUIDED = (*_KEPT, "memory", "on-touch")
_SHIPPED = [
    *_PARENT,
    _Entry("on-touch", "memory:on_touch"),
    _Entry("memory-auto", "memory:auto"),
    _Entry("commands", "commands:registry"),
]


def _guided(kept: Any = _GUIDED, parent: Any = _SHIPPED) -> Any:
    return child_rows(
        parent,
        name="general-1",
        kind=GENERAL,
        kept=kept,
        tools=("python",),
        transcript_row="transcript",
        model_row="model",
        place=_PLACE,
        hand="the hand",
    )


def test_a_child_with_the_memory_row_gets_a_commands_registry_of_its_own_beside_it() -> None:
    """`memory:files` needs `commands`, which a sealed realm does not read from outside: the
    child's rows gain a `commands:registry`, its own, and the memory rows are the parent's copied."""
    rows = _guided()
    assert [(r.id, r.use) for r in rows if "memory" in r.use or "commands" in r.use] == [
        ("agents/general-1/memory", "memory:files"),
        ("agents/general-1/on-touch", "memory:on_touch"),
        ("agents/general-1/commands", "commands:registry"),
    ]
    by_id = {r.id: r.config for r in rows}
    assert by_id["agents/general-1/memory"] == {"root": "/p"}  # the parent's config, for what it reads
    assert by_id["agents/general-1/commands"] == {}


def test_a_child_with_no_memory_row_has_no_commands_registry() -> None:
    rows = _guided(kept=_KEPT)
    assert not any(r.use == "commands:registry" for r in rows)
    rows = _guided(parent=[e for e in _SHIPPED if e.id != "memory"])  # a layer with no memory plugin
    assert not any(r.use in ("memory:files", "commands:registry") for r in rows)


def test_a_commands_row_the_layer_gave_the_child_is_the_only_one() -> None:
    """A layer's `rows` that names the commands row already gives the child a registry of its own
    (a copy, mounted in its realm): a second would bind the key twice."""
    rows = _guided(kept=(*_GUIDED, "commands"))
    assert [r.id for r in rows if r.use == "commands:registry"] == ["agents/general-1/commands"]


def test_the_default_rows_give_a_child_the_guidance_and_never_auto_memory() -> None:
    """The shipped layer's child has `memory:files` and `memory:on_touch`; the rows a child is made
    of by default name no auto memory row, so none is copied."""
    kept = AgentsConfig().rows
    assert "memory" in kept and "on-touch" in kept and "memory-auto" not in kept
    uses = [r.use for r in _guided(kept=kept)]
    assert "memory:files" in uses and "memory:on_touch" in uses and "commands:registry" in uses
    assert "memory:auto" not in uses


def test_a_child_never_gets_auto_memory_whatever_the_layer_names() -> None:
    """N children writing one auto memory directory would race the parent (decision-0002): naming
    the auto memory row in `rows`, by its id or as any row that uses `memory:auto`, is refused
    saying what to do; it never reaches a child. A disabled one is not mounted, so naming it is
    no error."""
    parent = [*_SHIPPED, _Entry("remembering", "memory:auto")]
    for named in ("memory-auto", "remembering"):
        with pytest.raises(ValueError, match=r"a child has no auto memory \(decision-0002: ") as why:
            _guided(kept=(*_GUIDED, named), parent=parent)
        assert repr(named) in str(why.value) and "take it out of `rows`" in str(why.value)
    off = [
        e if e.id != "memory-auto" else _Entry("memory-auto", "memory:auto", disabled=True) for e in _SHIPPED
    ]
    assert not any(r.use == "memory:auto" for r in _guided(kept=(*_GUIDED, "memory-auto"), parent=off))


@pytest.mark.parametrize("value", ["true", "false", "", 1, 0, None, [True], {}])
def test_a_background_that_is_not_a_boolean_is_refused_saying_what_to_pass(value: object) -> None:
    """Only true and false are an answer: a truthy "true" is not a yes, and none is taken for
    the foreground with no word."""
    said = background_flag(value)
    assert isinstance(said, str)
    assert said.startswith(f"error: the agent tool's `background` is {value!r}, not a boolean")
    assert "pass true to have its name back at once" in said and "so no agent was started" in said


def test_a_boolean_background_is_taken_as_it_is() -> None:
    assert background_flag(True) is True and background_flag(False) is False


@pytest.mark.parametrize(
    ("value", "seconds"), [(None, None), (5, 5.0), (0.5, 0.5), (0, 0.0), (-3, 0.0), (2**70, float(2**70))]
)
def test_agent_wait_takes_a_number_of_seconds_or_none(value: object, seconds: float | None) -> None:
    assert timeout_seconds(value) == seconds


@pytest.mark.parametrize(
    "value", ["soon", "30", "", True, False, [1], {}, float("nan"), float("inf"), 10**400]
)
def test_a_timeout_that_is_no_number_is_refused_saying_what_to_give(value: object) -> None:
    said = timeout_seconds(value)
    assert isinstance(said, str)
    assert said.startswith(f"error: agent_wait's `timeout` is {value!r}, not a number of seconds")
    assert "such as timeout=30" in said and "leave it out to wait until all" in said
