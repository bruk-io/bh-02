"""The rows: `agents`, outside, which binds `asker` and registers the `agent` tool, each call
mounting a child in a sealed realm through its performer; and, inside each child's realm,
`output` (the child's, over `asker`) and `child` (its type's section of the prompt, and its loop
passed to the run that mounted it).

A child is `use(cordis.loader:loader, config=LoaderConfig(overrides=rows, watch=None),
expose={runner, approval, host, asker})`: the realm's own loader resolves its rows by name, so
this plugin imports no other, and the realm reads nothing from outside but those four keys.
Every other key it binds (`loop`, `tools`, `transcript`, `model`, ...) is its own. The performer's
undo for each mount is the child's retirement, so the agents row unloading retires every child
it still holds.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, runtime_checkable

import cordis.loader
from agents_cordis_plugin.agents import (
    AGENT,
    SECTION,
    Agents,
    AgentsConfig,
    Asker,
    Confirm,
    Hand,
    Labelled,
    Loop,
    Rows,
)
from agents_cordis_plugin.child import ChildRow, prefixed
from cordis import Effects, Fiber, Inspection, Performer, Row, acquire, bind, component, performer, use

__all__ = ["ChildConfig", "OutputConfig", "agents", "child", "output"]

# What a child's realm reads from outside (decision-0002): its python tool's runner, the one
# approval rule, what the jail keeps from the model, and the asker over the parent's output.
_EXPOSED = ("runner", "approval", "host", "asker")


@runtime_checkable
class _Registrar(Protocol):
    """What the agents row needs of the `tools` value (CONTRACTS.md: tools): a tool registered,
    and its remover back."""

    def register(
        self,
        spec: Mapping[str, Any],
        run: Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]],
        *,
        runs: str = ...,
        show: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = ...,
    ) -> Callable[[], None]: ...


@runtime_checkable
class _Sections(Protocol):
    """What a row adding to the prompt needs of the `system` value (CONTRACTS.md: system)."""

    def add(self, name: str, section: Callable[[], str]) -> Callable[[], None]: ...


@dataclass(frozen=True, slots=True)
class _Child:
    """A mounted child: its realm's fiber, retired to end it, and read (through cordis's
    `Inspection`) to say why it never came up."""

    fiber: Fiber

    async def retire(self) -> None:
        await self.fiber.retire()

    def stalled(self) -> str:
        """Each of its rows that is not up, and why: its loader's own words, and what an
        inactive one waits on."""
        seen = Inspection(self.fiber.ctx.runtime)
        handle = self.fiber.ctx.get("loader")  # the realm's own loader, bound inside it
        status: Mapping[str, str] = handle.status() if handle is not None else {}
        said = []
        for rid, state in status.items():
            if state == "active":
                continue
            fiber = seen.fiber(rid)
            waits = seen.waiting_on(fiber) if fiber is not None and state == "inactive" else []
            said.append(f"{rid} {state}" + (f", waiting on {', '.join(map(str, waits))}" if waits else ""))
        return "; ".join(said)


async def _mount(host: Performer, name: str, rows: Sequence[ChildRow]) -> _Child:
    """Mount child `name` under the agents row's fiber: a sealed realm, its own loader over `rows`."""
    config = cordis.loader.LoaderConfig(
        overrides=tuple(Row(row.id, row.use, row.config) for row in rows), watch=None
    )
    return _Child(
        await host.perform(use(cordis.loader.loader, config=config, expose=_EXPOSED, id=prefixed(name)))
    )


@component(provides=("asker",))
async def agents(
    *, tools: _Registrar, system: _Sections, output: Confirm, loader: Rows, config: AgentsConfig
) -> Effects:
    """Fills an `agents` row: `use = "agents:agents"`. Binds `asker` (a confirm-only view of the
    parent's `output`, for its children), registers the `agent` tool (`runs="harness"`: bh-02's
    own, unasked exactly when the runner confines) and tells the model of it in the `system`
    section `agents`. Each call mounts one child through this row's performer, from the rows
    the parent's loader mounted (`loader.rows`, as `config.rows` names them), drives its reply
    and retires it; unloading this row retires every child still up."""
    host: Performer = yield performer()
    yield bind("asker", Asker(output))
    run = Agents(loader, partial(_mount, host), config)
    yield acquire(tools.register, AGENT, run.agent, runs="harness")
    yield acquire(system.add, "agents", lambda: SECTION)


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """`agents:output`'s config, written by the agents row: the agent's name and type."""

    name: str
    type: str


@component(provides=("output",))
async def output(*, asker: Confirm, config: OutputConfig) -> Effects:
    """Fills a child's `output` row (`use = "agents:output"`, inside its realm): its loop's
    `confirm` through `asker`, labelled with the agent's name and type. Nothing else."""
    yield bind("output", Labelled(asker, config.name, config.type))


@dataclass(frozen=True, slots=True)
class ChildConfig:
    """`agents:child`'s config, written by the agents row: where its loop is passed (`hand`) and
    its type's section of the prompt."""

    hand: Hand
    section: str


@component
async def child(*, loop: Loop, system: _Sections, config: ChildConfig) -> Effects:
    """A child's own row (`use = "agents:child"`, inside its realm): adds its type's section to
    its prompt (`agent`) and passes its loop to the run that mounted it; leaving says it is gone."""
    yield acquire(system.add, "agent", lambda: config.section)
    yield acquire(config.hand.give, loop)
