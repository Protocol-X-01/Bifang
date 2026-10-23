from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"  # stdio, sse, websocket
    url: str | None = None  # for SSE/websocket transports


@dataclass
class MCPTool:
    """An MCP tool."""
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


class MCPClient:
    """Client for communicating with an MCP server."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self.request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._initialized = False
        self._tools: list[MCPTool] = []

    async def start(self) -> None:
        """Start the MCP server process."""
        if self.config.transport == "stdio":
            env = os.environ.copy()
            env.update(self.config.env)
            self.process = await asyncio.create_subprocess_exec(
                self.config.command,
                *self.config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            # Start reading responses
            asyncio.create_task(self._read_stdout())
            asyncio.create_task(self._read_stderr())
        elif self.config.transport in ("sse", "websocket"):
            # For HTTP-based transports, we don't start a process
            pass
        else:
            raise ValueError(f"Unknown transport: {self.config.transport}")

    async def initialize(self) -> None:
        """Initialize the MCP connection."""
        if self._initialized:
            return

        # Send initialize request
        response = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "bifang", "version": "0.2.0"},
        })

        if "error" in response:
            raise RuntimeError(f"MCP initialization failed: {response['error']}")

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

        # List available tools
        await self.list_tools()

        self._initialized = True

    async def list_tools(self) -> list[MCPTool]:
        """List available tools from the server."""
        response = await self._send_request("tools/list", {})
        if "error" in response:
            raise RuntimeError(f"Failed to list tools: {response['error']}")

        self._tools = [
            MCPTool(
                name=tool["name"],
                description=tool.get("description", ""),
                input_schema=tool.get("inputSchema", {}),
                server_name=self.config.name,
            )
            for tool in response.get("result", {}).get("tools", [])
        ]
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the server."""
        response = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        if "error" in response:
            raise RuntimeError(f"Tool call failed: {response['error']}")
        return response.get("result")

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request."""
        self.request_id += 1
        request_id = self.request_id

        future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        await self._write(request)
        return await future

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._write(notification)

    async def _write(self, message: dict[str, Any]) -> None:
        """Write a message to the server."""
        if self.config.transport == "stdio" and self.process and self.process.stdin:
            data = json.dumps(message) + "\n"
            self.process.stdin.write(data.encode())
            await self.process.stdin.drain()
        elif self.config.transport in ("sse", "websocket") and self.config.url:
            # HTTP-based transports would go here
            pass

    async def _read_stdout(self) -> None:
        """Read responses from stdout."""
        if not self.process or not self.process.stdout:
            return

        async for line in self.process.stdout:
            line = line.decode().strip()
            if not line:
                continue
            try:
                response = json.loads(line)
                await self._handle_response(response)
            except json.JSONDecodeError:
                pass

    async def _read_stderr(self) -> None:
        """Read stderr for debugging."""
        if not self.process or not self.process.stderr:
            return

        async for line in self.process.stderr:
            print(f"[MCP {self.config.name} stderr] {line.decode().strip()}")

    async def _handle_response(self, response: dict[str, Any]) -> None:
        """Handle a JSON-RPC response."""
        request_id = response.get("id")
        if request_id is not None and request_id in self._pending:
            future = self._pending.pop(request_id)
            future.set_result(response)

    async def close(self) -> None:
        """Close the connection."""
        if self.process:
            self.process.terminate()
            await self.process.wait()
            self.process = None