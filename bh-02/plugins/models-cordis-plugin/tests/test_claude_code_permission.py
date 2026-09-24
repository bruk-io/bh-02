"""Claude Code's permission callback: the one declared tool is allowed, anything else denied."""

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

from models_cordis_plugin.claude_code import permission_for


async def test_only_the_declared_python_tool_is_allowed_and_nothing_else_is_asked_about() -> None:
    can_use = permission_for(frozenset({"python"}))
    context = ToolPermissionContext(signal=None, suggestions=[])
    assert isinstance(await can_use("mcp__bh__python", {"code": "1"}, context), PermissionResultAllow)
    for other in ("Bash", "Write", "python", "mcp__bh__write_file", "mcp__other__python"):
        denied = await can_use(other, {}, context)
        assert isinstance(denied, PermissionResultDeny), other
        assert "denied without asking" in denied.message
