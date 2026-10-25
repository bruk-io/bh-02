"""The `openai` provider: one model on an OpenAI-compatible endpoint, as a `model` value.

Each step is one streamed POST to `<base_url>/chat/completions` (`wire.py` builds it and
folds what comes back). A model's `key` (`named.KeySpec`) says where its key comes from: `env`
names a variable of bh-02's process environment, read when a request is made, and `cmd` or `op`
is a command run as the person (`shell_key.py`) whose output is the key, kept for the key's `ttl_ms`
(dropped sooner when the server refuses it) so the command does not run for every step. The key
is put only in that request's `Authorization` header: never in an environment bh-02 hands on, never
in anything whose repr shows it, and taken out of anything the server says back before an error
quotes it. A model with no key sends none (a local server), and one whose key reads the Claude
Code token sends nothing at all (`named.withheld`: that is the CLI's alone). Usage is asked for
(`stream_options`) until the server refuses a step for it; that step is sent again without it,
and so is every later one. Closing the step (the person stopped the reply) closes the HTTP
stream with it.
"""

import json
import os
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Mapping, Sequence
from contextlib import aclosing
from typing import Any, Final

import httpx2

from models_cordis_plugin.named import DEFAULT_TTL_MS, KeySpec, ModelsError, Named, key_spec, withheld
from models_cordis_plugin.openai.wire import (
    Fold,
    Where,
    http_error,
    rejects_usage,
    request_for,
    scrubbed,
    settings_for,
    sse_data,
    stream_error,
)
from models_cordis_plugin.shell_key import command_key

__all__ = ["OpenAIModel", "headers_for", "missing_key"]

type Json = Mapping[str, Any]

# Connecting is quick or it fails; a local model can take minutes to its first token.
_TIMEOUT: Final = httpx2.Timeout(connect=10.0, read=None, write=60.0, pool=10.0)
_DONE: Final = "[DONE]"


class _Headers(dict[str, str]):
    """A request's headers: a dict whose repr names its keys, never a value (the key)."""

    def __repr__(self) -> str:
        return f"_Headers({sorted(self)!r})"

    __str__ = __repr__


async def headers_for(named: Named) -> dict[str, str]:
    """The request's headers: JSON, and `Authorization: Bearer <key>` when the model has a `key`: the
    variable it reads from bh-02's environment now, or what its command prints, run now
    (`shell_key.command_key`).

    Raises:
        ModelsError: the key can't be had (the variable is not set, the command fails or prints
            nothing), or is not something a header can carry (not printable ASCII); never the key.
    """
    headers = _Headers({"Content-Type": "application/json", "Accept": "text/event-stream"})
    spec = key_spec(named.table.get("key"))
    if spec is None:
        if "key" in named.table:  # never quoted: it may be the key itself (`named.problem` says so first)
            raise ModelsError(
                "model_config",
                f"model {named.name!r}: key must be a table saying where the key comes from, never the "
                'key itself, like `key = { env = "OPENAI_API_KEY" }`',
            )
        return headers
    if (why := withheld(named)) is not None:  # `named.problem` says so first; this is the last wall
        raise ModelsError("model_config", why)
    command = spec.command
    # straight into the header: no local of this frame holds the key (a crash prints locals)
    headers["Authorization"] = "Bearer " + (
        os.environ.get(spec.value, "") if command is None else await command_key(named.name, command)
    )
    if headers["Authorization"] == "Bearer ":
        raise ModelsError("authentication_failed", _unset_line(named.name, spec) + ".")
    if not _carried(headers["Authorization"]):
        raise ModelsError("authentication_failed", _unsendable_line(named.name, spec, command))
    return headers


def _carried(value: str) -> bool:
    """Whether a header's `value` can go out as it is: printable ASCII (httpx2 raises
    `UnicodeEncodeError` for a character outside it, and a control character is no header's)."""
    return value.isascii() and value.isprintable()


def _unset_line(name: str, spec: KeySpec) -> str:
    """Said for an `env` key whose variable is not set (or empty) in bh-02's environment."""
    return (
        f"model {name!r} reads its key from the environment variable {spec.value}, which is not set in "
        "bh-02's environment (the one it was started with; local.env is not read for a key). Export "
        f"{spec.value} in the shell that starts bh-02 (from direnv, `op run`, or your profile) and start it "
        "again"
    )


def _unsendable_line(name: str, spec: KeySpec, command: str | None) -> str:
    """Said without the key: it is what can't go in a header."""
    came = f"the environment variable {spec.value}" if command is None else f"`{command}`"
    check = (
        "Check what the variable holds" if command is None else "Run it in a terminal to check what it prints"
    )
    return (
        f"model {name!r}'s key from {came} holds a character a request header can't carry (a key is one "
        f"line of printable ASCII). {check}, fix it, then try again."
    )


def missing_key(named: Named) -> str | None:
    """Why `named`'s key can't be sent (an `env` key whose variable bh-02's environment doesn't
    have), said so the person can fix it; None when the model has no key, has a `cmd` or `op` (which is
    not run to find out), or the variable is set. Never quotes the key: it only asks whether it is set."""
    spec = key_spec(named.table.get("key"))
    if spec is None or spec.source != "env" or os.environ.get(spec.value):
        return None
    return _unset_line(named.name, spec) + "."


class OpenAIModel:
    """The `model` value over one OpenAI-compatible model (module docstring). An async context
    manager: its HTTP client is closed when the row leaves.

    `tool_changes` is `fixed` (CONTRACTS.md: model): a conversation is offered the tools it began
    with for its life, and a change is told as an aside. A chat template renders the tool list at
    the start of the prompt (llama.cpp, Ollama, vLLM), and OpenAI's prompt cache is a prefix
    too, so a changed list would make the whole conversation new to the server again.

    `settings` is what its requests are made with (CONTRACTS.md: model): the named model, the
    provider, and the `max_tokens` and `temperature` it sends (`wire.settings_for`)."""

    tool_changes: Final = "fixed"

    def __init__(
        self,
        named: Named,
        transport: httpx2.AsyncBaseTransport | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._named = named
        self.settings: Final = settings_for(named)
        self._client = httpx2.AsyncClient(timeout=_TIMEOUT, transport=transport)
        url = str(named.table["base_url"]).rstrip("/") + "/chat/completions"
        spec = key_spec(named.table.get("key"))
        self._command = spec.command if spec is not None else None
        self._where = Where(
            named.name,
            url,
            named.id,
            spec.value if spec and spec.source == "env" else None,
            named.source,
            self._command,
        )
        self._usage = True  # whether to ask for usage: until the server refuses it (`rejects_usage`)
        self._clock = clock
        self._ttl = (spec.ttl_ms if spec and spec.ttl_ms else DEFAULT_TTL_MS) / 1000
        self._kept: tuple[float, dict[str, str]] | None = None  # a command's headers, and until when

    async def _headers(self) -> dict[str, str]:
        """This step's headers (`headers_for`); a command key's are kept for its `ttl_ms`.

        Raises:
            ModelsError: the key can't be had.
        """
        if self._kept is not None and self._clock() < self._kept[0]:
            return self._kept[1]
        headers = await headers_for(self._named)
        if self._command is not None:
            self._kept = (self._clock() + self._ttl, headers)
        return headers

    async def __aenter__(self) -> OpenAIModel:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        """Stream one step's chunks (CONTRACTS.md: chunk)."""
        where = self._where
        try:
            headers = await self._headers()
            for usage in (True, False) if self._usage else (False,):
                body = request_for(self._named.id, messages, tools, self._named.table, usage=usage)
                async with self._client.stream("POST", where.url, json=body, headers=headers) as response:
                    if response.status_code >= 400:
                        said = (await response.aread()).decode("utf-8", errors="replace")
                        if usage and rejects_usage(response.status_code, scrubbed(said, headers)):
                            self._usage = False  # asked again without it, now and from now on
                            continue
                        if response.status_code in (401, 403):
                            self._kept = None  # a refused command key: the next step runs it again
                        raise http_error(response.status_code, said, where, headers)
                    async with aclosing(_streamed(response, where, headers)) as chunks:
                        async for chunk in chunks:
                            yield chunk
                    return
        except httpx2.ConnectError as error:
            raise ModelsError(
                "connection",
                f"Couldn't reach {where.url} for model {where.name!r} ({error}). Is the server running? "
                f"Check its base_url ({where.source}), or /model another model.",
            ) from None
        except httpx2.TimeoutException as error:
            raise ModelsError(
                "connection", f"{where.url} timed out ({type(error).__name__}). Send the message again."
            ) from None
        except httpx2.TransportError as error:
            raise ModelsError(
                "connection",
                f"Lost the connection to {where.url} ({type(error).__name__}: {error}). "
                "Send the message again.",
            ) from None
        except httpx2.InvalidURL as error:
            raise ModelsError(
                "model_config",
                f"model {where.name!r}: {where.url} is not a URL a request can go to ({error}); fix its "
                f"base_url ({where.source}), or /model another model.",
            ) from None
        except httpx2.HTTPError as error:  # the rest of httpx2's request failures (redirects, decoding)
            raise ModelsError(
                "server_error",
                f"{where.url} failed the request ({type(error).__name__}: {error}). Send the message again, "
                "or /model another model.",
            ) from None


async def _streamed(
    response: httpx2.Response, where: Where, headers: Mapping[str, str]
) -> AsyncGenerator[Json]:
    """A step's chunks from the server's events, as they arrive, then its end (`Fold.finish`)."""
    fold = Fold(ids=f"{uuid.uuid4().hex[:12]}_")
    done = False
    async for line in response.aiter_lines():
        data = sse_data(line)
        if data is None or not data:
            continue
        if data == _DONE:
            done = True
            break
        event = _event(data, where, headers)
        if event.get("error") is not None:
            raise stream_error(event["error"], where, headers)
        for chunk in fold.take(event):
            yield chunk
    if not done and fold.finish_reason is None:
        raise ModelsError(
            "connection",
            f"{where.url} ended the reply before it finished (no finish_reason, no [DONE]). "
            "Send the message again.",
        )
    for chunk in fold.finish():
        yield chunk


def _event(data: str, where: Where, headers: Mapping[str, str]) -> Json:
    """One event's JSON; one that is not JSON is a server failure, said as one (without the key)."""
    try:
        event = json.loads(data)
    except ValueError:
        raise ModelsError(
            "server_error",
            f"{where.url} sent an event that is not JSON: {scrubbed(data, headers)[:200]!r}. "
            "Send the message again.",
        ) from None
    if not isinstance(event, dict):
        raise ModelsError(
            "server_error",
            f"{where.url} sent an event that is not a JSON object: {scrubbed(data, headers)[:200]!r}",
        )
    return event
