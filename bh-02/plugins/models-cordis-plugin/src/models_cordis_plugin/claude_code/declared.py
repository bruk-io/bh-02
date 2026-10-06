"""bh-02's tool as Claude Code sees it: declared through an in-process MCP server, never run there.

Claude Code is told about the tool the loop offers (`server_for`: the kernel's `python`), and when
the model calls it Claude Code calls the server, which runs nothing: the call parks
(`Parking.wait`) until `agent:loop` has run it as an input in the kernel and the next request
brings its result (`Parking.deliver`).
A result can arrive before Claude Code gets round to the call; it waits for it. Every exit
answers what is parked ("resolve, never reject"): a call Claude Code waits on forever would hold
its process.

Calls pair by id: Claude Code puts the model's `tool_use` id in the MCP request's `_meta`
(`claudecode/toolUseId`), undocumented but seen on every call (README.md).

The server is the MCP library's own low-level `Server`, not the SDK's `create_sdk_mcp_server`,
which validates the input against the schema and answers a bad call itself: Claude Code would
then carry on to its next step without the loop.

`permission_for` is the second wall: Claude Code runs no built-in tool (`tools=[]`) and loads no
other server (`strict_mcp_config`), and anything that is not the declared tool
(`mcp__bh__python`) is denied without asking.
"""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any, Final

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext
from claude_agent_sdk.types import CanUseTool, McpSdkServerConfig, PermissionResult
from mcp.server import Server
from mcp.server.context import ServerRequestContext
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from models_cordis_plugin.claude_code.stream import SERVER, plain_name

__all__ = ["CALL_ID", "Parking", "permission_for", "server_for"]

type Json = Mapping[str, Any]

CALL_ID: Final = "claudecode/toolUseId"  # where Claude Code puts the model's tool_use id
# Each tool's `_meta`: a result as large as the loop sends reaches the model whole, rather than
# being saved to a file the model has no tool to read (measured at 155k and 520k characters),
# and the tool is always in the prompt, never deferred behind a search.
_META: Final[Mapping[str, Any]] = {"anthropic/maxResultSizeChars": 2_000_000, "anthropic/alwaysLoad": True}
_UNPAIRED: Final = (
    "bh-02 could not pair this call with the model's tool_use (Claude Code sent no "
    f"`{CALL_ID}`), so it did not run. This Claude Code version is not the one bh-02 pins; "
    "run `uv sync --all-packages`."
)


class Parking:
    """Calls Claude Code is waiting on, by tool_use id, and results that came before their call."""

    def __init__(self) -> None:
        self._waiting: dict[str, asyncio.Future[str]] = {}
        self._early: dict[str, str] = {}
        self.called: set[str] = set()  # every call Claude Code made through the server

    @property
    def waiting(self) -> tuple[str, ...]:
        """The ids of the calls parked now."""
        return tuple(self._waiting)

    async def wait(self, call_id: str) -> str:
        """The result for `call_id`, when the loop delivers it (at once, if it already has)."""
        self.called.add(call_id)
        if call_id in self._early:
            return self._early.pop(call_id)
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._waiting[call_id] = future
        try:
            return await future
        finally:
            self._waiting.pop(call_id, None)

    def deliver(self, call_id: str, result: str) -> None:
        """Answer `call_id`, now if it is parked, else when Claude Code calls it."""
        future = self._waiting.get(call_id)
        if future is not None and not future.done():
            future.set_result(result)
        else:
            self._early[call_id] = result

    def release(self, result: str) -> None:
        """Answer every parked call with `result`, and forget results nobody asked for."""
        for future in self._waiting.values():
            if not future.done():
                future.set_result(result)
        self._early.clear()


def _declared(spec: Json) -> Tool:
    return Tool.model_validate(
        {
            "name": str(spec["name"]),
            "description": str(spec.get("description") or ""),
            "inputSchema": dict(spec.get("parameters") or {"type": "object"}),
            "_meta": dict(_META),
        }
    )


def server_for(specs: Sequence[Json], parking: Parking) -> McpSdkServerConfig:
    """The tools `specs` declares, as the in-process MCP server Claude Code is given."""
    tools = [_declared(spec) for spec in specs]

    async def list_tools(
        ctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=tools)

    async def call_tool(ctx: ServerRequestContext[Any], params: CallToolRequestParams) -> CallToolResult:
        call_id = (params.meta or {}).get(CALL_ID)
        text = await parking.wait(str(call_id)) if call_id else _UNPAIRED
        return CallToolResult(content=[TextContent(type="text", text=text)])

    server: Server[Any] = Server(SERVER, version="1", on_list_tools=list_tools, on_call_tool=call_tool)
    return McpSdkServerConfig(type="sdk", name=SERVER, instance=server)


def permission_for(names: frozenset[str]) -> CanUseTool:
    """Claude Code's permission callback: a declared tool (`mcp__bh__<name>`) is allowed, since
    the loop decides when it runs it; anything else is denied without asking."""

    async def can_use(name: str, input: dict[str, Any], context: ToolPermissionContext) -> PermissionResult:
        if name != plain_name(name) and plain_name(name) in names:
            return PermissionResultAllow()
        return PermissionResultDeny(
            message=f"{name} is not bh-02's tool, so it is denied without asking; "
            "act through the tool you were given"
        )

    return can_use
