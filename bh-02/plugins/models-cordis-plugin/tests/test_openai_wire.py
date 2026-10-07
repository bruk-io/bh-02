"""The OpenAI-compatible API's request and stream, mapped to the `model` contract and back: pure."""

import json

import pytest

from models_cordis_plugin.openai import (
    Fold,
    Where,
    http_error,
    rejects_usage,
    replayed,
    request_for,
    sse_data,
    stop_for,
    stream_error,
)

_TOOL = {"name": "python", "description": "run it", "parameters": {"type": "object", "properties": {}}}
_WHERE = Where("local", "http://h/v1/chat/completions", "llama3.2", None, "/c/models.toml")


def test_the_request_streams_with_usage_offers_the_tool_and_sends_only_the_settings_given() -> None:
    body = request_for(
        "llama3.2",
        [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}],
        [_TOOL],
        {},
    )
    assert body == {
        "model": "llama3.2",
        "messages": [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "python",
                    "description": "run it",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    }
    tuned = request_for("m", [], [], {"max_tokens": 99, "temperature": 0.1, "key": "K", "provider": "openai"})
    assert tuned["max_tokens"] == 99 and tuned["temperature"] == 0.1 and "tools" not in tuned
    assert "key" not in tuned and "provider" not in tuned  # the table's other settings stay home


def test_a_tool_result_and_a_feedback_line_go_back_in_the_api_s_shape() -> None:
    assert replayed({"role": "tool", "content": "42\n", "call_id": "call_1"}) == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "42\n",
    }
    assert replayed({"role": "user", "content": "try again", "feedback": "silent"}) == {
        "role": "user",
        "content": "try again",
    }
    dated = "(Today's date: 2026-10-07.)\n\nhi"  # the loop's own field is not the API's
    assert replayed({"role": "user", "content": dated, "today": "2026-10-07"}) == {
        "role": "user",
        "content": dated,
    }


def test_this_api_s_own_message_is_replayed_as_it_came_and_another_provider_s_is_rebuilt() -> None:
    own = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "python", "arguments": '{"code": "1"}'}}
        ],
    }
    calls = [{"id": "call_1", "name": "python", "input": {"code": "1"}}]
    assert replayed({"role": "assistant", "content": "", "tool_calls": calls, "provider": own}) == own
    claude = {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "toolu_1", "name": "mcp__bh__python", "input": {}}],
    }
    rebuilt = replayed(
        {
            "role": "assistant",
            "content": "ok",
            "tool_calls": [{"id": "toolu_1", "name": "python", "input": {"code": "2"}}],
            "provider": claude,
        }
    )
    assert rebuilt == {
        "role": "assistant",
        "content": "ok",
        "tool_calls": [
            {
                "id": "toolu_1",
                "type": "function",
                "function": {"name": "python", "arguments": '{"code": "2"}'},
            }
        ],
    }
    ollama = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "python", "arguments": {"code": "3"}}}],
    }
    assert (
        replayed(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c", "name": "python", "input": {"code": "3"}}],
                "provider": ollama,
            }
        )["tool_calls"][0]["function"]["arguments"]
        == '{"code": "3"}'
    )
    assert replayed({"role": "assistant", "content": "[stopped]"}) == {
        "role": "assistant",
        "content": "[stopped]",
    }


def test_text_streams_as_it_comes_and_the_end_is_usage_stop_and_the_message() -> None:
    fold = Fold()
    assert fold.take({"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}]}) == []
    assert fold.take({"choices": [{"index": 0, "delta": {"reasoning_content": "hm"}}]}) == [
        {"type": "thinking", "text": "hm"}
    ]
    assert fold.take({"choices": [{"index": 0, "delta": {"content": "Hel"}}]}) == [
        {"type": "text", "text": "Hel"}
    ]
    assert fold.take({"choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}]}) == [
        {"type": "text", "text": "lo"}
    ]
    usage = {"prompt_tokens": 10, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": 4}}
    assert fold.take({"choices": [], "usage": usage}) == []
    assert fold.finish() == [
        {"type": "usage", "input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 4},
        {"type": "stop", "reason": "stop"},
        {"type": "message", "message": {"role": "assistant", "content": "Hello"}},
    ]


def test_a_call_s_arguments_are_assembled_from_its_deltas_by_index() -> None:
    fold = Fold()
    fold.take(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_a",
                                "type": "function",
                                "function": {"name": "python", "arguments": ""},
                            }
                        ]
                    }
                }
            ]
        }
    )
    for piece in ('{"co', 'de": "pri', 'nt(1)"}'):
        assert (
            fold.take(
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": piece}}]}}]}
            )
            == []
        )
    fold.take(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": "call_b",
                                "function": {"name": "python", "arguments": '{"code": "2"}'},
                            }
                        ]
                    }
                }
            ]
        }
    )  # whole, in one
    fold.take({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]})
    first, second, stop, message = fold.finish()
    assert first == {"type": "tool_call", "id": "call_a", "name": "python", "input": {"code": "print(1)"}}
    assert second == {"type": "tool_call", "id": "call_b", "name": "python", "input": {"code": "2"}}
    assert stop == {"type": "stop", "reason": "tool_calls"}
    assert message["message"]["content"] is None
    assert [c["function"]["arguments"] for c in message["message"]["tool_calls"]] == [
        '{"code": "print(1)"}',
        '{"code": "2"}',
    ]


def test_a_call_whose_arguments_do_not_decode_carries_error_and_no_id_is_numbered() -> None:
    fold = Fold()
    fold.take(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"name": "python", "arguments": '{"code": "x'}}
                        ]
                    }
                }
            ]
        }
    )
    fold.take(
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 1, "function": {"name": "python", "arguments": "[1]"}}]}}
            ]
        }
    )
    fold.take(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 2, "function": {"name": "python", "arguments": {"code": "3"}}}
                        ]
                    }
                }
            ]
        }
    )
    broken, listed, parsed, *_ = fold.finish()
    assert (
        broken["id"] == "call_0"
        and broken["input"] == {}
        and broken["error"].startswith("arguments are not JSON")
    )
    assert listed["error"] == "arguments are not a JSON object: [1]"
    assert parsed["input"] == {"code": "3"} and "error" not in parsed  # a server that sends them parsed


def _parts(*parts: dict[str, object]) -> dict[str, object]:
    return {"choices": [{"delta": {"tool_calls": list(parts)}}]}


def test_calls_streamed_without_an_index_are_told_apart_by_their_ids() -> None:
    """Gemini's compatibility endpoint leaves `index` out: a part with a new id is a new call,
    one without an id continues the last, and a second id-less part in one delta is another."""
    fold = Fold()
    fold.take(_parts({"id": "call_a", "function": {"name": "python", "arguments": '{"code": '}}))
    fold.take(_parts({"function": {"arguments": '"a"}'}}))
    fold.take(_parts({"id": "call_b", "function": {"name": "python", "arguments": '{"code": "b"}'}}))
    fold.take(
        _parts(
            {"id": "call_c", "function": {"name": "python", "arguments": '{"code": "c"}'}},
            {"function": {"name": "python", "arguments": '{"code": "d"}'}},
        )
    )
    calls = [c for c in fold.finish() if c["type"] == "tool_call"]
    assert [(c["id"], c["input"]) for c in calls] == [
        ("call_a", {"code": "a"}),
        ("call_b", {"code": "b"}),
        ("call_c", {"code": "c"}),
        ("call_3", {"code": "d"}),
    ]
    assert not any("error" in c for c in calls)


def test_parallel_calls_each_sent_whole_with_neither_index_nor_id_are_calls_of_their_own() -> None:
    """A server that streams each call whole in its own event, with no index and no id: a part
    naming a function after a whole call opens another; a part that only carries arguments
    still continues the last."""
    fold = Fold()
    fold.take(_parts({"function": {"name": "python", "arguments": '{"code": "a"}'}}))
    fold.take(_parts({"function": {"name": "python", "arguments": '{"code": '}}))
    fold.take(_parts({"function": {"arguments": '"b"}'}}))
    calls = [c for c in fold.finish() if c["type"] == "tool_call"]
    assert [(c["id"], c["input"]) for c in calls] == [("call_0", {"code": "a"}), ("call_1", {"code": "b"})]
    assert not any("error" in c for c in calls)


def test_usage_is_asked_for_unless_the_server_refused_it() -> None:
    assert "stream_options" not in request_for("m", [], [], {}, usage=False)
    refusal = json.dumps(
        {"detail": [{"loc": ["body", "stream_options"], "msg": "Extra inputs are not permitted"}]}
    )
    assert rejects_usage(422, refusal) and rejects_usage(400, "unknown field include_usage")
    assert not rejects_usage(422, "messages: field required") and not rejects_usage(500, refusal)


def test_a_key_the_server_echoes_back_is_never_quoted() -> None:
    """Whole (a proxy echoing the header) or masked but for its end (OpenAI's own 401), the key
    the request sent reads as `<key>`; a request that sent none quotes the server as it is."""
    key = "sk-proj-Abc123Def456Ghi789wxyz"
    sent = {"Authorization": f"Bearer {key}"}
    keyed = Where("router", "https://r/v1/chat/completions", "m", "OPENROUTER_API_KEY", "/c/models.toml")
    echoed = http_error(401, json.dumps({"error": {"message": f"bad header: Bearer {key}"}}), keyed, sent)
    masked = http_error(
        401, json.dumps({"error": {"message": "Incorrect API key provided: sk-proj-****wxyz."}}), keyed, sent
    )
    raw = http_error(502, f"<html>upstream said {key}</html>", keyed, sent)
    mid = stream_error({"message": f"proxy lost {key}"}, keyed, sent)
    for error in (echoed, masked, raw, mid):
        assert key not in error.message and "wxyz" not in error.message and "<key>" in error.message
    assert "sk-proj-****" in http_error(401, "Incorrect API key provided: sk-proj-****wxyz.", keyed).message


@pytest.mark.parametrize(
    ("finish", "stop"),
    [
        ("stop", "stop"),
        ("length", "length"),
        ("tool_calls", "tool_calls"),
        ("function_call", "tool_calls"),
        ("content_filter", "refusal"),
        (None, "stop"),
        ("eos", "eos"),
    ],
)
def test_the_finish_reason_is_a_stop_the_loop_classifies(finish: str | None, stop: str) -> None:
    assert stop_for(finish) == stop


def test_only_data_lines_are_events() -> None:
    assert sse_data('data: {"a": 1}') == '{"a": 1}' and sse_data("data: [DONE]") == "[DONE]"
    assert (
        sse_data(": OPENROUTER PROCESSING") is None and sse_data("") is None and sse_data("event: x") is None
    )


@pytest.mark.parametrize(
    ("status", "kind", "said"),
    [
        (
            401,
            "authentication_failed",
            "model 'local' sends no key; if the endpoint needs one, add `key = \"NAME\"`",
        ),
        (
            404,
            "not_found",
            "Check model 'local''s base_url (the part before /chat/completions) and its id 'llama3.2'",
        ),
        (429, "rate_limit", "Try again in a moment, or /model another model."),
        (400, "invalid_request", "The endpoint rejected the request"),
        (503, "server_error", "The server failed"),
        (418, "http_error", "HTTP 418"),
    ],
)
def test_an_http_failure_is_recoverable_and_says_what_to_do(status: int, kind: str, said: str) -> None:
    error = http_error(status, json.dumps({"error": {"message": "server words"}}), _WHERE)
    assert error.kind == kind and said in error.message
    assert error.message.startswith(f"http://h/v1/chat/completions answered HTTP {status}: server words")


def test_a_refused_key_names_its_line_of_local_env() -> None:
    keyed = Where("router", "https://r/v1/chat/completions", "m", "OPENROUTER_API_KEY", "/c/models.toml")
    error = http_error(401, "no", keyed)
    assert "check the key OPENROUTER_API_KEY in local.env" in error.message


def test_parallel_calls_a_server_sends_each_at_index_0_are_told_apart_by_their_ids() -> None:
    """Some servers stream every parallel call at index 0: a new id there opens a call of its own,
    and a later part at that index with no id continues the newest one."""
    fold = Fold()
    fold.take(_parts({"index": 0, "id": "a", "function": {"name": "python", "arguments": '{"code": "1"}'}}))
    fold.take(_parts({"index": 0, "id": "b", "function": {"name": "python", "arguments": '{"code": '}}))
    fold.take(_parts({"index": 0, "function": {"arguments": '"2"}'}}))
    first, second, *_ = fold.finish()
    assert first == {"type": "tool_call", "id": "a", "name": "python", "input": {"code": "1"}}
    assert second == {"type": "tool_call", "id": "b", "name": "python", "input": {"code": "2"}}


def test_a_call_sent_without_an_id_is_named_with_the_step_s_prefix() -> None:
    """Named `call_<ids><n>`: the client gives each step a fresh prefix, so two steps' unnamed
    calls never share an id (Claude, replaying them after /model, requires unique ids)."""
    fold = Fold(ids="s1_")
    fold.take(_parts({"index": 0, "function": {"name": "python", "arguments": '{"code": "1"}'}}))
    (call, *_) = fold.finish()
    assert call["id"] == "call_s1_0"
