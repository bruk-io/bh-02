"""An OpenAI-compatible `/chat/completions` stream as the `model` contract's chunks, and back.

The Chat Completions API is what OpenAI, OpenRouter, Groq, Together, Mistral, xAI, DeepSeek,
Gemini's compatibility endpoint, vLLM, LM Studio and Ollama (`/v1`) all serve. Everything here
is pure: the request body for one step (`request_for`), a streamed event folded into chunks
(`Fold`), the API's `finish_reason` as a stop the loop's `stops.classify` reads (`stop_for`), and
an HTTP failure as an error that says what to do (`http_error`), with the key the request sent
taken out of anything the server said (`scrubbed`). `client.py` does the I/O.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from models_cordis_plugin.named import ModelsError

__all__ = [
    "Fold",
    "Where",
    "http_error",
    "rejects_usage",
    "replayed",
    "request_for",
    "scrubbed",
    "sse_data",
    "stop_for",
    "stream_error",
]

type Json = Mapping[str, Any]

# The API's finish reasons in the words `stops.classify` knows: `stop` and `length` are its own
# already; a filtered reply is a refusal (never run, never fed back), and the legacy
# `function_call` is a call.
_STOPS: Final[Mapping[str, str]] = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "function_call": "tool_calls",
    "content_filter": "refusal",
}
_SERVER_TEXT: Final = 300  # how much of a server's error body a message quotes
_KEY_SHOWN: Final = "<key>"  # what a key the server echoed back reads as in an error
# A word the server masked a key in (OpenAI's `sk-proj-****abcd`): stars, or dots, in a run.
_MASKED: Final = re.compile(r"\S*(?:\*{2,}|\.{3,}|…)\S*")


@dataclass(frozen=True, slots=True)
class Where:
    """What an error names: the model, the URL asked, the key's line in local.env (if any)
    and where the model was named, so the message says what to change."""

    name: str
    url: str
    model: str
    key: str | None
    source: str


def request_for(
    model: str,
    messages: Sequence[Json],
    tools: Sequence[Json],
    settings: Mapping[str, Any],
    *,
    usage: bool = True,
) -> dict[str, Any]:
    """The `/chat/completions` body for one step: the transcript's messages in the API's
    shape, the tool specs as functions, streaming, with usage asked for (`stream_options`)
    unless `usage` is false (a server that rejects the field: `rejects_usage`); `max_tokens`
    and `temperature` only when the model's table sets them (reasoning models reject both)."""
    body: dict[str, Any] = {"model": model, "messages": [replayed(m) for m in messages], "stream": True}
    if usage:
        body["stream_options"] = {"include_usage": True}
    if tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": dict(t["parameters"]),
                },
            }
            for t in tools
        ]
    for name in ("max_tokens", "temperature"):
        if settings.get(name) is not None:
            body[name] = settings[name]
    return body


def replayed(message: Json) -> dict[str, Any]:
    """A transcript message as the API takes it. An assistant turn this provider sent is
    replayed as it came (`provider`); another provider's (Claude's content blocks, Ollama's
    parsed arguments), in a conversation that switched models, is rebuilt from the
    transcript's own text and calls."""
    role = message["role"]
    if role == "tool":
        return {
            "role": "tool",
            "tool_call_id": str(message.get("call_id", "")),
            "content": str(message["content"]),
        }
    if role != "assistant":
        return {"role": role, "content": str(message.get("content") or "")}
    provider = message.get("provider")
    if isinstance(provider, Mapping) and _ours(provider):
        return dict(provider)
    calls = message.get("tool_calls") or []
    out: dict[str, Any] = {"role": "assistant", "content": str(message.get("content") or "") or None}
    if calls:
        out["tool_calls"] = [
            {
                "id": str(c["id"]),
                "type": "function",
                "function": {"name": str(c["name"]), "arguments": json.dumps(dict(c["input"]))},
            }
            for c in calls
        ]
    elif out["content"] is None:
        out["content"] = ""
    return out


def _ours(provider: Json) -> bool:
    """Whether a transcript's `provider` message is in this API's shape: text or none, and
    calls whose arguments are the JSON text the API sent."""
    if provider.get("role") != "assistant" or not isinstance(provider.get("content"), str | None):
        return False
    calls = provider.get("tool_calls", [])
    return isinstance(calls, list) and all(
        isinstance(c, Mapping)
        and isinstance(c.get("function"), Mapping)
        and isinstance(c["function"].get("arguments"), str)
        for c in calls
    )


def sse_data(line: str) -> str | None:
    """The data of one server-sent-events line, or None for anything else (a comment such as
    OpenRouter's `: PROCESSING`, a blank line, an `event:` line)."""
    if not line.startswith("data:"):
        return None
    return line.removeprefix("data:").strip()


def stop_for(finish: str | None) -> str:
    """The API's `finish_reason` as a stop `stops.classify` reads (module docstring)."""
    return _STOPS.get(finish or "", finish or "stop")


@dataclass
class _Call:
    """One tool call as its deltas arrive: an id and a name (often only in the first delta),
    and the arguments' JSON text, a piece at a time."""

    id: str = ""
    name: str = ""
    arguments: list[str] = field(default_factory=list)


@dataclass
class Fold:
    """One step's streamed events, folded: text and thinking passed on as they arrive, the
    tool calls assembled by `index` (a server may send a call whole in one delta, or its id
    and name first and the arguments in pieces), then, at the end (`finish`), each call, the
    usage, the stop and the assistant message for replay."""

    # what a call the server sent without an id is named: `call_<ids><n>`. The client passes a
    # fresh prefix per step, so the names are unique across a conversation (a provider that
    # replays them, Claude's, requires it)
    ids: str = ""
    _text: list[str] = field(default_factory=list, init=False)
    _calls: dict[int, _Call] = field(default_factory=dict, init=False)
    _at: dict[int, int] = field(default_factory=dict, init=False)  # a server's index -> its call
    _usage: Json | None = field(default=None, init=False)
    finish_reason: str | None = field(default=None, init=False)

    def take(self, event: Json) -> list[dict[str, Any]]:
        """The chunks one streamed event carries now (a call waits for `finish`)."""
        out: list[dict[str, Any]] = []
        if isinstance(event.get("usage"), Mapping):
            self._usage = event["usage"]
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            # DeepSeek's `reasoning_content`, OpenRouter's and Ollama's `reasoning`
            thinking = delta.get("reasoning_content") or delta.get("reasoning")
            if isinstance(thinking, str) and thinking:
                out.append({"type": "thinking", "text": thinking})
            if isinstance(text := delta.get("content"), str) and text:
                self._text.append(text)
                out.append({"type": "text", "text": text})
            for n, part in enumerate(delta.get("tool_calls") or []):
                self._call(part, n)
            if choice.get("finish_reason"):
                self.finish_reason = str(choice["finish_reason"])
        return out

    def _slot(self, part: Json, n: int) -> int:
        """Which call a delta's part belongs to: its `index`; without one (Gemini's compatibility
        endpoint leaves it out), the last call, unless the part opens another: it carries an id
        other than the last call's; or it has no id and either is not the first part of its
        delta, or names a function while the last call is whole (named, its arguments complete
        JSON: parallel calls each sent whole, with neither index nor id)."""
        index = part.get("index")
        if isinstance(index, int):
            # a part with an id other than the one the call at its index holds opens a call of its
            # own: some servers send each parallel call at index 0
            slot = self._at.get(index)
            held = self._calls.get(slot) if slot is not None else None
            ident = part.get("id")
            if slot is None or (held is not None and ident and held.id and ident != held.id):
                slot = max(self._calls) + 1 if self._calls else 0
                self._at[index] = slot
            return slot
        if not self._calls:
            return 0
        last = self._calls[at := max(self._calls)]
        ident = part.get("id")
        named = isinstance(part.get("function"), Mapping) and bool(part["function"].get("name"))
        opens = (ident and last.id and ident != last.id) or (
            not ident and (n > 0 or (named and bool(last.name) and _whole(last.arguments)))
        )
        return at + 1 if opens else at

    def _call(self, part: Json, n: int) -> None:
        call = self._calls.setdefault(self._slot(part, n), _Call())
        call.id = str(part.get("id") or call.id)
        function = part.get("function") or {}
        call.name = str(function.get("name") or call.name)
        if isinstance(arguments := function.get("arguments"), str):
            call.arguments.append(arguments)
        elif isinstance(arguments, Mapping):  # a server that sends them parsed
            call.arguments.append(json.dumps(arguments))

    def finish(self) -> list[dict[str, Any]]:
        """The step's end: each call (one whose arguments don't decode carries `error`), the
        usage, the stop and the assistant message as received, for replay."""
        out: list[dict[str, Any]] = []
        sent: list[dict[str, Any]] = []
        for n, (_, call) in enumerate(sorted(self._calls.items())):
            ident = call.id or f"call_{self.ids}{n}"
            raw = "".join(call.arguments)
            chunk: dict[str, Any] = {"type": "tool_call", "id": ident, "name": call.name, "input": {}}
            try:
                decoded = json.loads(raw) if raw.strip() else {}
            except ValueError as error:
                chunk["error"] = f"arguments are not JSON ({error}): {raw[:200]}"
            else:
                if isinstance(decoded, dict):
                    chunk["input"] = decoded
                else:
                    chunk["error"] = f"arguments are not a JSON object: {raw[:200]}"
            out.append(chunk)
            sent.append({"id": ident, "type": "function", "function": {"name": call.name, "arguments": raw}})
        if self._usage is not None:
            out.append(_usage(self._usage))
        out.append({"type": "stop", "reason": stop_for(self.finish_reason)})
        message: dict[str, Any] = {"role": "assistant", "content": "".join(self._text) or None}
        if sent:
            message["tool_calls"] = sent
        elif message["content"] is None:
            message["content"] = ""
        out.append({"type": "message", "message": message})
        return out


def _whole(arguments: Sequence[str]) -> bool:
    """Whether a call's arguments so far are complete JSON (so more would not be its own)."""
    raw = "".join(arguments)
    try:
        json.loads(raw)
    except ValueError:
        return False
    return bool(raw.strip())


def _usage(usage: Json) -> dict[str, Any]:
    """The API's usage as a `usage` event: what the model read (cached or not) and wrote."""
    out: dict[str, Any] = {
        "type": "usage",
        "input_tokens": int(usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or 0),
    }
    details = usage.get("prompt_tokens_details")
    if isinstance(details, Mapping) and details.get("cached_tokens"):
        out["cache_read_input_tokens"] = int(details["cached_tokens"])
    return out


def scrubbed(text: str, sent: Mapping[str, str] | None) -> str:
    """`text` from the server with the key the request sent (`sent`: its headers) taken out:
    the key itself wherever it appears (a proxy that echoes the header), and a word that masks
    it but still shows its end (OpenAI's `Incorrect API key provided: sk-proj-****abcd`), each
    as `<key>`. An error is shown in the conversation and kept in the session's events, where
    no part of a key may go."""
    key = (sent or {}).get("Authorization", "").removeprefix("Bearer ").strip()
    if not key:
        return text
    text = text.replace(key, _KEY_SHOWN)
    return _MASKED.sub(lambda m: _KEY_SHOWN if key[-4:] in m.group() else m.group(), text)


def rejects_usage(status: int, body: str) -> bool:
    """Whether a failed request was refused for asking for usage (`stream_options`, a field
    some OpenAI-compatible servers don't take), so the step is asked again without it."""
    return status in (400, 422) and ("stream_options" in body or "include_usage" in body)


def _server_text(body: str) -> str:
    """What the server said about a failure: its error's message when the body is the API's
    JSON error, else the body itself, cut short."""
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    if isinstance(data, Mapping):
        error = data.get("error")
        if isinstance(error, Mapping) and error.get("message"):
            return str(error["message"])[:_SERVER_TEXT]
        if isinstance(error, str):
            return error[:_SERVER_TEXT]
    return " ".join(body.split())[:_SERVER_TEXT]


def http_error(status: int, body: str, where: Where, sent: Mapping[str, str] | None = None) -> ModelsError:
    """An HTTP failure as the recoverable error the person sees: what happened, and what to do;
    what the server said is quoted without the key the request sent (`scrubbed`)."""
    said = _server_text(scrubbed(body, sent))
    heard = f"{where.url} answered HTTP {status}" + (f": {said}" if said else "")
    if status in (401, 403):
        if where.key is None:
            todo = (
                f'model {where.name!r} sends no key; if the endpoint needs one, add `key = "NAME"` to its '
                f"table ({where.source}) and `NAME=<the key>` to local.env, then send the message again"
            )
        else:
            todo = (
                f"check the key {where.key} in local.env (model {where.name!r} names it), then send the "
                "message again"
            )
        return ModelsError("authentication_failed", f"{heard}. The endpoint refused the credential: {todo}.")
    if status == 404:
        return ModelsError(
            "not_found",
            f"{heard}. Check model {where.name!r}'s base_url (the part before /chat/completions) and its "
            f"id {where.model!r} ({where.source}), or /model another model.",
        )
    if status == 429:
        return ModelsError("rate_limit", f"{heard}. Try again in a moment, or /model another model.")
    if status in (400, 413, 422):
        return ModelsError(
            "invalid_request",
            f"{heard}. The endpoint rejected the request: send the message again; if it is rejected "
            "again, /clear starts a fresh conversation, or /model another model.",
        )
    if status >= 500:
        return ModelsError("server_error", f"{heard}. The server failed; try again in a moment.")
    return ModelsError("http_error", f"{heard}. Send the message again, or /model another model.")


def stream_error(error: object, where: Where, sent: Mapping[str, str] | None = None) -> ModelsError:
    """An error the server sent inside the stream (OpenRouter does, mid-reply), quoted without
    the key the request sent."""
    said = _server_text(scrubbed(json.dumps({"error": error}), sent))
    return ModelsError(
        "server_error",
        f"{where.url} failed mid-reply: {said}. Send the message again, or /model another model.",
    )
