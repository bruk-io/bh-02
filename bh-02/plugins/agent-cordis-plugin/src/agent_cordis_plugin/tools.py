"""The `tools` value: the tools rows offer the model, a broker (paper 6.2).

A tool is a standard tool spec (`name`, `description`, `parameters`, a JSON Schema) and an async
function that runs a call: given the call's input, it returns what the model reads
(`{"content": str, "touched": [path, ...]}`, the files the call opened). A row with a tool to
offer `acquire`s `tools.register(spec, run)`, so the tool leaves with the row; the loop offers
every registered spec and runs each call through the tool its name has. CodeAct's `python` is one
registration (the python row's), not something the loop knows of.

A registration also says where its calls run (`runs`: "jail", in the runner's jail, which
`approval` decides about by whether it confines; "host", bh-02's own process, which it always puts
to the person) and how a call is put to the person (`show(input) -> {"title", "lines",
"language"}`; without one, the tool's name and its input as JSON).

The specs are given in name order (`specs`), never in the order rows registered them: a row that
registers again after a restart (the python row's, on `/clear`) gives the same list, which is the
start of what a model server caches. A name is one tool; a second registration of it raises.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from cordis_helpers import Registry

__all__ = ["HOST", "JAIL", "ToolBroker"]

type Json = Mapping[str, Any]

JAIL = "jail"  # a call runs in the runner's jail: asked about only when the runner does not confine
HOST = "host"  # a call runs in bh-02's own process: always put to the person
_WHERE = (JAIL, HOST)


@dataclass(frozen=True, slots=True)
class _Tool:
    """One registration: the spec the model is offered, the function that runs a call, where a
    call runs (`runs`) and how one is put to the person (`show`, None for the loop's own way)."""

    spec: Json
    run: Callable[[Json], Awaitable[Json]]
    runs: str = JAIL
    show: Callable[[Json], Json] | None = None


class ToolBroker:
    """Implements `tools` (CONTRACTS.md: tools)."""

    def __init__(self) -> None:
        self._tools: Registry[_Tool] = Registry("tool")
        # set when a tool comes or goes, then replaced: what `ready` waits on
        self._changed = asyncio.Event()

    def register(
        self,
        spec: Json,
        run: Callable[[Json], Awaitable[Json]],
        *,
        runs: str = JAIL,
        show: Callable[[Json], Json] | None = None,
    ) -> Callable[[], None]:
        """Offer the model a tool: `spec`, a standard tool spec named by its `name`, and `run`,
        which runs a call; returns its remover. A row `acquire`s one, so the tool leaves with it."""
        name = spec.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"a tool's spec needs a `name`, the text the model calls it by; this one has {name!r}"
            )
        if runs not in _WHERE:
            raise ValueError(
                f"the tool {name!r} says its calls run in {runs!r}; say {JAIL!r} (in the runner's "
                f"jail) or {HOST!r} (in bh-02's own process, every call put to the person)"
            )
        remove = self._tools.register(name, _Tool(spec, run, runs, show))
        self._now_changed()

        def removed() -> None:
            remove()
            self._now_changed()

        return removed

    def specs(self) -> list[Json]:
        """Every registered tool's spec, in name order: what the model is offered."""
        return [tool.spec for _, tool in sorted(self._tools, key=lambda named: named[0])]

    def get(self, name: str) -> _Tool | None:
        """The tool registered under `name`, or None."""
        return self._tools.get(name)

    async def ready(self, names: Iterable[str], timeout: float) -> tuple[str, ...]:
        """Wait up to `timeout` seconds for every one of `names` to be registered; the ones still
        missing then (empty: all are)."""
        wanted = tuple(names)
        loop = asyncio.get_running_loop()
        until = loop.time() + timeout
        while missing := tuple(name for name in wanted if name not in self._tools):
            left = until - loop.time()
            if left <= 0:
                return missing
            with contextlib.suppress(TimeoutError):  # then `left` is spent: the loop says what is missing
                await asyncio.wait_for(self._changed.wait(), left)
        return ()

    def _now_changed(self) -> None:
        self._changed.set()
        self._changed = asyncio.Event()
