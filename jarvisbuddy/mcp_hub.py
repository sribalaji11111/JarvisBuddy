"""Connect Jarvis to other MCP servers, so Claude can use their tools too.

List servers in ~/.jarvisbuddy/mcp_servers.json, in the same format as Claude Desktop:

    {"mcpServers": {"filesystem": {"command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/Sri/Documents"]}}}

Tools from these servers ask for a spoken yes before running, unless the server marks them
read-only.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any


def _safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64]


class McpHub:
    def __init__(self, config_file: Path, timeout: float = 60) -> None:
        self.config_file = config_file
        self.timeout = timeout
        self.tools: dict[str, tuple[Any, Any]] = {}  # api name -> (session, mcp tool)
        self.errors: list[str] = []
        self._loop = asyncio.new_event_loop()
        self._stack = AsyncExitStack()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

    @property
    def servers(self) -> dict[str, dict[str, Any]]:
        if not self.config_file.is_file():
            return {}
        try:
            return json.loads(self.config_file.read_text(encoding="utf-8")).get("mcpServers", {})
        except ValueError as e:
            self.errors.append(f"{self.config_file.name}: {e}")
            return {}

    def start(self) -> McpHub:
        servers = self.servers
        if servers:
            asyncio.run_coroutine_threadsafe(self._connect_all(servers), self._loop).result(self.timeout)
        return self

    async def _connect_all(self, servers: dict[str, dict[str, Any]]) -> None:
        for name, spec in servers.items():
            try:
                await self._connect(name, spec)
            except Exception as e:
                self.errors.append(f"{name}: {e}")

    async def _connect(self, name: str, spec: dict[str, Any]) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=spec["command"], args=spec.get("args", []), env=spec.get("env"))
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        for tool in (await session.list_tools()).tools:
            self.tools[_safe(f"{name}__{tool.name}")] = (session, tool)

    # --- used by ToolRunner ----------------------------------------------------

    def has(self, name: str) -> bool:
        return name in self.tools

    def schemas(self) -> list[dict[str, Any]]:
        return [{"name": api_name, "description": (tool.description or tool.name)[:1000],
                 "input_schema": tool.inputSchema or {"type": "object", "properties": {}}}
                for api_name, (_, tool) in self.tools.items()]

    def is_risky(self, name: str) -> bool:
        annotations = getattr(self.tools[name][1], "annotations", None)
        return not (annotations and annotations.readOnlyHint)

    def question(self, name: str, args: dict[str, Any]) -> str:
        server, _, tool = name.partition("__")
        details = ", ".join(f"{k} {v}" for k, v in list(args.items())[:3])
        return f"Should I use {tool.replace('_', ' ')} from {server}" + (f" with {details}?" if details else "?")

    def call(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        session, tool = self.tools[name]
        try:
            result = asyncio.run_coroutine_threadsafe(
                session.call_tool(tool.name, args), self._loop).result(self.timeout)
        except Exception as e:
            return f"Error: {e}", True
        text = "\n".join(getattr(block, "text", f"[{block.type}]") for block in result.content)
        return text[:3000] or "(no output)", bool(result.isError)

    def close(self) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self._stack.aclose(), self._loop).result(10)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
