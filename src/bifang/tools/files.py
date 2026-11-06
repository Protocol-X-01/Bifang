from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from ..policy import Policy
from ..secret_patterns import is_sensitive_workspace_path, redact_secrets

SKIP = {".git", ".bifang", ".venv", "node_modules", "dist", "build", "__pycache__"}
MAX_READ_FILE_BYTES = 8 * 1024 * 1024
MAX_READ_LINES = 1000


def _workspace_files(root: Path):
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        directory = Path(current)
        relative_directory = directory.relative_to(root)
        directories[:] = [
            name for name in sorted(directories)
            if name not in SKIP
            and not (directory / name).is_symlink()
            and not is_sensitive_workspace_path(relative_directory / name)
        ]
        for name in sorted(filenames):
            path = directory / name
            relative = path.relative_to(root)
            if (path.is_symlink() or not path.is_file() or any(part in SKIP for part in relative.parts)
                    or is_sensitive_workspace_path(relative)):
                continue
            yield path, relative


def list_files(root: Path, limit: int = 500) -> str:
    root = root.resolve()
    if isinstance(limit, bool) or not isinstance(limit, int):
        limit = 500
    limit = min(max(limit, 1), 2000)
    out = []
    for _, relative in _workspace_files(root):
        out.append(redact_secrets(relative.as_posix()))
        if len(out) >= limit:
            break
    return "\n".join(out)


def read_file(policy: Policy, path: str, start: int = 1, end: int = 400) -> str:
    if (type(start) is not int or type(end) is not int or start < 1 or end < start
            or end - start + 1 > MAX_READ_LINES):
        return f"Invalid read range: select 1 to {MAX_READ_LINES} lines"
    target = policy.read_path(path)
    if not target.is_file():
        return "Read failed: path is not a regular file"
    if target.stat().st_size > MAX_READ_FILE_BYTES:
        return "Read failed: file exceeds the 8 MiB model-read limit"
    lines = redact_secrets(target.read_text(encoding="utf-8", errors="replace")).splitlines()
    return "\n".join(f"{i+1}: {v}" for i, v in enumerate(lines[start-1:end], start-1))[:100000]


def _search_file_context(path: Path, *, rg_lines: bool = False) -> tuple[list[str], list[str]] | None:
    if path.stat().st_size > MAX_READ_FILE_BYTES:
        return None
    with path.open("rb") as source:
        content = source.read(MAX_READ_FILE_BYTES + 1)
    if len(content) > MAX_READ_FILE_BYTES:
        return None
    text = content.decode("utf-8", errors="replace" if rg_lines else "ignore")
    # ripgrep counts LF-delimited lines; retain the fallback's existing splitlines behavior.
    original_lines = ([line.rstrip("\r") for line in text.split("\n")]
                      if rg_lines else text.splitlines())
    clean_lines = redact_secrets("\n".join(original_lines)).split("\n")
    if len(clean_lines) != len(original_lines):
        # Never associate a collapsed multiline redaction with the wrong source line.
        clean_lines = ["[REDACTED]"] * len(original_lines)
    clean_lines = [clean or ("[REDACTED]" if original else "")
                   for original, clean in zip(original_lines, clean_lines)]
    return original_lines, clean_lines


def search(root: Path, query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 512:
        return "Search query must contain 1 to 512 characters"
    root = root.resolve()
    if shutil.which("rg"):
        result = subprocess.run(
            ["rg", "--no-config", "--json", "--hidden", "--max-filesize", "8M", "--max-count", "100",
             "--glob", "!.git/**", "--glob", "!.bifang/**", "--glob", "!**/.venv/**",
             "--glob", "!**/node_modules/**", "--glob", "!**/dist/**", "--glob", "!**/build/**",
             "--glob", "!**/__pycache__/**", "--", query, "."],
            cwd=root, capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode not in (0, 1):
            return "Search failed: invalid pattern or unavailable files"
        matches = []
        # Retain at most one bounded file, rather than caching the whole result set.
        cached_path = None
        cached_context = None
        for record in result.stdout.splitlines():
            try:
                event = json.loads(record)
            except json.JSONDecodeError:
                return "Search failed: invalid search output"
            if event.get("type") != "match":
                continue
            data = event.get("data", {})
            path_text = data.get("path", {}).get("text")
            if not isinstance(path_text, str):
                continue
            relative = Path(path_text)
            if relative.is_absolute() or ".." in relative.parts or is_sensitive_workspace_path(relative):
                continue
            if any(part in SKIP for part in relative.parts):
                continue
            candidate = root / relative
            try:
                resolved = candidate.resolve(strict=True)
                if (candidate.is_symlink() or not resolved.is_relative_to(root)
                        or is_sensitive_workspace_path(resolved.relative_to(root))):
                    continue
            except (OSError, RuntimeError):
                continue
            line_number = data.get("line_number")
            line_text = data.get("lines", {}).get("text")
            if not isinstance(line_number, int) or not isinstance(line_text, str):
                continue
            if resolved != cached_path:
                cached_path = resolved
                try:
                    cached_context = _search_file_context(resolved, rg_lines=True)
                except OSError:
                    cached_context = None
            if cached_context is None or not 1 <= line_number <= len(cached_context[1]):
                continue
            clean_line = cached_context[1][line_number - 1]
            clean_path = redact_secrets(relative.as_posix())
            matches.append(f"{clean_path}:{line_number}:{clean_line}")
            if len(matches) >= 1000:
                break
        return "\n".join(matches)[-100000:] or "No matches"

    matches = []
    output_size = 0
    for path, relative in _workspace_files(root):
        try:
            context = _search_file_context(path)
            if context is None:
                continue
            original_lines, clean_lines = context
            for i, line in enumerate(original_lines, 1):
                if query.lower() in line.lower():
                    clean_path = redact_secrets(relative.as_posix())
                    match = f"{clean_path}:{i}:{clean_lines[i - 1]}"
                    matches.append(match)
                    output_size += len(match)
                    if len(matches) >= 1000 or output_size >= 100000:
                        return "\n".join(matches)[:100000]
        except OSError:
            pass
    return "\n".join(matches)[:100000] or "No matches"


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)
