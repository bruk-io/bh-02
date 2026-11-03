from claude_code.fixture_mcp import respond


def test_the_fixture_speaks_mcp_and_serves_its_payload_from_any_of_its_tools():
    init = respond(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "x"}}, "P"
    )
    assert init["result"]["protocolVersion"] == "x"
    assert respond({"jsonrpc": "2.0", "method": "notifications/initialized"}, "P") is None
    names = [
        t["name"]
        for t in respond({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, "P")["result"]["tools"]
    ]
    assert names == ["list_pods", "get_logs", "browser_snapshot", "get_figma_metadata"]
    call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "get_logs", "arguments": {}},
    }
    assert respond(call, "P")["result"]["content"] == [{"type": "text", "text": "P"}]
    bad = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "rm"}}
    assert "no tool" in respond(bad, "P")["error"]["message"]
