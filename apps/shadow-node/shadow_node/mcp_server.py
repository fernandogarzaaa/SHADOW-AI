"""Shadow frontier-router MCP server (stdio).

Exposes Shadow's hybrid local+frontier routing as Model Context Protocol tools so
any MCP client (Claude Desktop, Claude Code, other agents) can route prompts
through Shadow to save frontier tokens.

Run:  python -m shadow_node.mcp_server
The heavy ``mcp`` dependency is imported here only — the FastAPI node never loads it.
"""
from __future__ import annotations
import json

from .mcp_tools import RouteEngine

try:
    import anyio
    from mcp.server import Server
    from mcp.server.context import ServerRequestContext
    from mcp.server.stdio import stdio_server
    import mcp.types as types
except ImportError as e:  # pragma: no cover - exercised only without the extra installed
    raise SystemExit("The MCP server requires the 'mcp' package. Install it with: pip install mcp") from e


def build_server(engine: RouteEngine | None = None) -> "Server":
    engine = engine or RouteEngine()
    tools = [
        types.Tool(
            name=s["name"],
            description=s["description"],
            inputSchema=s["schema"],
            annotations=types.ToolAnnotations(**s["annotations"]) if s.get("annotations") else None,
        )
        for s in engine.tool_specs()
    ]

    # MCP 2.x uses constructor-based handler registration; the v1
    # @server.list_tools() / @server.call_tool() decorators were removed.
    async def _list_tools(
        ctx: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def _call_tool(
        ctx: ServerRequestContext, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        result = engine.dispatch(params.name, params.arguments)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(result, default=str))]
        )

    return Server(
        "shadow-router",
        on_list_tools=_list_tools,
        on_call_tool=_call_tool,
    )


def main() -> None:
    server = build_server()

    async def _run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(_run)


if __name__ == "__main__":
    main()
