from __future__ import annotations

from typing import Any
import re
from .client import MCPClient, MCPServerConfig, MCPTool


class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self):
        self.clients: dict[str, MCPClient] = {}
        self.configs: dict[str, MCPServerConfig] = {}

    def add_server(self, config: MCPServerConfig | dict[str, Any]) -> None:
        """Add an MCP server configuration."""
        if isinstance(config, dict):
            config = MCPServerConfig(**config)
        if not re.fullmatch(r"[A-Za-z0-9-]{1,48}", config.name):
            raise ValueError("MCP server names must use letters, digits or hyphens")
        if config.transport != "stdio":
            raise ValueError("Only MCP stdio transport is currently supported")
        if not isinstance(config.command, str) or not config.command.strip():
            raise ValueError("MCP server command is required")
        if not isinstance(config.args, list) or not all(isinstance(argument, str) for argument in config.args):
            raise ValueError("MCP server arguments must be a list of strings")
        self.configs[config.name] = config

    def remove_server(self, name: str) -> None:
        """Remove an MCP server configuration."""
        self.configs.pop(name, None)
        if name in self.clients:
            # Note: async close needed, but this is sync
            pass

    async def start_all(self) -> None:
        """Start all configured servers."""
        for name, config in self.configs.items():
            client = MCPClient(config)
            await client.start()
            await client.initialize()
            self.clients[name] = client

    async def start_server(self, name: str) -> MCPClient | None:
        """Start a specific server."""
        config = self.configs.get(name)
        if not config:
            return None
        client = MCPClient(config)
        await client.start()
        await client.initialize()
        self.clients[name] = client
        return client

    def get_client(self, name: str) -> MCPClient | None:
        """Get a client by name."""
        return self.clients.get(name)

    def get_all_tools(self) -> list[MCPTool]:
        """Get all tools from all connected servers."""
        tools = []
        for client in self.clients.values():
            tools.extend(client._tools)
        return tools

    def get_tools_for_llm(self) -> list[dict[str, Any]]:
        """Get tools formatted for LLM function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": f"mcp_{tool.server_name}_{tool.name}",
                    "description": f"[{tool.server_name}] {tool.description}",
                    "parameters": tool.input_schema,
                },
            }
            for tool in self.get_all_tools()
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool by its full name (server_tool)."""
        # Parse server_name and tool_name from mcp_servername_toolname
        if not tool_name.startswith("mcp_"):
            raise ValueError(f"Invalid MCP tool name: {tool_name}")

        parts = tool_name[4:].split("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid MCP tool name format: {tool_name}")

        server_name, name = parts
        client = self.clients.get(server_name)
        if not client:
            raise ValueError(f"MCP server not connected: {server_name}")

        return await client.call_tool(name, arguments)

    async def close_all(self) -> None:
        """Close all connections."""
        for client in self.clients.values():
            await client.close()
        self.clients.clear()

    async def __aenter__(self):
        await self.start_all()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_all()
