"""
MCP server exposing the CoachLenz Operator read-only tools to any MCP client
(Claude, Cursor, ChatGPT). Stdio transport. Every tool is read-only and safe.

Run:  python -m backend.mcp_server.server   (requires `pip install mcp`)
Discoverable via backend/mcp_server/server-card.json and mcp.json at the repo root,
and named in AGENTS.md. It reuses backend/agent/tools.py, so the MCP surface can never
diverge from the in-app agent's tools.
"""
import asyncio
import json

from backend.agent import tools as toolkit


def _build():
    # Imported lazily so the module is importable (for discovery/tests) even when the
    # optional `mcp` package is not installed.
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool as MCPTool, TextContent

    server = Server("coachlenz-operator")

    @server.list_tools()
    async def list_tools():
        return [MCPTool(name=t.name, description=t.description, inputSchema=t.input_schema)
                for t in toolkit.TOOLS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        from backend.models.base import AsyncSessionLocal
        tool = toolkit.by_name(name)
        if tool is None:
            return [TextContent(type="text", text="Error: unknown tool")]
        try:
            async with AsyncSessionLocal() as db:
                ctx = toolkit.ToolContext(db=db, is_admin=True)  # operator privilege
                out = await tool.handler(ctx, arguments or {})
            return [TextContent(type="text", text=json.dumps(out, default=str))]
        except Exception as e:  # honest failure, never a fabricated result
            return [TextContent(type="text", text=f"Error: {e}")]

    return server, stdio_server


async def main():
    server, stdio_server = _build()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
