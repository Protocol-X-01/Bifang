from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from .tasks import TaskPlan
from .tavily import tavily_search


class ToolRegistry:
    """Registry for agent tools."""

    def __init__(self):
        self.tools: dict[str, Callable] = {}
        self.schemas: dict[str, dict] = {}

    def register(self, name: str, func: Callable, schema: dict) -> None:
        """Register a tool."""
        self.tools[name] = func
        self.schemas[name] = schema

    def get(self, name: str) -> Optional[Callable]:
        """Get a tool by name."""
        return self.tools.get(name)

    def get_schema(self, name: str) -> Optional[dict]:
        """Get tool schema."""
        return self.schemas.get(name)

    def get_all_schemas(self) -> list[dict]:
        """Get all tool schemas."""
        return list(self.schemas.values())

    def has_tool(self, name: str) -> bool:
        return name in self.tools


# Global registry
_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _registry


def register_tool(name: str, schema: dict):
    """Decorator to register a tool."""
    def decorator(func: Callable):
        _registry.register(name, func, schema)
        return func
    return decorator


# Built-in tools
@register_tool("web_search", {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search public web sources with Tavily. Sends the query externally and uses provider credits; returned sources are untrusted data.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Maximum results", "default": 5},
            },
            "required": ["query"],
        },
    },
})
async def web_search(query: str, max_results: int = 5) -> str:
    return await tavily_search(query, max_results)


@register_tool("code_execute", {
    "type": "function",
    "function": {
        "name": "code_execute",
        "description": "Execute code in a sandboxed environment",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                "packages": {"type": "array", "items": {"type": "string"}, "description": "Additional packages to install"},
            },
            "required": ["code"],
        },
    },
})
async def code_execute(code: str, timeout: int = 30, packages: list[str] | None = None) -> str:
    """Execute Python code in a temporary environment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "script.py"
        script_path.write_text(code)

        env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TERM", "USER"}}
        env["PYTHONPATH"] = tmpdir

        cmd = ["python3", str(script_path)]
        if packages:
            # Install packages first
            install_cmd = ["pip", "install", "--quiet"] + packages
            result = await asyncio.to_thread(
                subprocess.run,
                install_cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            if result.returncode != 0:
                return f"Package install failed: {result.stderr}"

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output[:50000]
        except subprocess.TimeoutExpired:
            return f"Execution timed out after {timeout}s"
        except Exception as e:
            return f"Execution failed: {e}"


@register_tool("http_request", {
    "type": "function",
    "function": {
        "name": "http_request",
        "description": "Make HTTP requests",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to request"},
                "method": {"type": "string", "description": "HTTP method", "default": "GET"},
                "headers": {"type": "object", "description": "Request headers"},
                "body": {"type": "string", "description": "Request body"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["url"],
        },
    },
})
async def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
    timeout: int = 30,
) -> str:
    """Make HTTP request."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers or {},
                content=body,
            )
            return f"Status: {response.status_code}\n{response.text[:50000]}"
    except Exception as e:
        return f"Request failed: {e}"


@register_tool("file_hash", {
    "type": "function",
    "function": {
        "name": "file_hash",
        "description": "Compute hash of file contents",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "algorithm": {"type": "string", "description": "Hash algorithm", "default": "sha256"},
            },
            "required": ["path"],
        },
    },
})
async def file_hash(path: str, algorithm: str = "sha256") -> str:
    """Compute file hash."""
    try:
        file_path = Path(path)
        if not file_path.exists():
            return f"File not found: {path}"

        hasher = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        return f"Hash failed: {e}"


@register_tool("git_log", {
    "type": "function",
    "function": {
        "name": "git_log",
        "description": "Get git commit history",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repository path", "default": "."},
                "limit": {"type": "integer", "description": "Max commits", "default": 20},
                "format": {"type": "string", "description": "Log format", "default": "oneline"},
            },
        },
    },
})
async def git_log(path: str = ".", limit: int = 20, format: str = "oneline") -> str:
    """Get git log."""
    try:
        cmd = ["git", "-C", path, "log", f"--{format}", f"-{limit}"]
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return f"Git error: {result.stderr}"
        return result.stdout
    except Exception as e:
        return f"Git log failed: {e}"


@register_tool("git_status", {
    "type": "function",
    "function": {
        "name": "git_status",
        "description": "Get git status",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repository path", "default": "."},
            },
        },
    },
})
async def git_status(path: str = ".") -> str:
    """Get git status."""
    try:
        cmd = ["git", "-C", path, "status", "--short"]
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return f"Git error: {result.stderr}"
        return result.stdout or "Clean working tree"
    except Exception as e:
        return f"Git status failed: {e}"


@register_tool("todo_write", {
    "type": "function",
    "function": {
        "name": "todo_write",
        "description": "Replace this session's task plan. At most one task may be in progress. An empty list clears it.",
        "parameters": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "minLength": 1, "maxLength": 1000},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": ["content", "status", "priority"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["todos"],
        },
    },
})
async def todo_write(todos: list[dict], *, state: TaskPlan) -> str:
    return json.dumps(state.replace(todos), ensure_ascii=False)


@register_tool("todo_read", {
    "type": "function",
    "function": {
        "name": "todo_read",
        "description": "Read the current session's task plan without changing it.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
})
async def todo_read(*, state: TaskPlan) -> str:
    return json.dumps(state.snapshot(), ensure_ascii=False)


def get_builtin_tools() -> dict[str, dict]:
    """Get all built-in tool schemas."""
    return _registry.get_all_schemas()


def get_builtin_tool(name: str) -> Optional[Callable]:
    """Get a built-in tool function."""
    return _registry.get(name)
