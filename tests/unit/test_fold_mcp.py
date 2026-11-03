"""The fold MCP server's replies, with the file reading faked."""

from claude_code.fold_mcp import respond


def _call(arguments: dict, fold) -> dict:
    request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "fold", "arguments": arguments},
    }
    return respond(request, fold)


def test_the_server_lists_one_tool_and_folds_what_it_is_asked_for():
    init = respond(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "x"}}, None
    )
    assert init["result"]["protocolVersion"] == "x"
    assert respond({"jsonrpc": "2.0", "method": "notifications/initialized"}, None) is None
    tools = respond({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, None)["result"]["tools"]
    assert [t["name"] for t in tools] == ["fold"] and tools[0]["inputSchema"]["required"] == ["path"]
    asked = []
    reply = _call({"path": "/a.py", "query": "close"}, lambda *a: asked.append(a) or "[fold: code]")
    assert asked == [("/a.py", 2000, "close")]
    assert reply["result"] == {"content": [{"type": "text", "text": "[fold: code]"}], "isError": False}


def test_a_file_it_cannot_fold_is_an_error_the_model_can_read_and_a_missing_path_is_refused():
    def missing(*_):
        raise FileNotFoundError("[Errno 2] No such file or directory: '/nope.py'")

    reply = _call({"path": "/nope.py"}, missing)
    assert reply["result"]["isError"] and "No such file" in reply["result"]["content"][0]["text"]
    assert "fold needs a path" in _call({}, missing)["error"]["message"]
    bad = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "rm"}}
    assert "this server has fold" in respond(bad, missing)["error"]["message"]
