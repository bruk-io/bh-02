"""The worker's pure pieces, imported directly: no process, no socket."""

import ast
import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from python_cordis_plugin import worker_argv
from python_cordis_plugin.worker import input_traceback, split_last_expression
from runner_cordis_plugin import Unjailed


def test_an_input_ending_in_an_expression_shows_it() -> None:
    body, last = split_last_expression("x = 2\nx * 21")
    assert len(body.body) == 1 and last is not None
    assert eval(compile(last, "<t>", "eval"), {"x": 2}) == 42
    body, last = split_last_expression("x = 2\nprint(x)\ny = 3")
    assert last is None and len(body.body) == 3
    assert isinstance(split_last_expression("")[0], ast.Module)


def test_a_failure_outside_any_input_keeps_every_frame() -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        shown = input_traceback(exc)
    assert "test_python_worker.py" in shown and shown.endswith("ValueError: boom")


async def _done(*codes: str) -> list[dict[str, Any]]:
    """A real worker (unjailed), sent `codes` as inputs by hand: the `done` message each ends with,
    as the host reads it off the socket."""
    short = tempfile.mkdtemp(prefix="bh-nm-", dir="/tmp")  # a socket path must fit in ~100 bytes
    endpoint = str(Path(short) / "k.sock")
    started = await Unjailed().start(worker_argv(endpoint), cwd=short, endpoint=endpoint)
    try:
        reader, writer = await asyncio.open_unix_connection(endpoint, limit=1 << 20)
        writer.write(b'{"op": "hello"}\n')
        answers: list[dict[str, Any]] = []
        async with asyncio.timeout(30):
            for code in codes:
                writer.write(json.dumps({"op": "exec", "code": code}).encode() + b"\n")
                answers.append(json.loads(await reader.readline()))
        writer.close()
        return answers
    finally:
        await started.stop()
        shutil.rmtree(short, ignore_errors=True)


async def test_a_done_lists_the_public_names_with_a_type_and_a_size() -> None:
    [done] = await _done(
        "import json\n"
        "hits = [1, 2, 3]\n"
        "pair = (1, 2)\n"
        "table = {'a': 1}\n"
        "seen = {1, 2}\n"
        "frozen = frozenset()\n"
        "text = 'x' * 1204\n"
        "one = 'x'\n"
        "blob = b'abc'\n"
        "count = 7\n"
        "nothing = None\n"
        "class Box:\n    def __init__(self, size, *, tag='t'): ...\n"
        "def edit(path, old, new='', *args): ...\n"
        "box = Box(1)\n"
    )
    assert done["names"] == [
        ["json", "module"],
        ["hits", "list, 3 items"],
        ["pair", "tuple, 2 items"],
        ["table", "dict, 1 item"],
        ["seen", "set, 2 items"],
        ["frozen", "frozenset, 0 items"],
        ["text", "str, 1,204 chars"],
        ["one", "str, 1 char"],
        ["blob", "bytes, 3 bytes"],
        ["count", "int"],
        ["nothing", "NoneType"],
        ["Box", "class (size, *, tag='t')"],
        ["edit", "function (path, old, new='', *args)"],
        ["box", "Box"],
    ]
    assert done["unlisted"] == 0


async def test_underscore_names_the_dunders_and_tools_are_left_out() -> None:
    first, second = await _done("_private = 1\n__dunder__ = 2\nvisible = 3", "tools = 5\nafter = 6")
    assert first["names"] == [["visible", "int"]]  # no `__builtins__`, `__name__`, `_private`
    # `tools` is bh-02's view when the host offers tools, left out; an input's own `tools` is a name
    assert second["names"] == [["visible", "int"], ["tools", "int"], ["after", "int"]]


async def test_no_length_repr_or_attribute_of_the_model_s_runs_to_describe_a_value() -> None:
    """Every hook below records itself in `calls` (and raises, for the ones a describer might
    call without guarding): describing the namespace must leave `calls` empty. A list subclass is
    not a built-in list, so it has no size."""
    first, second = await _done(
        "calls = []\n"
        "class Loud(list):\n"
        "    def __len__(self): calls.append('len'); raise RuntimeError('len')\n"
        "    def __repr__(self): calls.append('repr'); raise RuntimeError('repr')\n"
        "    def __str__(self): calls.append('str'); raise RuntimeError('str')\n"
        "    def __getattr__(self, name): calls.append(name); raise RuntimeError(name)\n"
        "    @property\n    def size(self): calls.append('size'); raise RuntimeError('size')\n"
        "class Odd:\n"
        "    def __len__(self): calls.append('len'); return 1\n"
        "    def __repr__(self): calls.append('repr'); return 'SECRET'\n"
        "    def __getattr__(self, name): calls.append(name); raise AttributeError(name)\n"
        "    @property\n    def __class__(self): calls.append('class'); return int\n"
        "loud, odd = Loud([1, 2]), Odd()\n"
        "calls.clear()\n",
        "print(calls)",
    )
    assert first["names"][-2:] == [["loud", "Loud"], ["odd", "Odd"]]
    assert second["output"] == "[]\n" and "SECRET" not in json.dumps(first["names"])


async def test_at_most_200_names_are_listed_and_the_rest_counted() -> None:
    [done] = await _done(
        "for i in range(250): globals()[f'v{i}'] = i\n"
        "del i\n"
        "globals()['not an identifier'] = 1\n"
        "globals()['x' * 101] = 1\n"
    )
    assert len(done["names"]) == 200 and done["names"][0] == ["v0", "int"]
    assert done["unlisted"] == 50 + 2
    assert len(json.dumps(done)) < 20_000


async def test_a_signature_is_cut_at_160_characters() -> None:
    [done] = await _done("def f(" + ", ".join(f"arg{n}" for n in range(60)) + "): ...")
    [[name, description]] = done["names"]
    assert name == "f" and description.startswith("function (arg0, arg1")
    assert len(description) == len("function ") + 160 + 1 and description.endswith("…")


async def test_a_signature_that_cannot_be_read_is_the_type_alone() -> None:
    [done] = await _done(
        "class Meta(type):\n    @property\n    def __signature__(cls): raise RuntimeError('no')\n"
        "class Hidden(metaclass=Meta): ...\n"
        "len2 = len\n"
    )
    assert done["names"] == [
        ["Meta", "class"],
        ["Hidden", "class"],
        ["len2", "builtin_function_or_method (obj, /)"],
    ]


async def test_a_large_last_expression_is_shown_cut_and_a_small_one_whole() -> None:
    """The last expression's repr is cut where it is large (`...` marks what was left out); a small
    value reads as `repr` gives it, a dict in its own order; `print` is never cut."""
    shown = [
        d["output"].rstrip("\n")
        for d in await _done(
            "list(range(1000))",
            "{str(n): n for n in range(500)}",
            "'x' * 50_000",
            "[[[[[[[[1]]]]]]]]",
            "{'b': 1, 'a': [1, 2], 'c': 'three'}",
            "(1.5, None, b'x', {3})",
            "print(list(range(1000)))",
        )
    ]
    big_list, big_dict, long_text, deep, small_dict, small_tuple, printed = shown
    assert big_list.startswith("[0, 1, 2,") and big_list.endswith("98, 99, ...]")
    assert big_dict.startswith("{'0': 0, '1': 1,") and big_dict.endswith("'49': 49, ...}")
    assert len(long_text) == 4_000 and "..." in long_text
    assert "..." in deep and len(deep) < 20
    assert small_dict == "{'b': 1, 'a': [1, 2], 'c': 'three'}"
    assert small_tuple == "(1.5, None, b'x', {3})"
    assert printed == str(list(range(1000)))
