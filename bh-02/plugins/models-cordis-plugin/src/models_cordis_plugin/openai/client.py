"""The `openai` provider: one model on an OpenAI-compatible endpoint, as a `model` value.

Each step is one streamed POST to `<base_url>/chat/completions` (`wire.py` builds it and
folds what comes back). A model's `key` names a line of `local.env`, read when a request is
made and put only in that request's `Authorization` header: never in an environment, never in
anything whose repr shows it, and taken out of anything the server says back before an error
quotes it. A model with no key sends none (a local server). Usage is asked for
(`stream_options`) until the server refuses a step for it; that step is sent again without it,
and so is every later one. Closing the step (the person stopped the reply) closes the HTTP
stream with it.
"""

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from contextlib import aclosing
from pathlib import Path
from typing import Any, Final

import httpx2

from models_cordis_plugin.local_env import ENV_FILE, parse_env, token_file
from models_cordis_plugin.named import ModelsError, Named, key_name
from models_cordis_plugin.openai.wire import (
    Fold,
    Where,
    http_error,
    rejects_usage,
    request_for,
    scrubbed,
    sse_data,
    stream_error,
)

__all__ = ["OpenAIModel", "authorization", "missing_key"]

type Json = Mapping[str, Any]

# Connecting is quick or it fails; a local model can take minutes to its first token.
_TIMEOUT: Final = httpx2.Timeout(connect=10.0, read=None, write=60.0, pool=10.0)
_DONE: Final = "[DONE]"


class _Headers(dict[str, str]):
    """A request's headers: a dict whose repr names its keys, never a value (the key)."""

    def __repr__(self) -> str:
        return f"_Headers({sorted(self)!r})"

    __str__ = __repr__


def authorization(named: Named, env_file: str | None) -> dict[str, str]:
    """The request's headers: JSON, and `Authorization: Bearer <key>` when the model names a
    key, read from local.env now. A key named but not there is a `ModelsError` saying where
    to put it."""
    headers = _Headers({"Content-Type": "application/json", "Accept": "text/event-stream"})
    if named.table.get("key") is None:
        return headers
    key = key_name(named.table["key"])
    if key is None:  # never quoted: it may be the key itself (`named.problem` says so first)
        raise ModelsError(
            "model_config",
            f"model {named.name!r}: key must name a line of local.env (like OPENAI_API_KEY), not hold "
            "the key itself; move the key into local.env and name that line",
        )
    path = token_file(env_file)
    # read into the header at once: no local of this frame holds the key (a crash prints locals)
    headers["Authorization"] = "Bearer " + (
        parse_env(path.read_text(encoding="utf-8")).get(key, "")
        if path is not None and path.is_file()
        else ""
    )
    if headers["Authorization"] == "Bearer ":
        raise ModelsError(
            "authentication_failed", _no_key_line(named.name, key, path) + " then send the message again."
        )
    return headers


def _no_key_line(name: str, key: str, path: Path | None) -> str:
    where = str(path) if path is not None else f"{ENV_FILE} at the repository root"
    return (
        f"model {name!r} names the key {key}, which is not a line of {where}. Add "
        f"`{key}=<the key>` there (keep that file out of git),"
    )


def missing_key(named: Named, env_file: str | None) -> str | None:
    """Why `named`'s key can't be sent (it names a line local.env doesn't have), said so the
    person can fix it; None when the model names no key or the line is there. Never quotes
    the key: it only asks whether the line is there."""
    key = key_name(named.table.get("key"))
    if key is None:
        return None
    path = token_file(env_file)
    if path is not None and path.is_file() and parse_env(path.read_text(encoding="utf-8")).get(key):
        return None
    return _no_key_line(named.name, key, path) + f" then /model {named.name} again."


class OpenAIModel:
    """The `model` value over one OpenAI-compatible model (module docstring). An async context
    manager: its HTTP client is closed when the row leaves."""

    def __init__(
        self, named: Named, env_file: str | None = None, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self._named = named
        self._env_file = env_file
        self._client = httpx2.AsyncClient(timeout=_TIMEOUT, transport=transport)
        url = str(named.table["base_url"]).rstrip("/") + "/chat/completions"
        self._where = Where(named.name, url, named.id, key_name(named.table.get("key")), named.source)
        self._usage = True  # whether to ask for usage: until the server refuses it (`rejects_usage`)

    async def __aenter__(self) -> OpenAIModel:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
        """Stream one step's chunks (CONTRACTS.md: chunk)."""
        where = self._where
        try:
            headers = authorization(self._named, self._env_file)
            for usage in (True, False) if self._usage else (False,):
                body = request_for(self._named.id, messages, tools, self._named.table, usage=usage)
                async with self._client.stream("POST", where.url, json=body, headers=headers) as response:
                    if response.status_code >= 400:
                        said = (await response.aread()).decode("utf-8", errors="replace")
                        if usage and rejects_usage(response.status_code, scrubbed(said, headers)):
                            self._usage = False  # asked again without it, now and from now on
                            continue
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
