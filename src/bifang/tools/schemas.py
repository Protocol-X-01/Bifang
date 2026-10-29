from __future__ import annotations

from typing import Any


def schemas() -> list[dict[str, Any]]:
    """Get built-in tool schemas."""
    def fn(name: str, description: str, properties: dict, required: list[str]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }

    return [
        fn("list_files", "List repository files", {"limit": {"type": "integer"}}, []),
        fn("read_file", "Read a UTF-8 file", {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path"]),
        fn("search", "Search repository text with ripgrep", {"query": {"type": "string"}}, ["query"]),
        fn("write_file", "Replace a file with complete content", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
        fn("run_command", "Run a command in the isolated workspace", {"command": {"type": "string"}, "timeout": {"type": "integer"}}, ["command"]),
        fn("git_diff", "Show current Git diff", {}, []),
    ]