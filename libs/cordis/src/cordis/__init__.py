"""cordis: composition that can be added, replaced and removed while the program runs.

A component is an async generator that yields effects. Keyword-only parameters are its
dependencies and `config` is its configuration. What it provides is what it binds. The
runtime performs every effect and every undo; the author performs neither.

    @component
    async def net(*, config: NetConfig) -> Effects:
        client = yield enter(NetClient(config.port))
        yield bind("net", client)

A Python realisation of "A Programming Paradigm for Spatiotemporal Composability"
(Shi, Zhang, Cui, arXiv:2608.25512). It knows nothing about agents, models, tools or user
interfaces; `bh-02` is one harness built on it. `cordis/README.md` is the design doc.

This namespace is what an author and a bootstrap need. The operator's vocabulary (rows,
layers, plans, the loader handle, `read_layer`, `resolve`) is `cordis.loader` and
`cordis.composition`; test helpers are `cordis.testing`. Those three modules and this one
are the public surface; the rest is internal.
"""

from cordis.authoring import component, scan
from cordis.component import Component, configure
from cordis.composition import Row
from cordis.decisions import ContractViolation, State
from cordis.effects import Effect, Effects, Key, Result, Step, Undo, effect
from cordis.inspection import Inspection
from cordis.loader import Booted, boot
from cordis.runtime import (
    AlreadyBound,
    Context,
    Event,
    Fiber,
    Performer,
    Runtime,
    acquire,
    background,
    bind,
    enter,
    observe,
    performer,
    use,
)

__all__ = [
    "AlreadyBound",
    "acquire",
    "background",
    "bind",
    "boot",
    "Booted",
    "Component",
    "component",
    "configure",
    "Context",
    "ContractViolation",
    "Effect",
    "effect",
    "Effects",
    "enter",
    "Event",
    "Fiber",
    "Inspection",
    "Key",
    "observe",
    "Performer",
    "performer",
    "Result",
    "Row",
    "Runtime",
    "scan",
    "State",
    "Step",
    "Undo",
    "use",
]
