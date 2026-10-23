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
        "description": "Search the web for information",
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
    """Search the web using DuckDuckGo HTML scraping."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query, "kl": "us-en"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; Bifang/1.0)"},
            )
            html = response.text

            # Simple HTML parsing for results
            from html.parser import HTMLParser

            class ResultParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.results = []
                    self.in_result = False
                    self.current = {}

                def handle_starttag(self, tag, attrs):
                    attrs_dict = dict(attrs)
                    if tag == "a" and attrs_dict.get("class") == "result__snippet":
                        self.in_result = True
                    elif tag == "a" and attrs_dict.get("class") == "result__url":
                        self.current["url"] = attrs_dict.get("href", "")

                def handle_data(self, data):
                    if self.in_result and data.strip():
                        self.current["snippet"] = data.strip()
                        self.results.append(self.current.copy())
                        self.current = {}
                        self.in_result = False

            parser = ResultParser()
            parser.feed(html)

            results = parser.results[:max_results]
            if not results:
                # Fallback: try API
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1},
                )
                data = response.json()
                abstract = data.get("Abstract", "")
                related = data.get("RelatedTopics", [])
                out = [abstract] if abstract else []
                for topic in related[:max_results]:
                    if isinstance(topic, dict):
                        out.append(topic.get("Text", ""))
                return "\n".join(out) or "No results found"

            formatted = []
            for r in results:
                url = r.get("url", "")
                snippet = r.get("snippet", "")
                formatted.append(f"[{url}] {snippet}")
            return "\n\n".join(formatted)

    except Exception as e:
        return f"Search failed: {e}"


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
        "description": "Write/update todo list",
        "parameters": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": ["content", "status", "priority"],
                    },
                },
            },
            "required": ["todos"],
        },
    },
})
async def todo_write(todos: list[dict]) -> str:
    """Write todo list (placeholder - would integrate with UI)."""
    return f"Updated {len(todos)} todos"


def get_builtin_tools() -> dict[str, dict]:
    """Get all built-in tool schemas."""
    return _registry.get_all_schemas()


def get_builtin_tool(name: str) -> Optional[Callable]:
    """Get a built-in tool function."""
    return _registry.get(name)
