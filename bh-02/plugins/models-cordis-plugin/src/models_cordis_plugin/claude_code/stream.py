"""One model step's raw Anthropic stream events, folded into chunks (CONTRACTS.md: chunk).

Claude Code, run with `include_partial_messages`, hands each raw Messages API stream event
through as a `StreamEvent` whose `event` is the event as a plain dict (`message_start`,
`content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`,
`message_stop`). `Step` folds them, purely: text and thinking as they stream, a tool call once
its block ends, then usage, the API's own stop reason and the assistant message as received
(every block, thinking signatures included), which `agent:loop` keeps for replay.

Tool names come as Claude Code sent them to the API (`mcp__bh__python`): the chunk carries the
name the loop knows (`python`), the message keeps the name as sent, so a rebuilt Claude
Code session replays it unchanged.
"""

import json
import re
from collections.abc import Mapping
from typing import Any, Final

__all__ = ["SERVER", "Step", "cost_of", "plain_name", "visible"]

type Json = Mapping[str, Any]

SERVER: Final = "bh"  # the MCP server's name: Claude Code calls its tools `mcp__bh__<name>`
_PREFIX: Final = f"mcp__{SERVER}__"

# USD per million tokens: (input, output, cache read), Anthropic's first-party list prices
# (the claude-api reference, cached 2026-06-24). A 5-minute cache write is 1.25x input. On a
# subscription nothing is billed per token: this is what the step would cost on the API, which
# is what the status bar shows. A model not listed gets no `cost_usd` rather than a guessed one.
_PRICES: Final[Mapping[str, tuple[float, float, float]]] = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-opus-4-7": (5.0, 25.0, 0.50),
    "claude-opus-4-6": (5.0, 25.0, 0.50),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
}
_CACHE_WRITE: Final = 1.25
_DATED: Final = re.compile(r"-\d{8}$")  # `claude-haiku-4-5-20251001` is priced as `claude-haiku-4-5`
_COUNTS: Final = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def plain_name(name: str) -> str:
    """`mcp__bh__python` as the loop knows it: `python`."""
    return name.removeprefix(_PREFIX)


def cost_of(model: str, usage: Json) -> float | None:
    """One step's cost in USD from its token counts, or None for a model the table does not list.

    `usage` carries the API's split: `input_tokens` (uncached), `cache_creation_input_tokens`,
    `cache_read_input_tokens`, `output_tokens`. The exact id is looked up first, so
    `claude-opus-5-5` is never priced as `claude-opus-5`.
    """
    price = _PRICES.get(model) or _PRICES.get(_DATED.sub("", model))
    if price is None:
        return None
    base, out, read = price
    total = (
        int(usage.get("input_tokens") or 0) * base
        + int(usage.get("cache_creation_input_tokens") or 0) * base * _CACHE_WRITE
        + int(usage.get("cache_read_input_tokens") or 0) * read
        + int(usage.get("output_tokens") or 0) * out
    )
    return total / 1_000_000


def _blank(block: Json) -> bool:
    """A text block with nothing but whitespace in it, which the API refuses (400) when sent
    back: a model can stream one (`"\\n\\n"`) before a tool call."""
    return block.get("type") == "text" and not str(block.get("text") or "").strip()


def visible(message: Json) -> bool:
    """Whether an assistant message says anything: a text block with more than whitespace."""
    return any(b.get("type") == "text" and not _blank(b) for b in message.get("content") or [])


class Step:
    """One streamed step, folded: the chunks each raw event carries, then the rest.

    Usage comes in two parts, each a `usage` chunk (CONTRACTS.md: the ui sums them): what the
    API reports at `message_start` (everything the model read, cached or not), marked
    `partial`, then at `finish` what the final counts add to it, output included.
    `message_start`'s provisional output count is left out: the output is known only from the
    final `message_delta`, which a step the person stops never gets, so its usage stays
    `partial` rather than a precise-looking "1 out".
    """

    def __init__(self) -> None:
        self.model = ""  # the model id the API answered with (`message_start`)
        self.stop: str | None = None
        self.ended = False  # `message_stop` seen
        self._blocks: dict[int, dict[str, Any]] = {}
        self._json: dict[int, list[str]] = {}
        self._usage: dict[str, int] = {}
        self._sent: dict[str, int] = {}  # what the usage chunks so far added up to
        self._bad: set[int] = set()  # tool_use blocks whose arguments did not decode

    def take(self, event: Json) -> list[dict[str, Any]]:
        """Record one raw stream event; return the chunks it carries."""
        match event.get("type"):
            case "message_start":
                message = event.get("message") or {}
                self.model = str(message.get("model") or "")
                self._count({k: v for k, v in (message.get("usage") or {}).items() if k != "output_tokens"})
                return self._used()
            case "content_block_start":
                block = dict(event.get("content_block") or {})
                index = int(event.get("index", 0))
                if block.get("type") == "tool_use":
                    block["input"] = {}
                    self._json[index] = []
                self._blocks[index] = block
                if block.get("type") == "text" and block.get("text"):
                    return [{"type": "text", "text": block["text"]}]
            case "content_block_delta":
                return self._delta(int(event.get("index", 0)), event.get("delta") or {})
            case "content_block_stop":
                return self._stopped(int(event.get("index", 0)))
            case "message_delta":
                self.stop = (event.get("delta") or {}).get("stop_reason") or self.stop
                self._count(event.get("usage") or {})
            case "message_stop":
                self.ended = True
        return []

    def _count(self, usage: Json) -> None:
        for key in _COUNTS:
            if isinstance(value := usage.get(key), int):
                self._usage[key] = value  # message_delta's counts are cumulative: the last one stands

    def _delta(self, index: int, delta: Json) -> list[dict[str, Any]]:
        block = self._blocks.get(index)
        if block is None:
            return []
        match delta.get("type"):
            case "text_delta":
                text = str(delta.get("text") or "")
                block["text"] = block.get("text", "") + text
                return [{"type": "text", "text": text}] if text else []
            case "thinking_delta":
                thinking = str(delta.get("thinking") or "")
                block["thinking"] = block.get("thinking", "") + thinking
                return [{"type": "thinking", "text": thinking}] if thinking else []
            case "signature_delta":
                block["signature"] = block.get("signature", "") + str(delta.get("signature") or "")
            case "input_json_delta":
                self._json.setdefault(index, []).append(str(delta.get("partial_json") or ""))
        return []

    def _stopped(self, index: int) -> list[dict[str, Any]]:
        block = self._blocks.get(index)
        if block is None or block.get("type") != "tool_use":
            return []
        raw = "".join(self._json.get(index, []))
        name = plain_name(str(block.get("name") or ""))
        chunk: dict[str, Any] = {"type": "tool_call", "id": block.get("id"), "name": name, "input": {}}
        try:
            decoded = json.loads(raw) if raw.strip() else {}
        except ValueError as error:
            chunk["error"] = f"the arguments are not valid JSON ({error})"
            self._bad.add(index)
            return [chunk]
        if not isinstance(decoded, dict):
            chunk["error"] = f"the arguments are a JSON {type(decoded).__name__}, not an object"
            self._bad.add(index)
            return [chunk]
        block["input"] = decoded
        chunk["input"] = decoded
        return [chunk]

    @property
    def message(self) -> dict[str, Any]:
        """The assistant message as received: every block but blank text, in order."""
        content = [block for _, block in sorted(self._blocks.items()) if not _blank(block)]
        return {"role": "assistant", "content": content}

    @property
    def calls(self) -> list[str]:
        """The ids of the tool calls this step made."""
        return [str(b.get("id")) for b in self.message["content"] if b.get("type") == "tool_use"]

    @property
    def undecodable(self) -> bool:
        """Whether a call's arguments did not decode."""
        return bool(self._bad)

    def finish(self) -> list[dict[str, Any]]:
        """The chunks that end the step: usage, the stop reason (when the API gave one), and the
        assistant message as received."""
        out = self._used()
        if self.stop is not None:
            out.append({"type": "stop", "reason": self.stop})
        out.append({"type": "message", "message": self.message})
        return out

    def _used(self) -> list[dict[str, Any]]:
        """A `usage` chunk for what the counts grew by since the last one, or none if nothing did."""
        grown = {key: value - self._sent.get(key, 0) for key, value in self._usage.items()}
        if not any(grown.values()):
            return []
        self._sent = dict(self._usage)
        used: dict[str, Any] = {
            "type": "usage",
            "input_tokens": sum(
                grown.get(k, 0)
                for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
            ),
            "output_tokens": grown.get("output_tokens", 0),
            "cache_read_input_tokens": grown.get("cache_read_input_tokens", 0),
            "cache_creation_input_tokens": grown.get("cache_creation_input_tokens", 0),
        }
        if "output_tokens" not in self._usage:
            used["partial"] = True  # the output count is still to come (CONTRACTS.md: usage)
        if (cost := cost_of(self.model, grown)) is not None:
            used["cost_usd"] = cost
        return [used]
