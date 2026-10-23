from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..policy import Policy

SKIP = {".git", ".bifang", ".venv", "node_modules", "dist", "build", "__pycache__"}


def list_files(root: Path, limit: int = 500) -> str:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not any(x in SKIP for x in p.parts):
            out.append(str(p.relative_to(root)))
        if len(out) >= limit:
            break
    return "\n".join(out)


def read_file(policy: Policy, path: str, start: int = 1, end: int = 400) -> str:
    lines = policy.path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(f"{i+1}: {v}" for i, v in enumerate(lines[start-1:end], start-1))


def search(root: Path, query: str) -> str:
    if shutil.which("rg"):
        r = os.popen(
            f"cd {shlex_quote(str(root))} && rg -n --hidden --glob '!.git' --glob '!.bifang' {shlex_quote(query)} 2>/dev/null"
        ).read()
        return r[-100000:] or "No matches"

    matches = []
    for p in root.rglob("*"):
        if p.is_file() and not any(x in SKIP for x in p.parts):
            try:
                for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                    if query.lower() in line.lower():
                        matches.append(f"{p.relative_to(root)}:{i}:{line}")
            except OSError:
                pass
    return "\n".join(matches[:1000]) or "No matches"


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)