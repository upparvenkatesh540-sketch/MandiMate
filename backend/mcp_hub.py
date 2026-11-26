"""MCP client: starts the three servers, discovers their tools, routes calls."""
import json, os, sys
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVERS = {"inventory": "inventory_server.py", "orders": "orders_server.py",
           "notifications": "notifications_server.py"}

class MCPHub:
    def __init__(self):
        self.stack = AsyncExitStack()
        self.tools = {}   # tool name -> session (discovered, not hard-coded)

    async def start(self):
        here = os.path.dirname(os.path.abspath(__file__))
        for script in SERVERS.values():
            params = StdioServerParameters(command=sys.executable,
                args=[os.path.join(here, script)], env=dict(os.environ), cwd=here)
            read, write = await self.stack.enter_async_context(stdio_client(params))
            session = await self.stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            for t in (await session.list_tools()).tools:
                self.tools[t.name] = session

    async def stop(self):
        await self.stack.aclose()

    async def call(self, tool: str, **args) -> dict:
        if tool not in self.tools:
            raise RuntimeError(f"Unknown MCP tool: {tool}")
        res = await self.tools[tool].call_tool(tool, args)
        text = res.content[0].text if res.content else "{}"
        if res.isError:
            raise RuntimeError(text.replace("Error executing tool " + tool + ": ", ""))
        return json.loads(text)
