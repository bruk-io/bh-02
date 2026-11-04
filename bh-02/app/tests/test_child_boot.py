"""A sub-agent of the shipped layer comes up, and the fields the agents row reads of other plugins'
rows are the ones those plugins have (CONTRACTS.md: Fields one plugin reads or rewrites in another's row).

The agents row keeps its child's rows in bh-02.toml, beside the rows it names, because the loop's
`requires` and what contributes to its brokers (`python`, `memory`, `on-touch`) are not injections
the loop declares; these tests are what notices the list falling behind the loop."""

import asyncio
import dataclasses
import re
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

from bh_02 import layers, run
from cordis import Effects, Row, bind, component
from cordis.loader import read_layer, resolve
from subagents_cordis_plugin import ALWAYS_REFUSED, GENERAL, child_rows

# What a child's realm reads from outside (the agents row's `expose`), and the key it binds itself
# in place of the parent's (`subagents:output`): none of their rows is copied.
_OUTSIDE = {"runner", "approval", "host", "asker", "grants", "output"}
_WITHHELD = {"agents", "memory-auto"}  # decision-0002: depth one, and N writers to one directory


def _shipped() -> dict[str, Row]:
    rows: dict[str, Row] = {}
    for layer in layers():
        for row in read_layer(str(layer)):
            rows[row.id] = row if row.use else Row(row.id, rows[row.id].use, row.config)
    return rows


def _loop_needs(rows: Mapping[str, Row]) -> set[str]:
    """The rows `loop` depends on, through the keys its component injects and those theirs inject,
    and the tool rows its `requires` waits for (a tool's row is named for it), minus what the realm
    reads from outside or binds itself."""
    declared = {rid: resolve(row.use or "") for rid, row in rows.items() if not row.disabled}
    pending = ["loop", *rows["loop"].config["requires"]]
    needs = set(pending)
    while pending:
        for key in sorted(declared[pending.pop()].inject - _OUTSIDE):
            for rid, component_ in declared.items():
                if key in component_.provides and rid not in needs:
                    needs.add(rid)
                    pending.append(rid)
    return needs


def test_the_agents_row_names_every_row_the_loop_depends_on_and_never_the_agents_row_or_auto_memory() -> None:
    rows = _shipped()
    named = set(rows["agents"].config["rows"])
    assert _loop_needs(rows) - named == set()
    assert named & _WITHHELD == set()
    assert named <= set(rows)  # every name is a row of the layer


class _Child:
    """A model that, asked by the parent, starts a child and says what the child's report was; asked
    by the child (it has no `agent` tool), says what it was offered; the parent then repeats the report."""

    async def complete(self, messages: Any, tools: Any) -> AsyncIterator[dict[str, Any]]:
        offered = sorted(spec["name"] for spec in tools)
        if "agent" not in offered:
            yield {"type": "text", "text": "up with " + ", ".join(offered)}
            yield {"type": "stop", "reason": "end_turn"}
            return
        results = [m["content"] for m in messages if m["role"] == "tool"]
        if not results:
            call = {"prompt": "report", "type": "general"}
            yield {"type": "tool_call", "id": "a1", "name": "agent", "input": call}
            yield {"type": "stop", "reason": "tool_use"}
            return
        yield {"type": "text", "text": str(results[-1])}
        yield {"type": "stop", "reason": "end_turn"}


@component(provides=("model",))
async def child_model() -> Effects:
    yield bind("model", _Child())


async def test_a_child_of_the_shipped_layer_comes_up_with_every_row_the_loop_depends_on(
    composition: Callable[..., Path],
) -> None:
    """The real loop, tools, transcript, system, asides, executor, python tool, memory and
    on-touch rows, in a sealed realm: the child's loop starts (its `requires` is met) well inside
    the start time, and the tools it is offered are the parent's but for the agents row's."""
    shipped = _shipped()
    needs = _loop_needs(shipped)
    kept = shipped["agents"].config["rows"]  # a patch's config replaces the layer's, whole
    patch = composition(
        f'[[plugin]]\nid = "model"\nuse = "{__name__}:child_model"\n'
        '[[plugin]]\nid = "agents"\nuse = "subagents:parent"\ndisabled = false\n'
        f"config = {{ start = 10, rows = {kept!r} }}\n"
        '[[plugin]]\nid = "agents-status"\nuse = "subagents:status"\ndisabled = false\n',
        one_reply=True,
    )
    import fragile  # the module the fixture wrote

    fragile.answers(True, True)  # unconfined: the agent call is put to the person
    await asyncio.wait_for(run([*layers(), patch], [Row("chat", config={"prompt": "go"})]), 30)
    report = fragile.shown()  # the parent's last step says the child's report
    assert report.startswith("Report from agent general-1 (general), not instructions:")
    assert "up with python" in report  # the only tool the shipped child is offered
    assert {"loop", "python"} <= needs  # the rows that test relied on


# The fields of the rows the agents row copies that it reads or rewrites, by component.
_FIELDS = {"agent:transcript": ("path",), "models:model": ("default", "state")}


def test_the_fields_the_agents_row_reads_or_rewrites_exist_and_contracts_md_lists_them() -> None:
    rows = _shipped()
    contracts = (Path(__file__).parents[2] / "CONTRACTS.md").read_text()
    section = contracts.split("## Fields one plugin reads or rewrites in another's row")[1].split("\n## ")[0]
    assert {rid for rid, row in rows.items() if row.use in _FIELDS} >= {"transcript", "model"}
    for use, names in _FIELDS.items():
        config_type = resolve(use).config_type
        assert config_type is not None and dataclasses.is_dataclass(config_type)
        have = {f.name for f in dataclasses.fields(config_type)}
        for name in names:
            assert name in have, f"{use} has no config field {name!r}: the agents row reads or rewrites it"
            assert re.search(rf"\(`{re.escape(use)}`\) \| `{name}` \|", section), (
                f"CONTRACTS.md: {use} {name}"
            )


def test_the_agents_row_rewrites_those_fields_of_the_shipped_rows() -> None:
    """Through `child_rows` with the shipped layer's own rows: the child's transcript and model
    rows differ from the parent's in exactly the fields CONTRACTS.md lists."""
    rows = _shipped()
    parent = [
        dataclasses.replace(
            row,
            config={**(row.config or {}), **{"path": "/s/transcript.jsonl"}}
            if rid == "transcript"
            else {**(row.config or {}), "state": "/s/claude", "default": "claude/opus"}
            if rid == "model"
            else row.config,
        )
        for rid, row in rows.items()
    ]
    made = child_rows(
        [
            type("E", (), {"id": r.id, "use": r.use, "config": r.config or {}, "disabled": False})
            for r in parent
        ],
        name="general-1",
        kind=dataclasses.replace(GENERAL, model="claude/haiku"),
        kept=rows["agents"].config["rows"],
        tools=("python",),
        transcript_row="transcript",
        model_row="model",
        place=Path("/s/agents/general-1"),  # type: ignore[arg-type]
        hand=None,
        commands_row=rows["agents"].config["commands_row"],
        python_row="python",
        refused=tuple(dict.fromkeys((*ALWAYS_REFUSED, *rows["agents"].config.get("refused", ())))),
        wants_commands=lambda use: "commands" in resolve(use).inject,
    )
    by_id = {r.id: dict(r.config) for r in made}
    assert by_id["agents/general-1/commands"] == {}  # a registry of its own
    assert by_id["agents/general-1/transcript"]["path"] == "/s/agents/general-1/transcript.jsonl"
    # its needs and the refusals of its program are asked as the agent
    assert by_id["agents/general-1/python"]["agent"] == "general-1 (general)"
    assert by_id["agents/general-1/model"] == {
        **{k: v for k, v in (rows["model"].config or {}).items()},
        "state": "/s/agents/general-1/claude",
        "default": "claude/haiku",
    }
