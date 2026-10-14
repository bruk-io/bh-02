"""What an endpoint's `GET /models` says, read as the models `ENDPOINT/ID` can name: pure."""

import json

import pytest

from models_cordis_plugin.openai.listing import (
    KEPT,
    SHOWN,
    Down,
    Listed,
    Reply,
    Unlisted,
    cleaned,
    matching,
    models_url,
    notes,
    read_listing,
    usable,
)


def _reply(*ids: object, status: int = 200) -> Reply:
    data = [{"id": i, "object": "model"} for i in ids]
    return Reply(status, json.dumps({"object": "list", "data": data}).encode())


def test_the_models_url_is_the_base_url_and_models() -> None:
    assert models_url("http://localhost:11434/v1") == "http://localhost:11434/v1/models"
    assert models_url("https://openrouter.ai/api/v1/") == "https://openrouter.ai/api/v1/models"


@pytest.mark.parametrize(
    "id",
    ["qwen2.5-coder:7b", "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", "q4_k_m@lm", "~a/b:free", "/models/x.gguf"],
)
def test_an_id_of_printable_ascii_is_a_name_as_it_is(id: str) -> None:
    assert usable(id) == id


@pytest.mark.parametrize(
    "id",
    [
        "",
        "has a space",
        "caf" + chr(0xE9),  # not ASCII
        chr(0x1F999),  # outside the Basic Multilingual Plane: format_layer would write invalid TOML for it
        "line" + chr(0x2028) + "break",
        "x" * 201,
    ],
)
def test_an_id_that_is_not_a_name_here_is_not_listed(id: str) -> None:
    assert usable(id) is None


def test_control_characters_are_stripped_before_an_id_is_judged() -> None:
    assert usable("qwen\x1b[2Jcoder") == "qwen[2Jcoder"
    assert usable("a\x07b\x7fc\x85d") == "abcd"  # BEL, DEL, a C1 control
    assert usable("tab\there") == "tabhere"  # a tab is a control character; the space it stood for is gone
    assert usable("\x1b\x07") is None  # nothing is left
    assert usable("x" * 200) == "x" * 200
    assert cleaned("a\x00b\x9fc\nd") == "abcd"


def test_a_list_is_its_usable_ids_sorted_each_once_and_the_rest_counted() -> None:
    got = read_listing(_reply("b-model", "a-model", "b-model", "has space", "café", ""))
    assert got == Listed(("a-model", "b-model"), skipped=3)  # a repeat is not skipped, it is one model


def test_what_is_not_an_id_is_skipped_and_counted() -> None:
    body = json.dumps({"data": [{"id": "ok"}, {"id": 5}, {"name": "x"}, "str", None]}).encode()
    assert read_listing(Reply(200, body)) == Listed(("ok",), skipped=4)


def test_a_list_longer_than_kept_is_cut_and_the_cut_counted() -> None:
    ids = [f"m{n:05d}" for n in range(KEPT + 7)]
    got = read_listing(_reply(*ids))
    assert isinstance(got, Listed) and len(got.ids) == KEPT and got.cut == 7
    assert got.ids[0] == "m00000" and got.ids[-1] == f"m{KEPT - 1:05d}"


@pytest.mark.parametrize(
    ("got", "said"),
    [
        (Down("no answer within 6 s"), "no answer within 6 s"),
        (
            Reply(401, b'{"error": "key sk-secret rejected"}'),
            "HTTP 401: it wants a key, or refused the one named",
        ),
        (Reply(403, b""), "HTTP 403"),
        (Reply(404, b"<html>"), "HTTP 404: it has no /models"),
        (Reply(302, b""), "a redirect, which is not followed"),
        (Reply(500, b"boom"), "HTTP 500"),
        (Reply(200, b"not json"), "not an OpenAI model list"),
        (Reply(200, b"[1, 2]"), "not an OpenAI model list"),
        (Reply(200, b'"text"'), "not an OpenAI model list"),
        (Reply(200, b'{"data": "no"}'), "not an OpenAI model list"),
        (Reply(200, b"\xff\xfe"), "not an OpenAI model list"),
    ],
)
def test_no_list_says_why_and_never_quotes_what_the_server_sent(got: Reply | Down, said: str) -> None:
    out = read_listing(got)
    assert isinstance(out, Unlisted) and said in out.why
    assert "sk-secret" not in out.why and "<html>" not in out.why and "boom" not in out.why


def test_include_keeps_the_ids_matching_any_pattern_by_glob_case_sensitively() -> None:
    ids = ("Qwen/Qwen2.5-Coder:7b", "llama3.2:latest", "qwen2.5-coder:7b", "qwen3:30b", "mistral")
    assert matching(ids, ()) == ids  # no include: all of them
    assert matching(ids, ["qwen*"]) == ("qwen2.5-coder:7b", "qwen3:30b")  # case-sensitive
    assert matching(ids, ["qwen*", "*:latest"]) == ("llama3.2:latest", "qwen2.5-coder:7b", "qwen3:30b")
    assert matching(ids, ["*/*"]) == ("Qwen/Qwen2.5-Coder:7b",)  # `*` crosses `/` and `:`
    assert matching(ids, ["qwen?:[0-9]*b"]) == ("qwen3:30b",)
    assert matching(ids, ["nothing"]) == ()


def test_the_notes_say_what_an_endpoint_leaves_out_one_line_each() -> None:
    url = "http://h/v1/models"
    assert notes(url, None, ()) == ()  # never asked: nothing to say
    assert notes(url, Unlisted("can't connect: refused; is the server running?"), ()) == (
        "no list from http://h/v1/models (can't connect: refused; is the server running?); "
        "its models are not listed",
    )
    assert notes(url, Listed(("a", "b")), ()) == ()  # everything shown, nothing to say
    assert notes(url, Listed(()), ()) == ("its server lists no models",)
    assert notes(url, Listed(("a", "b")), ["z*"]) == ("none of its 2 models matches include = ['z*']",)
    many = Listed(tuple(f"m{n:04d}" for n in range(SHOWN + 5)))
    assert notes(url, many, ()) == ('5 more not shown; narrow them with include = ["qwen*"]',)
    left_out = notes(url, Listed(("a",), skipped=2, cut=3), ())
    assert [line.split(" ")[0] for line in left_out] == ["2", "3"]
    assert "printable ASCII without a space" in left_out[0] and "first 2000" in left_out[1]
