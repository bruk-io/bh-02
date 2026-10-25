"""Model discovery over real sockets and httpx2: the `Get` the catalog really uses, against the stand-in
server: what it asks, how it fails, that it does not block the event loop, and that the model row
never asks at all."""

import asyncio
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import httpx2
import pytest

from models_cordis_plugin import Catalog, ModelConfig, Switch, SwitchConfig, opened, set_model
from models_cordis_plugin.openai import Down, Reply, discovery, httpx_get
from models_cordis_plugin.openai.listing import BODY_LIMIT
from models_cordis_plugin.openai.testing import StubServer

_KEY = "sk-live-0123456789abcdef"


@dataclass
class _Entry:
    id: str
    use: str | None
    config: dict[str, Any]


class _Loader:
    def __init__(self, *entries: _Entry) -> None:
        self.entries_now = list(entries)

    def entries(self) -> list[_Entry]:
        return self.entries_now

    def status(self) -> dict[str, str]:
        return {}

    async def reload(self) -> None:
        pass


class _Jobs:
    def put(self, job: Any, failed: Any) -> None:
        pass


@pytest.fixture(autouse=True)
def _own_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


def _endpoint(tmp_path: Path, base_url: str, key: str | None = None) -> str:
    """A models file naming `base_url` as the endpoint `local`, whose key (when `key`) is the
    environment variable LOCAL_KEY; its path."""
    extra = 'key = { env = "LOCAL_KEY" }\n' if key else ""
    path = tmp_path / "models.toml"
    path.write_text(f'[local]\nprovider = "openai"\ndiscover = true\nbase_url = "{base_url}"\n{extra}')
    return str(path)


def _catalog(tmp_path: Path, base_url: str, *, get: Any = httpx_get, key: str | None = None) -> Catalog:
    """The catalog over that file; `key` makes the endpoint read the variable LOCAL_KEY (the test sets it)."""
    row: dict[str, Any] = {"models": _endpoint(tmp_path, base_url, key)}
    return Catalog(_Loader(_Entry("model", "models:model", row)), get=get)


def _names(catalog: Catalog) -> list[str]:
    return [m["name"] for m in catalog.listed() if "/" in m["name"]]


async def test_the_real_get_lists_what_a_server_serves(tmp_path: Path) -> None:
    with StubServer(models=["qwen2.5-coder:7b", "Qwen/Q:7b"]) as server:
        catalog = _catalog(tmp_path, server.base_url)
        await catalog.refresh()
    assert _names(catalog) == ["local/Qwen/Q:7b", "local/qwen2.5-coder:7b"]
    assert [(r["method"], r["path"]) for r in server.requests] == [("GET", "/v1/models")]  # one request


async def test_the_key_is_sent_in_the_header_only_and_a_wrong_one_says_so_without_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_KEY", _KEY)
    with StubServer(key=_KEY, models=["m"]) as server:
        good = _catalog(tmp_path, server.base_url, key=_KEY)
        await good.refresh()
        assert _names(good) == ["local/m"]
        (request,) = server.requests
        assert request["authorization"] == f"Bearer {_KEY}" and _KEY not in request["path"]
    other = tmp_path / "other"
    other.mkdir()
    with StubServer(key="sk-another-0000", models=["m"]) as server:
        wrong = _catalog(other, server.base_url, key=_KEY)
        said = str(await _switch(other, wrong).run(""))
    assert _names(wrong) == [] and "HTTP 401: it wants a key, or refused the one its `key` gives" in said
    assert _KEY not in said and "cdef" not in said


async def test_a_key_that_cannot_go_in_a_header_is_one_line_under_the_list_and_asks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-0095: a header carries printable ASCII; httpx2 raises `UnicodeEncodeError` for anything else,
    which `/model` used to let out. The endpoint says why instead (never the key), and the server is
    not asked."""
    for n, key in enumerate(("sk-caf" + chr(0xE9) + "-0123", "sk-tab\there")):
        directory = tmp_path / f"key{n}"
        directory.mkdir()
        monkeypatch.setenv("LOCAL_KEY", key)
        with StubServer(models=["m"]) as server:
            catalog = _catalog(directory, server.base_url, key=key)
            said = str(await _switch(directory, catalog).run(""))  # nothing raises out of /model
        (line,) = [s for s in said.splitlines() if s.startswith("  local: ")]
        assert line == (
            f"  local: no list from {server.base_url}/models (model 'local''s key from the environment "
            "variable LOCAL_KEY holds a character a request header can't carry (a key is one line of "
            "printable ASCII). Check what the variable holds, fix it, then try again.); "
            "its models are not listed"
        )
        assert key not in said and _names(catalog) == [] and server.requests == []


def _switch(tmp_path: Path, catalog: Catalog) -> Switch:
    layer = tmp_path / "session.toml"
    layer.write_text('[[plugin]]\nid = "model"\n')
    return Switch(_Loader(), catalog, SwitchConfig(layer=str(layer)), _Jobs(), set_model)


async def test_an_unreachable_endpoint_is_one_line_within_the_deadline_never_an_error(tmp_path: Path) -> None:
    with StubServer() as server:
        url = server.base_url
    catalog = _catalog(tmp_path, url)  # the server is gone: nothing listens on its port
    started = time.monotonic()
    said = str(await _switch(tmp_path, catalog).run("")).splitlines()
    assert time.monotonic() - started < 6
    (line,) = [s for s in said if s.startswith("  local: ")]
    assert line.startswith(f"  local: no list from {url}/models (can't connect: ")
    assert line.endswith("; is the server running?); its models are not listed")


async def test_a_server_that_does_not_answer_in_time_is_said_at_the_deadline(tmp_path: Path) -> None:
    with StubServer(models=["m"], delay=1.0) as server:
        catalog = _catalog(tmp_path, server.base_url, get=partial(httpx_get, deadline=0.3))
        started = time.monotonic()
        await catalog.refresh()
        took = time.monotonic() - started
    assert took < 0.9  # the deadline, not the server's second
    assert catalog.endpoints()[0]["notes"] == [
        f"no list from {server.base_url}/models (no answer within 0.3 s); its models are not listed"
    ]


async def test_asking_a_slow_server_does_not_block_the_event_loop(tmp_path: Path) -> None:
    """A TUI shares the loop: a ticker keeps ticking while `/model` waits for a server."""
    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    with StubServer(models=["m"], delay=0.6) as server:
        catalog = _catalog(tmp_path, server.base_url)
        ticker = asyncio.create_task(tick())
        try:
            await catalog.refresh()
        finally:
            ticker.cancel()
    assert _names(catalog) == ["local/m"]
    assert ticks >= 25  # about 60 passes of the event loop in 0.6 s; a blocking call would leave a handful


def _mock(handler: Any) -> Any:
    return partial(httpx_get, transport=httpx2.MockTransport(handler))


async def test_a_redirect_is_not_followed_so_a_key_never_goes_anywhere_else() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(302, headers={"Location": "http://elsewhere.example/v1/models"})

    got = await _mock(handler)("http://h/v1/models", {"Authorization": f"Bearer {_KEY}"})
    assert got == Reply(302, b"") and [r.url.host for r in seen] == ["h"]  # one request, to its base_url


async def test_an_answer_over_the_limit_is_not_read_whole_and_a_failure_status_has_no_body_read() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/big":
            return httpx2.Response(200, content=b"x" * (BODY_LIMIT + 10))
        return httpx2.Response(500, content=b"secret " + _KEY.encode())

    get = _mock(handler)
    assert await get("http://h/big", {}) == Down("its answer is over 1 MiB, more than a model list is")
    assert await get("http://h/err", {}) == Reply(500, b"")  # a body is never quoted, so never read


async def test_the_body_limit_is_checked_before_a_chunk_is_held_so_never_more_than_the_limit_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-0095: an answer just over the limit is a `Down` either way, so what tells the checks apart is
    what was held: the buffer's size after each chunk it took. A test double for the buffer records it."""
    held: list[int] = []

    class _Buffer(bytearray):
        def __iadd__(self, chunk: Any) -> Any:
            held.append(len(self) + len(chunk))
            return super().__iadd__(chunk)

    monkeypatch.setattr(discovery, "bytearray", _Buffer, raising=False)  # the name `httpx_get` builds it by

    def answer(size: int) -> Any:
        async def chunks() -> Any:  # two chunks, the first just short of the limit
            yield b"x" * (BODY_LIMIT - 10)
            yield b"y" * (size - (BODY_LIMIT - 10))

        return _mock(lambda request: httpx2.Response(200, content=chunks()))

    assert await answer(BODY_LIMIT + 1)("http://h/v1/models", {}) == Down(
        "its answer is over 1 MiB, more than a model list is"
    )
    assert held and max(held) <= BODY_LIMIT  # the second chunk was refused, not taken and then counted
    held.clear()
    got = await answer(BODY_LIMIT)("http://h/v1/models", {})  # exactly the limit is still an answer
    assert isinstance(got, Reply) and len(got.body) == BODY_LIMIT and max(held) == BODY_LIMIT


async def test_a_request_that_fails_is_a_down_with_no_key_in_it() -> None:
    def refused(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"all connection attempts failed for {_KEY}")

    got = await _mock(refused)("http://h/v1/models", {"Authorization": f"Bearer {_KEY}"})
    assert isinstance(got, Down) and got.why.startswith("can't connect: ") and _KEY not in got.why


async def test_the_model_row_binds_an_endpoint_s_model_and_runs_a_step_with_no_listing_asked(
    tmp_path: Path,
) -> None:
    """`local/x:7b` is the model with no network call but the step's own: the server is asked the one
    chat completion, never for its list."""
    with StubServer(models=["something-else"]) as server:
        config = ModelConfig(default="local/x:7b", models=_endpoint(tmp_path, server.base_url))
        async with opened(config) as model:
            chunks = [c async for c in model.complete([{"role": "user", "content": "hi"}], [])]
        assert any(c.get("type") == "text" for c in chunks)
    assert [(r["method"], r["path"]) for r in server.requests] == [("POST", "/v1/chat/completions")]
    assert server.requests[0]["body"]["model"] == "x:7b"  # the id, as the model's id in the body
