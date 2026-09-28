"""A composition on disk, for the tests that boot one the way the CLI does."""

import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import pytest

# The kernel with no jail, for tests that are not about the jail: brig runs on darwin and on
# Linux with bubblewrap, and a test of a model or a chat row should not depend on the platform.
UNJAILED = '[[plugin]]\nid = "jail"\nuse = "kernel:unjailed"\n'

# bh-02 has no one-shot chat row, but many of its tests want one: the reply to one prompt (the
# `chat` override's config), recorded rather than drawn, with a failure left to reach `done`.
ONE_REPLY = (
    '[[plugin]]\nid = "chat"\nuse = "fragile:one_reply"\n[[plugin]]\nid = "ui"\nuse = "fragile:recorded_ui"\n'
)

# An importable module of components, named by layer files as `fragile:<component>`.
PLUGIN = '''
import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from cordis import Effects, background, bind, component, use


class Slow(Exception):
    def __init__(self) -> None:
        super().__init__("slow down")
        self.kind, self.message = "rate_limit", "slow down"


class Echo:
    async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "text", "text": message}


class Angry:
    async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
        raise Slow()
        yield


class Silent:
    """An input that never answers, so only a model leaving ends the run."""

    async def read(self) -> str | None:
        await asyncio.Event().wait()
        return None

    async def interrupted(self) -> None:
        await asyncio.Event().wait()


FIELDS: dict[str, str] = {}


class Pushed:
    """A `frame` (CONTRACTS.md) that notes the status fields rows push, in FIELDS, and keeps
    them after their rows leave (so a test can read them once the run is over)."""

    def status(self, field: str, text: str, *shorter: str) -> Any:
        FIELDS[field] = text
        return None

    def sessions(self, listed: Any) -> Any:
        SESSIONS[:] = list(listed())  # read once, at the push: what the sidebar would show then
        return None

    def commands(self, specs: Any) -> Any:
        return None


SESSIONS: list[Any] = []


class Drop:
    async def show(self, chunks: AsyncIterator[Mapping[str, Any]]) -> None:
        async for _ in chunks:
            pass

    async def notice(self, message: str) -> None: ...

    async def confirm(self, request: Mapping[str, Any]) -> bool:
        return False


class OneMessage:
    """One message, then no more input: an interactive session that ends on its own."""

    def __init__(self) -> None:
        self._sent = False

    async def read(self) -> str | None:
        if self._sent:
            return None
        self._sent = True
        return "hi"

    async def interrupted(self) -> None:
        await asyncio.Event().wait()


class Upper:
    async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "text", "text": message.upper()}


@component(provides=("loop",))
async def upper_model() -> Effects:
    yield bind("loop", Upper())


# A session a test can pace: the first message at once, the second when SECOND is set.
SECOND = asyncio.Event()
SHOWN: list[str] = []


class Paced:
    def __init__(self) -> None:
        self._sent = 0

    async def read(self) -> str | None:
        """A read cancelled part-way (the chat row restarting) is not a read: nothing is lost."""
        if self._sent == 0:
            self._sent = 1
            return "one"
        if self._sent == 1:
            await SECOND.wait()
            self._sent = 2
            return "two"
        return None

    async def interrupted(self) -> None:
        await asyncio.Event().wait()


NOTES: list[str] = []
SCRIPT: list[str] = []


def script(*lines: str) -> None:
    """What the scripted ui will read, in order."""
    SCRIPT[:] = lines


ASKED: list[Mapping[str, Any]] = []
ANSWERS: list[bool] = []


def answers(*these: bool) -> None:
    """What a recording ui says to each question (a cell to approve), in order; no after them."""
    ANSWERS[:] = these
    ASKED.clear()


class Record(Drop):
    async def show(self, chunks: AsyncIterator[Mapping[str, Any]]) -> None:
        async for chunk in chunks:
            if chunk.get("type") == "text":
                SHOWN.append(str(chunk["text"]))
            elif chunk.get("type") == "note":
                NOTES.append(str(chunk["text"]))

    async def confirm(self, request: Mapping[str, Any]) -> bool:
        ASKED.append(request)
        return ANSWERS.pop(0) if ANSWERS else False


class Scripted:
    """Reads SCRIPT a line at a time, pausing so a queued restart can land between lines."""

    async def read(self) -> str | None:
        await asyncio.sleep(0.2)
        return SCRIPT.pop(0) if SCRIPT else None

    async def interrupted(self) -> None:
        await asyncio.Event().wait()


@dataclass(frozen=True, slots=True)
class Prompt:
    prompt: str


@component(provides=("done",))
async def one_reply(*, loop: Any, output: Any, config: Prompt) -> Effects:
    """A one-shot chat row: show the reply to `config.prompt`, then done. A failure is not caught:
    it reaches the bootstrap through `done`, the way the chat row's failure does."""
    task = yield background(output.show(loop.reply(config.prompt)))
    yield bind("done", task)


@component(provides=("output", "frame"))
async def recorded_ui() -> Effects:
    """An output that records, and no input: for a one-shot chat row (`one_reply`)."""
    yield bind("output", Record())
    yield bind("frame", Pushed())


def shown() -> str:
    """Everything the recording outputs were shown, as one text."""
    return "".join(SHOWN)


@component(provides=("input", "output", "frame"))
async def scripted_ui() -> Effects:
    yield bind("input", Scripted())
    yield bind("frame", Pushed())
    yield bind("output", Record())


@component(provides=("input", "output", "frame"))
async def paced_ui() -> Effects:
    yield bind("input", Paced())
    yield bind("frame", Pushed())
    yield bind("output", Record())


class Counting:
    """A model that says how many user messages it was shown: history, made visible."""

    async def complete(self, messages: Any, tools: Any) -> AsyncIterator[dict[str, Any]]:
        users = [m for m in messages if m["role"] == "user"]
        yield {"type": "text", "text": f"seen {len(users)}"}
        yield {"type": "stop", "reason": "stop"}


@component(provides=("model",))
async def counting_model() -> Effects:
    yield bind("model", Counting())


@component(provides=("input", "output", "frame"))
async def one_message_recorded_ui() -> Effects:
    yield bind("input", OneMessage())
    yield bind("frame", Pushed())
    yield bind("output", Record())


@component(provides=("loop",))
async def echo_model() -> Effects:
    yield bind("loop", Echo())


@component(provides=("loop",))
async def angry_model() -> Effects:
    yield bind("loop", Angry())


@component(provides=("loop",))
async def held_model() -> Effects:
    yield bind("loop", Echo())


@component(provides=("done",))
async def bad_done_mode() -> Effects:
    """Binds `done` to something that is not awaitable: a contract violation for bh-02's
    own `harness` row (bh_02.bootstrap:_ChatDone), not a shape any chat row should produce."""
    yield bind("done", 42)


@component
async def fragile_model() -> Effects:
    """Binds the model through a child, then retires that child mid-run."""
    child = yield use(held_model)

    async def leave() -> None:
        await asyncio.sleep(0.01)
        await child.retire()

    yield background(leave())


@component(provides=("input", "output", "frame"))
async def silent_ui() -> Effects:
    yield bind("input", Silent())
    yield bind("frame", Pushed())
    yield bind("output", Drop())


@component(provides=("input", "output", "frame"))
async def one_message_ui() -> Effects:
    yield bind("input", OneMessage())
    yield bind("frame", Pushed())
    yield bind("output", Drop())


@component
async def heartbeat() -> Effects:
    """Background work owned by a row that is not the chat row: never resolves on its own."""

    async def forever() -> None:
        await asyncio.Event().wait()

    yield background(forever())


@dataclass(frozen=True)
class Cells:
    code: tuple[str, ...] = ()


class CellScript:
    """A model that acts only in code: it calls each scripted cell in turn, through the
    loop (which asks about it when the kernel is unjailed), then shows every result."""

    def __init__(self, cells: tuple[str, ...]) -> None:
        self._cells = cells

    async def complete(self, messages: Any, tools: Any) -> AsyncIterator[dict[str, Any]]:
        results = [m["content"] for m in messages if m["role"] == "tool"]
        if len(results) < len(self._cells):
            n = len(results)
            yield {"type": "tool_call", "id": f"c{n}", "name": "python", "input": {"code": self._cells[n]}}
            yield {"type": "stop", "reason": "tool_use"}
            return
        yield {"type": "text", "text": "".join(f"[{n}] {r}\\n" for n, r in enumerate(results))}
        yield {"type": "stop", "reason": "end_turn"}


@component(provides=("model",))
async def cell_model(*, config: Cells) -> Effects:
    yield bind("model", CellScript(tuple(config.code)))


class OneCell:
    """A model that asks for one python cell, then answers with what the cell printed."""

    async def complete(self, messages: Any, tools: Any) -> AsyncIterator[dict[str, Any]]:
        offered = [t["name"] for t in tools]
        results = [m for m in messages if m["role"] == "tool"]
        if not results:
            yield {"type": "tool_call", "id": "c1", "name": "python", "input": {"code": "print(6 * 7)"}}
            yield {"type": "stop", "reason": "stop"}
            return
        yield {"type": "text", "text": f"offered {offered}; the cell said {results[-1]['content'].strip()}"}
        yield {"type": "stop", "reason": "stop"}


@component(provides=("model",))
async def one_cell_model() -> Effects:
    yield bind("model", OneCell())
'''


@pytest.fixture(autouse=True)
def _own_models_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test reads a models file of its own (none, unless it writes one), never the
    person's `~/.config/bh-02/models.toml`."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


class Composition(Protocol):
    def __call__(self, text: str, *, one_reply: bool = False) -> Path: ...


@pytest.fixture
def composition(tmp_path: Path) -> Iterator[Composition]:
    """Writes an importable `fragile` module, and builds layer files that name it."""
    (tmp_path / "fragile.py").write_text(PLUGIN)
    sys.path.insert(0, str(tmp_path))
    written = 0

    def layer(text: str, *, one_reply: bool = False) -> Path:
        """A layer file; every one also puts the kernel in no jail (see UNJAILED), and
        `one_reply` makes the chat row a one-shot whose reply is recorded (see ONE_REPLY)."""
        nonlocal written
        written += 1
        path = tmp_path / f"layer{written}.toml"
        path.write_text(UNJAILED + (ONE_REPLY if one_reply else "") + text)
        return path

    try:
        yield layer
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("fragile", None)
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)
