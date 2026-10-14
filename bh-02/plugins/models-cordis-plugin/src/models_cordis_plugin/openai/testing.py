"""A stand-in OpenAI-compatible server for tests: `StubServer`, real sockets, real SSE; and
`FakeGet`, the `Get` a test of model discovery gives the catalog instead of a network.

It serves `POST /v1/chat/completions` on 127.0.0.1 from a thread, streaming each reply as
server-sent events the way the API does (a role delta, content in pieces, a tool call's id and
name first and its arguments in pieces, `finish_reason`, a usage-only event, `[DONE]`), and
keeps every request it was sent. What it answers depends on the conversation's last message,
read without the date `agent:loop` may tell first (`(Today's date: 2026-10-07.)` and a blank
line, CONTRACTS.md: message):

- a tool result: `the input said: <result>` (a python call's round trip);
- `call <code>`: one call of the offered tool with `<code>` as its `code`;
- `broken call`: a call whose arguments are not JSON;
- `status <n>`: that HTTP status with the API's JSON error;
- `fail midway`: some text, then an error event inside the stream;
- `slowly <words>`: the words over and over, one event every 20ms, for some seconds (a reply
  long enough to be stopped part-way);
- anything else: `[<model id>] heard: <message>`, a few words at a time.

`GET /v1/models` lists the ids it was given (`models`), after `delay` seconds when that is set, as
the API's JSON list (`{"object": "list", "data": [{"id": ..., "object": "model"}]}`), kept in
`requests` like the rest (each has its `method`, `path` and `authorization`; a POST its `body`).

With `key` set, a request without `Authorization: Bearer <key>` is answered 401, and a wrong
key is echoed back in that answer, whole and masked but for its end (as a proxy and OpenAI's
own 401 do). With `strict`, a request asking for usage (`stream_options`) is answered 422, as
a server that forbids fields it doesn't know does. Each kept
request gets an `outcome` once its reply ends: `complete`, or `cut` when the client closed the
connection before the reply was all written.
"""

import asyncio
import json
import re
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from models_cordis_plugin.openai.listing import Down, Reply

__all__ = ["FakeGet", "StubServer"]

type Json = Mapping[str, Any]

_DATED = re.compile(r"\(Today's date: [0-9-]+\.\)\n\n")


_CHANGED = "(End of what changed.)\n\n"  # how the loop's aside on changed instructions ends


def _said(message: Json) -> str:
    """A message's text, without what the loop may put first: the date, and an aside that the
    model's instructions changed."""
    content = str(message.get("content") or "")
    content = content[dated.end() :] if (dated := _DATED.match(content)) else content
    return (
        content.partition(_CHANGED)[2] if content.startswith("(bh-02: ") and _CHANGED in content else content
    )


def _chunk(model: str, delta: Json | None = None, finish: str | None = None, **extra: Any) -> dict[str, Any]:
    choices = [] if delta is None else [{"index": 0, "delta": dict(delta), "finish_reason": finish}]
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion.chunk",
        "model": model,
        "choices": choices,
        **extra,
    }


def _events(body: Json) -> Iterator[dict[str, Any] | str]:
    """The events one reply streams (module docstring), `[DONE]` last."""
    model = str(body.get("model", "stub"))
    messages: Sequence[Json] = body.get("messages", [])
    last = messages[-1] if messages else {"role": "user", "content": ""}
    said = _said(last)
    yield _chunk(model, {"role": "assistant", "content": ""})
    if last.get("role") == "tool":
        # what the input printed, without the python tool's note of bh-02's other tools, told
        # with the first input
        printed = "\n".join(line for line in said.strip().splitlines() if not line.startswith("(bh-02's "))
        for part in ("the input ", f"said: {printed}"):
            yield _chunk(model, {"content": part})
        finish = "stop"
    elif said.startswith("call ") or said == "broken call":
        offered = [str(t.get("function", {}).get("name")) for t in body.get("tools") or []]
        tool = "python" if "python" in offered or not offered else offered[0]
        arguments = (
            json.dumps({"code": said.removeprefix("call ")}) if said != "broken call" else '{"code": "x'
        )
        yield _chunk(
            model,
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": f"call_{len(messages)}",
                        "type": "function",
                        "function": {"name": tool, "arguments": ""},
                    }
                ]
            },
        )
        for n in range(0, len(arguments), 7):
            yield _chunk(
                model, {"tool_calls": [{"index": 0, "function": {"arguments": arguments[n : n + 7]}}]}
            )
        finish = "tool_calls"
    elif said.startswith("slowly "):
        for word in said.split()[1:] * 100:
            yield _chunk(model, {"content": f"{word} "})
        finish = "stop"
    elif said == "fail midway":
        yield _chunk(model, {"content": "half a "})
        yield {"error": {"message": "the upstream provider went away", "code": 502}}
        return
    else:
        for word in f"[{model}] heard: {said}".split(" "):
            yield _chunk(model, {"content": f"{word} "})
        finish = "stop"
    yield _chunk(model, {}, finish)
    prompt = sum(len(str(m.get("content") or "")) for m in messages)
    yield _chunk(model, usage={"prompt_tokens": prompt, "completion_tokens": 7, "total_tokens": prompt + 7})
    yield "[DONE]"


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, format: str, *args: Any) -> None:
        pass  # quiet: a test's output is its own

    def _json(self, status: int, message: str) -> None:
        data = json.dumps({"error": {"message": message, "type": "stub_error", "code": status}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        kept: dict[str, Any] = {
            "method": "GET",
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
        }
        self.server.requests.append(kept)
        if self.path.rstrip("/") != "/v1/models":
            self._json(404, f"no route {self.path}")
            return
        time.sleep(self.server.delay)
        sent = self.headers.get("Authorization")
        if self.server.key is not None and sent != f"Bearer {self.server.key}":
            self._json(401, "Incorrect API key provided")
            return
        data = json.dumps(
            {"object": "list", "data": [{"id": name, "object": "model"} for name in self.server.models]}
        ).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except BrokenPipeError, ConnectionResetError:
            pass  # the client gave up before the answer (its deadline): nothing to say

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        kept: dict[str, Any] = {
            "method": "POST",
            "path": self.path,
            "body": body,
            "authorization": self.headers.get("Authorization"),
        }
        self.server.requests.append(kept)
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._json(404, f"no route {self.path}")
            kept["outcome"] = "complete"
            return
        sent = self.headers.get("Authorization")
        if self.server.key is not None and sent != f"Bearer {self.server.key}":
            wrong = (sent or "").removeprefix("Bearer ")
            echo = f": {wrong[:3]}****{wrong[-4:]} (you sent {sent})" if wrong else ""
            self._json(401, f"Incorrect API key provided{echo}")
            return
        if self.server.strict and "stream_options" in body:
            self._json(422, "body.stream_options: Extra inputs are not permitted")
            return
        said = _said((body.get("messages") or [{}])[-1])
        if said.startswith("status "):
            self._json(int(said.split()[1]), f"stub says {said}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        pause = 0.02 if said.startswith("slowly ") else 0.0
        try:
            self.wfile.write(b": stub keep-alive\n\n")  # a comment line, as OpenRouter sends
            for event in _events(body):
                data = event if isinstance(event, str) else json.dumps(event)
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
                time.sleep(pause)
        except BrokenPipeError, ConnectionResetError:
            kept["outcome"] = "cut"  # the client closed the stream part-way
        else:
            kept["outcome"] = "complete"
        self.close_connection = True


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, key: str | None, strict: bool, models: Sequence[str], delay: float) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.key = key
        self.strict = strict
        self.models = tuple(models)
        self.delay = delay
        self.requests: list[dict[str, Any]] = []


class StubServer:
    """The stub on a port of its own, served from a thread while entered: `base_url` is what a
    model's table names, `requests` what it was sent."""

    def __init__(
        self,
        key: str | None = None,
        *,
        strict: bool = False,
        models: Sequence[str] = (),
        delay: float = 0.0,
    ) -> None:
        self._server = _Server(key, strict, models, delay)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}/v1"

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self._server.requests

    def __enter__(self) -> StubServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()


class FakeGet:
    """A `Get` with no network: each URL asked answers what `replies` maps it to (a `Reply`, or a
    `Down`), else `Down("no such server")`. `calls` keeps every request as `(url, headers)`, in
    order, headers as they were handed over. `gate`, when set, holds each answer until it is set."""

    def __init__(self, replies: Mapping[str, Reply | Down], gate: asyncio.Event | None = None) -> None:
        self.replies = dict(replies)
        self.calls: list[tuple[str, dict[str, str]]] = []
        self._gate = gate

    async def __call__(self, url: str, headers: Mapping[str, str]) -> Reply | Down:
        self.calls.append((url, dict(headers)))
        if self._gate is not None:
            await self._gate.wait()
        return self.replies.get(url, Down("no such server"))
