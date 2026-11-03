from harness.extract import NextStep, rows_from_records


def _assistant(mid: str, *blocks: dict) -> dict:
    return {"type": "assistant", "message": {"id": mid, "content": list(blocks)}}


def _result(uuid: str, tid: str, content, is_error: bool = False) -> dict:
    block = {"type": "tool_result", "tool_use_id": tid, "content": content, "is_error": is_error}
    return {"type": "user", "uuid": uuid, "message": {"content": [block]}}


def test_a_result_is_paired_with_its_call_and_the_next_assistant_message():
    records = [
        _assistant("m1", {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}),
        _result("u1", "t1", "a\nb"),
        {"type": "system"},
        _assistant("m2", {"type": "text", "text": "Two files."}),
        _assistant("m2", {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "a"}}),
        _assistant("m3", {"type": "text", "text": "not part of the step"}),
    ]
    [row] = rows_from_records(records, "s.jsonl")
    assert (row.tool_name, row.args, row.text, row.record_uuid) == ("Bash", {"command": "ls"}, "a\nb", "u1")
    assert row.next_step == NextStep("Two files.", [{"name": "Read", "input": {"file_path": "a"}}])


def test_block_content_joins_text_and_counts_images():
    content = [{"type": "text", "text": "x"}, {"type": "image", "source": {}}, {"type": "text", "text": "y"}]
    [row] = rows_from_records([_result("u", "t", content, is_error=True)], "s")
    assert (row.text, row.images, row.is_error, row.tool_name) == ("x\ny", 1, True, "?")
    assert row.next_step is None


def test_parallel_results_share_the_next_step():
    records = [
        _assistant(
            "m1",
            {"type": "tool_use", "id": "a", "name": "Grep", "input": {}},
            {"type": "tool_use", "id": "b", "name": "Glob", "input": {}},
        ),
        _result("u1", "a", "1"),
        _result("u2", "b", "2"),
        _assistant("m2", {"type": "text", "text": "done"}),
    ]
    rows = rows_from_records(records, "s")
    assert [r.tool_name for r in rows] == ["Grep", "Glob"]
    assert all(r.next_step == NextStep("done") for r in rows)
