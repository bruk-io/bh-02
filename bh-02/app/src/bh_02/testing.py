"""Rows a `--patch` layer names to launch the real app with no credential: fake models.

A shell module (the gate's `cordis-in-wiring-only` lists it), so it may know cordis without
putting test rows into a plugin. Most bind `loop` (CONTRACTS.md), replacing the whole loop:

    [[plugin]]
    id = "loop"
    use = "bh_02.testing:echo"

`echo_model`, `slow_model` and `repl_model` bind `model` instead, so the shipped loop, its
transcript and the session's own layer (`/clear`, a resume) run as they do with Claude, only
the one turn being fake. Each takes whatever `config` the row already had, since a patch that
only names `use` keeps it (the session layer gives `model` a `state`).

`echo_provider`, `slow_provider` and `repl_provider` are providers, not rows: a models file
names one for a model of its own (`provider = "bh_02.testing:echo_provider"`), so `/model`
switches between it and any other model under the shipped `models:model` row, as it would
between Claude and an OpenAI model.
"""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from cordis import Effects, bind, component

__all__ = [
    "bomb",
    "repl_model",
    "repl_provider",
    "echo",
    "echo_model",
    "echo_provider",
    "showcase",
    "slow_model",
    "slow_provider",
    "slow_start",
]


class _Echo:
    """Replies `echo:` and the message upper-cased, a word at a time (so it streams)."""

    async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "text", "text": "echo:"}
        for word in message.upper().split():
            yield {"type": "text", "text": f" {word}"}


@component(provides=("loop",))
async def echo(*, config: Mapping[str, Any] | None = None) -> Effects:
    """A model that shouts back: `use = "bh_02.testing:echo"`."""
    yield bind("loop", _Echo())


_SLOW_START_S = 3.0


@component(provides=("loop",))
async def slow_start(*, config: Mapping[str, Any] | None = None) -> Effects:
    """`echo`, taking a few seconds to start every time, as a slow model row would:
    `use = "bh_02.testing:slow_start"`. A `/clear` restarts it, so a real screen shows what
    bh-02 says while the model row is coming back up."""
    await asyncio.sleep(_SLOW_START_S)
    yield bind("loop", _Echo())


_CHANGED = "(End of what changed.)\n\n"  # how the loop's aside on changed instructions ends


def _words(message: Mapping[str, Any]) -> str:
    """What the person typed, from a user entry: its content without what `agent:loop` puts
    first, the date on an entry that carries `today` and an aside that the model's instructions
    changed (CONTRACTS.md: message)."""
    content = str(message.get("content") or "")
    content = content.partition("\n\n")[2] if message.get("today") else content
    return (
        content.partition(_CHANGED)[2] if content.startswith("(bh-02: ") and _CHANGED in content else content
    )


class _EchoModel:
    """One turn: `echo:` and the last user message upper-cased, a word at a time, then which
    user message of the conversation it was (`(message 2)`), so a screen shows whether the
    transcript was kept, forgotten (`/clear`) or restored (a resume). `name`, when given, is
    said first (`[fake]`), so a screen shows which model answered."""

    def __init__(self, name: str = "") -> None:
        self._name = name

    async def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]:
        said = [m for m in messages if m.get("role") == "user" and not m.get("feedback")]
        if self._name:
            yield {"type": "text", "text": f"[{self._name}] "}
        yield {"type": "text", "text": "echo:"}
        for word in (_words(said[-1]) if said else "").upper().split():
            yield {"type": "text", "text": f" {word}"}
        yield {"type": "text", "text": f" (message {len(said)})"}
        yield {"type": "stop", "reason": "end_turn"}


@component(provides=("model",))
async def echo_model(*, config: Mapping[str, Any] | None = None) -> Effects:
    """A model that shouts back, under the shipped loop: `id = "model"`, `use =
    "bh_02.testing:echo_model"`."""
    yield bind("model", _EchoModel())


@component(provides=("model",))
async def slow_model(*, config: Mapping[str, Any] | None = None) -> Effects:
    """`echo_model`, taking a few seconds to start every time: `/clear` restarts it, so a real
    screen shows what bh-02 says while the model is coming back up."""
    await asyncio.sleep(_SLOW_START_S)
    yield bind("model", _EchoModel())


def echo_provider(table: Mapping[str, Any]) -> _EchoModel:
    """A provider a models file names (`provider = "bh_02.testing:echo_provider"`): the echo
    model, saying the model's `id` first, so a screen shows which model answered."""
    return _EchoModel(str(table.get("id") or "echo"))


class _SlowStart:
    """The echo model, taking a few seconds to come up each time the model row enters it."""

    def __init__(self, name: str) -> None:
        self._model = _EchoModel(name)

    async def __aenter__(self) -> _EchoModel:
        await asyncio.sleep(_SLOW_START_S)
        return self._model

    async def __aexit__(self, *exc: object) -> None:
        return None


def slow_provider(table: Mapping[str, Any]) -> _SlowStart:
    """`echo_provider`, taking a few seconds to start every time: `/model` to it (and `/clear`)
    restarts the model row, so a real screen shows what bh-02 says while it comes back up."""
    return _SlowStart(str(table.get("id") or "slow"))


class _Repl:
    """Each message the person sends is one call of the offered tool, `python`, with the message
    as its code; once the input has answered, the turn says what it printed."""

    async def complete(
        self, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]:
        last = messages[-1]
        if last.get("role") == "tool":
            yield {"type": "text", "text": f"the input said: {str(last['content']).strip()}"}
            yield {"type": "stop", "reason": "end_turn"}
            return
        code = _words(last)
        yield {
            "type": "tool_call",
            "id": f"input{len(messages)}",
            "name": tools[0]["name"],
            "input": {"code": code},
        }
        yield {"type": "stop", "reason": "tool_use"}


def repl_provider(table: Mapping[str, Any]) -> _Repl:
    """A provider a models file names: `repl_model`'s model, every message a python input."""
    return _Repl()


@component(provides=("model",))
async def repl_model(*, config: Mapping[str, Any] | None = None) -> Effects:
    """A model whose every message is a python input, under the shipped loop: `id = "model"`,
    `use = "bh_02.testing:repl_model"`. Exercises the loop, the Python process, the jail and
    (unconfined, `--no-jail`) the approval modal on the real screen."""
    yield bind("model", _Repl())


_DIFF = (
    "--- a/greet.py\n+++ b/greet.py\n@@ -1,2 +1,2 @@\n def greet():\n-    return 'hi'\n+    return 'hello'"
)


class _Showcase:
    """Replies with one of every kind of event the transcript draws, so a real screen shows
    them all; `lines N` streams N numbered lines instead, a few words at a time and all at
    once (a burst: the reply never waits); `slow N` streams N lines paced like a model's,
    one every 50 ms, so a Ctrl-C can land mid-reply."""

    async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
        words = message.split()
        count = int(words[1]) if len(words) == 2 and words[1].isdigit() else None
        if words[:1] == ["lines"] and count is not None:
            for n in range(count):
                yield {"type": "text", "text": f"line {n} "}
                yield {"type": "text", "text": "of the **long** reply\n"}
            return
        if words[:1] == ["slow"] and count is not None:
            for n in range(count):
                await asyncio.sleep(0.05)
                yield {"type": "text", "text": f"slow {n}\n"}
            return
        yield {"type": "thinking", "text": "The person wants a tour.\n"}
        yield {"type": "thinking", "text": "Show every kind of event."}
        yield {"type": "text", "text": "## A tour\nFirst a `input`, then a **diff**:\n"}
        yield {"type": "text", "text": "```python\nfor n in range(3):\n    print(n)\n```\n"}
        call = {"id": "t1", "name": "python", "input": {"code": "import this  # " + "long " * 30}}
        yield {"type": "tool_call", **call}
        yield {"type": "tool_result", "call_id": "t1", "content": _DIFF, "is_error": False}
        yield {"type": "tool_result", "call_id": "t2", "content": "NameError: x", "is_error": True}
        yield {"type": "usage", "input_tokens": 1234, "output_tokens": 56, "cost_usd": 0.0123}
        yield {"type": "stop", "reason": "max_tokens"}


@component(provides=("loop",))
async def showcase(*, config: Mapping[str, Any] | None = None) -> Effects:
    """A model that shows the transcript every kind of event: `use = "bh_02.testing:showcase"`."""
    yield bind("loop", _Showcase())


class _Unprintable:
    """Text the ui cannot draw: turning it into a string fails."""

    def __str__(self) -> str:
        raise RuntimeError("this text cannot be drawn (bh_02.testing:bomb, on purpose)")


class _Bomb:
    """Replies with one text event the ui fails to draw, so the app crashes mid-turn."""

    async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "text", "text": _Unprintable()}


@component(provides=("loop",))
async def bomb(*, config: Mapping[str, Any] | None = None) -> Effects:
    """A model that crashes the ui: `use = "bh_02.testing:bomb"`, for the crash path."""
    yield bind("loop", _Bomb())
