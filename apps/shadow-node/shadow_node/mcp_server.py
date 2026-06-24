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
    from mcp.server.stdio import stdio_server
    import mcp.types as types
except ImportError as e:  # pragma: no cover - exercised only without the extra installed
    raise SystemExit("The MCP server requires the 'mcp' package. Install it with: pip install mcp") from e


def build_server(engine: RouteEngine | None = None) -> "Server":
    engine = engine or RouteEngine()
    server = Server("shadow-router")
    tools = [
        types.Tool(name=s["name"], description=s["description"], inputSchema=s["schema"])
        for s in engine.tool_specs()
    ]

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        result = engine.dispatch(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    return server


def main() -> None:
    server = build_server()

    async def _run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(_run)


if __name__ == "__main__":
    main()
