"""A Claude Code session with no process and no network, for tests: `FakeClaudeCode`.

It behaves the way the real CLI was measured to (README.md), in the SDK's own message types:
a query streams each scripted step as raw Messages API events (`StreamEvent`), then the
finished `AssistantMessage`; a step that asks for tools asks the permission callback, then
calls the declared tools through the in-process MCP server over the MCP protocol itself (an
`mcp.Client` on the options' `Server`), with the tool_use id in the request's `_meta`, and
records the results (`UserMessage`) before the next step; an answered step ends the query with
a `ResultMessage`; `interrupt()` ends the running query with one at once. A tool the
permission callback denies is answered by the fake itself, as Claude Code does.
"""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    Message,
    PermissionResultAllow,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk.types import AssistantMessageError, ContentBlock
from mcp import Client
from mcp.types import RequestParamsMeta

__all__ = ["FakeClaudeCode", "FakeStep", "events_for"]

type Json = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class FakeStep:
    """One scripted model step: its content blocks as the API sends them, and why it stopped."""

    blocks: Sequence[Json]
    stop: str = "end_turn"
    model: str = "claude-sonnet-5"
    input_tokens: int = 100
    output_tokens: int = 10
    # stream this many events, then nothing until interrupted (a slow model)
    stall_after: int | None = None
    # the step fails instead, with Claude Code's error kind (`rate_limit`, ...)
    error: AssistantMessageError | None = None
    # after this many events the stream starts over (a retried stream: a second `message_start`)
    restart_after: int | None = None


def events_for(step: FakeStep, *, message_id: str = "msg_fake") -> list[dict[str, Any]]:
    """The raw stream events the Messages API sends for `step` (text in two deltas, a tool
    call's input as JSON in two fragments, a thinking block with its signature)."""
    start = {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": step.model,
        "content": [],
        "usage": {"input_tokens": step.input_tokens, "output_tokens": 1},
    }
    events: list[dict[str, Any]] = [{"type": "message_start", "message": start}]
    for index, block in enumerate(step.blocks):
        match block.get("type"):
            case "text":
                text = str(block["text"])
                half = len(text) // 2
                events.append(
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {"type": "text", "text": ""},
                    }
                )
                for part in (text[:half], text[half:]):
                    events.append(
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {"type": "text_delta", "text": part},
                        }
                    )
            case "thinking":
                events.append(
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {"type": "thinking", "thinking": "", "signature": ""},
                    }
                )
                events.append(
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "thinking_delta", "thinking": block["thinking"]},
                    }
                )
                events.append(
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "signature_delta", "signature": block["signature"]},
                    }
                )
            case "tool_use":
                started = {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}
                events.append({"type": "content_block_start", "index": index, "content_block": started})
                raw = str(block["raw"]) if "raw" in block else json.dumps(block["input"])
                half = len(raw) // 2
                for part in (raw[:half], raw[half:]):
                    events.append(
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {"type": "input_json_delta", "partial_json": part},
                        }
                    )
        events.append({"type": "content_block_stop", "index": index})
    events.append(
        {
            "type": "message_delta",
            "delta": {"stop_reason": step.stop},
            "usage": {"output_tokens": step.output_tokens},
        }
    )
    events.append({"type": "message_stop"})
    return events


def _blocks(step: FakeStep) -> list[Any]:
    out: list[Any] = []
    for block in step.blocks:
        if block.get("type") == "text":
            out.append(TextBlock(text=str(block["text"])))
        elif block.get("type") == "tool_use":
            out.append(
                ToolUseBlock(
                    id=str(block["id"]), name=str(block["name"]), input=dict(block.get("input") or {})
                )
            )
    return out


@dataclass
class FakeClaudeCode:
    """A `Session` over scripted steps (module docstring). `hold_calls`, when given, is awaited
    before the declared tools are called, so a test can deliver a result before its call.
    `asked` records every query: a string, or the message dicts a streamed prompt sent."""

    options: ClaudeAgentOptions
    steps: list[FakeStep]
    session_id: str = "fake-session"
    hold_calls: asyncio.Event | None = None
    asked: list[Any] = field(default_factory=list)
    interrupts: int = 0
    connected: bool = False
    disconnected: bool = False
    results: dict[str, str] = field(default_factory=dict)  # what each call got back
    crashed: Exception | None = None
    _queue: asyncio.Queue[Message] = field(default_factory=asyncio.Queue)
    _task: asyncio.Task[None] | None = None
    _stopping: bool = False

    async def connect(self) -> None:
        self.connected = True

    async def query(self, prompt: str | AsyncIterable[dict[str, Any]]) -> None:
        if isinstance(prompt, str):
            self.asked.append(prompt)
        else:
            self.asked.append([message async for message in prompt])
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._run())

    async def interrupt(self) -> None:
        self.interrupts += 1
        if self._task is not None and not self._task.done():
            self._stopping = True
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._stopping = False
            self._result("error_during_execution")

    async def receive_messages(self) -> AsyncIterator[Message]:
        while True:
            yield await self._queue.get()

    async def disconnect(self) -> None:
        self.disconnected = True
        if self._task is not None and not self._task.done():
            self._stopping = True
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

    def _result(self, subtype: str, *, is_error: bool = False) -> None:
        self._queue.put_nowait(
            ResultMessage(
                subtype=subtype,
                duration_ms=1,
                duration_api_ms=1,
                is_error=is_error,
                num_turns=1,
                session_id=self.session_id,
            )
        )

    async def _run(self) -> None:
        try:
            await self._steps()
        except Exception as error:
            if self._stopping:
                raise  # an interrupt's cancellation, as the MCP client's task group reports it
            # a broken script ends the query, so a test fails instead of waiting forever
            self.crashed = error
            self._result("error_during_execution", is_error=True)
            raise

    async def _steps(self) -> None:
        self._queue.put_nowait(SystemMessage(subtype="init", data={"session_id": self.session_id}))
        while self.steps:
            step = self.steps.pop(0)
            if step.error is not None:
                said = TextBlock(text=f"API Error: {step.error}")
                self._queue.put_nowait(AssistantMessage(content=[said], model=step.model, error=step.error))
                self._result("error_during_execution", is_error=True)
                return
            events = events_for(step)
            if step.restart_after is not None:
                events = events[: step.restart_after] + events
            for n, event in enumerate(events):
                if n == step.stall_after:
                    await asyncio.Event().wait()  # a slow model: until interrupted
                self._queue.put_nowait(StreamEvent(uuid="u", session_id=self.session_id, event=event))
                await asyncio.sleep(0)
            self._queue.put_nowait(AssistantMessage(content=_blocks(step), model=step.model))
            if step.stop != "tool_use":
                self._result("success")
                return
            if self.hold_calls is not None:
                await self.hold_calls.wait()
            calls = [b for b in step.blocks if b.get("type") == "tool_use"]
            answered: list[ContentBlock] = [await self._call(block) for block in calls]
            self._queue.put_nowait(UserMessage(content=answered))
        self._result("error_max_turns", is_error=True)

    async def _call(self, block: Json) -> ToolResultBlock:
        call_id, name, arguments = str(block["id"]), str(block["name"]), dict(block.get("input") or {})
        assert self.options.can_use_tool is not None
        allowed = await self.options.can_use_tool(name, arguments, ToolPermissionContext(tool_use_id=call_id))
        if not isinstance(allowed, PermissionResultAllow):
            return ToolResultBlock(tool_use_id=call_id, content=str(allowed.message), is_error=True)
        servers = self.options.mcp_servers
        assert isinstance(servers, dict) and servers["bh"]["type"] == "sdk"
        async with Client(servers["bh"]["instance"]) as client:
            result = await client.call_tool(
                name.removeprefix("mcp__bh__"),
                arguments,
                meta=cast(RequestParamsMeta, {"claudecode/toolUseId": call_id}),
            )
        text = "".join(getattr(part, "text", "") for part in result.content)
        self.results[call_id] = text
        return ToolResultBlock(tool_use_id=call_id, content=[{"type": "text", "text": text}])
