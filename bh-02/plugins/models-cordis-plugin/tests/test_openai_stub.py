"""The openai provider against a stand-in OpenAI-compatible server on a real socket
(`models_cordis_plugin.openai.testing.StubServer`): streamed text, a python call's round trip,
a call that doesn't decode, the key from local.env, and the failures a person must read."""

import asyncio
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from models_cordis_plugin import ModelsError, Named
from models_cordis_plugin.openai import OpenAIModel
from models_cordis_plugin.openai.testing import StubServer

_TOOL = {
    "name": "python",
    "description": "run Python",
    "parameters": {"type": "object", "properties": {"code": {"type": "string"}}},
}


def _named(base_url: str, **more: Any) -> Named:
    table = {"provider": "openai", "id": "stub-1", "base_url": base_url, **more}
    return Named("stub", "openai", "stub-1", table, "/c/models.toml")


async def _step(model: OpenAIModel, messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(chunk) async for chunk in model.complete(messages, [_TOOL])]


async def test_a_reply_streams_in_pieces_with_usage_its_stop_and_its_message() -> None:
    with StubServer() as stub:
        async with OpenAIModel(_named(stub.base_url)) as model:
            chunks = await _step(
                model, [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello there"}]
            )
    texts = [c["text"] for c in chunks if c["type"] == "text"]
    assert len(texts) > 1 and "".join(texts) == "[stub-1] heard: hello there "  # streamed, not at once
    assert [c["type"] for c in chunks[-3:]] == ["usage", "stop", "message"]
    assert chunks[-3]["output_tokens"] == 7 and chunks[-2] == {"type": "stop", "reason": "stop"}
    (request,) = stub.requests
    assert request["path"] == "/v1/chat/completions" and request["authorization"] is None  # no key named
    assert request["body"]["stream"] is True and request["body"]["tools"][0]["function"]["name"] == "python"


async def test_a_python_call_round_trips_through_the_transcript() -> None:
    with StubServer() as stub:
        async with OpenAIModel(_named(stub.base_url)) as model:
            asked = [{"role": "user", "content": "call print(6 * 7)"}]
            first = await _step(model, asked)
            (call,) = [c for c in first if c["type"] == "tool_call"]
            assert call["name"] == "python" and call["input"] == {
                "code": "print(6 * 7)"
            }  # assembled from pieces
            assert first[-2] == {"type": "stop", "reason": "tool_calls"}
            message = first[-1]["message"]
            transcript = [
                *asked,
                {"role": "assistant", "content": "", "tool_calls": [call], "provider": message},
                {"role": "tool", "content": "42\n", "call_id": call["id"]},
            ]
            second = await _step(model, transcript)
    assert "".join(c["text"] for c in second if c["type"] == "text") == "the input said: 42"
    replayed = stub.requests[1]["body"]["messages"]
    assert replayed[1] == message  # the assistant turn went back as it came
    assert replayed[2] == {"role": "tool", "tool_call_id": call["id"], "content": "42\n"}


async def test_a_call_whose_arguments_do_not_decode_carries_error() -> None:
    with StubServer() as stub:
        async with OpenAIModel(_named(stub.base_url)) as model:
            chunks = await _step(model, [{"role": "user", "content": "broken call"}])
    (call,) = [c for c in chunks if c["type"] == "tool_call"]
    assert call["error"].startswith("arguments are not JSON") and call["input"] == {}


async def test_the_key_is_read_from_local_env_and_sent_only_as_the_authorization_header(
    tmp_path: Path,
) -> None:
    env = tmp_path / "local.env"
    env.write_text("STUB_KEY=sk-stand-in\n")
    with StubServer(key="sk-stand-in") as stub:
        async with OpenAIModel(_named(stub.base_url, key="STUB_KEY"), str(env)) as model:
            chunks = await _step(model, [{"role": "user", "content": "hi"}])
            assert chunks[-2]["reason"] == "stop"
            env.write_text("OTHER=1\n")  # read per request: gone now
            with pytest.raises(ModelsError) as missing:
                await _step(model, [{"role": "user", "content": "hi"}])
        async with OpenAIModel(_named(stub.base_url), str(env)) as keyless:
            with pytest.raises(ModelsError) as refused:
                await _step(keyless, [{"role": "user", "content": "hi"}])
    assert stub.requests[0]["authorization"] == "Bearer sk-stand-in"
    assert "sk-stand-in" not in str(stub.requests[0]["body"])
    # never in bh-02's environment, which the kernel's (and any child's) is made from
    assert "STUB_KEY" not in os.environ and "sk-stand-in" not in os.environ.values()
    assert missing.value.kind == "authentication_failed"
    assert missing.value.message.startswith(
        f"model 'stub' names the key STUB_KEY, which is not a line of {env}"
    )
    assert "sk-stand-in" not in missing.value.message
    assert (
        refused.value.kind == "authentication_failed"
        and "HTTP 401: Incorrect API key provided" in refused.value.message
    )
    assert "sends no key; if the endpoint needs one" in refused.value.message


async def test_a_key_the_server_echoes_back_in_its_refusal_is_not_in_the_error(tmp_path: Path) -> None:
    """A wrong key, which the stub's 401 echoes whole and masked but for its end: neither is
    in the message the conversation (and the session's events) would keep."""
    env = tmp_path / "local.env"
    env.write_text("STUB_KEY=sk-wrong-one-9f8e7d6c5b4a\n")
    with StubServer(key="sk-right") as stub:
        async with OpenAIModel(_named(stub.base_url, key="STUB_KEY"), str(env)) as model:
            with pytest.raises(ModelsError) as refused:
                await _step(model, [{"role": "user", "content": "hi"}])
    assert stub.requests[0]["authorization"] == "Bearer sk-wrong-one-9f8e7d6c5b4a"  # it was sent
    assert refused.value.kind == "authentication_failed"
    assert "Incorrect API key provided: <key> (you sent Bearer <key>)" in refused.value.message
    assert "sk-wrong-one" not in refused.value.message and "5b4a" not in refused.value.message


async def test_a_server_that_refuses_the_usage_field_is_asked_again_without_it() -> None:
    """A server forbidding fields it doesn't know (422 naming `stream_options`): the step is
    sent again without it and streams, with no usage; later steps don't ask for it at all."""
    with StubServer(strict=True) as stub:
        async with OpenAIModel(_named(stub.base_url)) as model:
            first = await _step(model, [{"role": "user", "content": "hi"}])
            second = await _step(model, [{"role": "user", "content": "again"}])
    assert "".join(c.get("text", "") for c in first) == "[stub-1] heard: hi "
    assert "usage" in [c["type"] for c in first]  # the stub sends it anyway; usage is optional
    assert "[stub-1] heard: again" in "".join(c.get("text", "") for c in second)
    asked = ["stream_options" in r["body"] for r in stub.requests]
    assert asked == [True, False, False]


@pytest.mark.parametrize(
    ("said", "kind", "text"),
    [
        ("status 429", "rate_limit", "HTTP 429: stub says status 429. Try again in a moment"),
        ("status 500", "server_error", "HTTP 500"),
        ("fail midway", "server_error", "failed mid-reply: the upstream provider went away"),
    ],
)
async def test_an_error_status_or_one_mid_stream_is_recoverable(said: str, kind: str, text: str) -> None:
    with StubServer() as stub:
        async with OpenAIModel(_named(stub.base_url)) as model:
            with pytest.raises(ModelsError) as raised:
                await _step(model, [{"role": "user", "content": said}])
    assert raised.value.kind == kind and text in raised.value.message


async def test_a_wrong_base_url_and_a_server_that_isn_t_there_say_what_to_check() -> None:
    with StubServer() as stub:
        async with OpenAIModel(_named(stub.base_url.removesuffix("/v1"))) as model:
            with pytest.raises(ModelsError) as wrong:
                await _step(model, [{"role": "user", "content": "hi"}])
        gone = stub.base_url
    async with OpenAIModel(_named(gone)) as model:
        with pytest.raises(ModelsError) as down:
            await _step(model, [{"role": "user", "content": "hi"}])
    assert (
        wrong.value.kind == "not_found"
        and "base_url (the part before /chat/completions)" in wrong.value.message
    )
    assert down.value.kind == "connection" and "Is the server running?" in down.value.message


async def test_a_base_url_a_request_can_t_go_to_is_a_models_error_not_a_crash() -> None:
    """`named.problem` refuses such a base_url first; this is the provider's own guard, for a
    `Named` made some other way: nothing httpx2 raises escapes as a bug that ends the app."""
    async with OpenAIModel(_named("http://h:notaport/v1")) as model:
        with pytest.raises(ModelsError) as raised:
            await _step(model, [{"role": "user", "content": "hi"}])
    assert raised.value.kind == "model_config"
    assert "is not a URL a request can go to" in raised.value.message
    assert "fix its base_url (/c/models.toml)" in raised.value.message


async def test_a_stopped_step_closes_its_stream() -> None:
    """The server sees the connection close part-way through the reply: the stream is not left
    open (a `ThreadingHTTPServer` would answer the next request either way)."""
    with StubServer() as stub:
        async with OpenAIModel(_named(stub.base_url)) as model:
            steps = model.complete([{"role": "user", "content": "slowly one two three four"}], [_TOOL])
            first = await anext(steps)
            await steps.aclose()  # the person stopped the reply
            for _ in range(250):  # the reply alone would take 8 seconds
                if "outcome" in stub.requests[0]:
                    break
                await asyncio.sleep(0.02)
            again = await _step(model, [{"role": "user", "content": "after"}])
    assert first["type"] == "text" and stub.requests[0].get("outcome") == "cut"
    assert "after" in "".join(c.get("text", "") for c in again)
