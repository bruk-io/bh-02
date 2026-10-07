"""The rows: who the model is and where it is working, bound under `system`; and what the
context files say about the files an input opened, added to `memory`."""

from typing import Any

from context_cordis_plugin.project import ContextConfig, ProjectContext
from context_cordis_plugin.touch import Memory, OnTouch, System
from cordis import Effects, acquire, bind, component

__all__ = ["on_touch", "project"]


@component(provides=("system",))
async def project(*, config: ContextConfig) -> Effects:
    """Fills a `system` row: `use = "context:project"`."""
    yield bind("system", ProjectContext(config))


@component
async def on_touch(*, system: System, memory: Memory, transcript: Any) -> Effects:
    """Fills an `on-touch` row: `use = "context:on_touch"`, with no config of its own: it asks
    the `system` value (`touched`), so the context files are the ones `context:project`'s config
    names, read and searched once for the prompt and for this. After each input, what their
    sections' `on_touch` functions say about the files it opened goes to the model with its
    result, each once a conversation (`OnTouch`). It depends on `transcript` only to share its
    lifetime: a new conversation (`/clear`) starts a new row, which tells each again. A row of its
    own, not `context:project`, so a new conversation never rebinds `system` and what depends on
    it; `context:project` depends on nothing, so `system` reloads this only when its own row
    changes or restarts."""
    yield acquire(memory.add, OnTouch(system))
