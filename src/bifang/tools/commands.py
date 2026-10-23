from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from ..policy import Policy
from .files import shlex_quote


def bwrap_argv(root: Path, command: str) -> list[str]:
    return [
        "bwrap",
        "--die-with-parent",
        "--unshare-all",
        "--share-net",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind-try",
        "/lib",
        "/lib",
        "--ro-bind-try",
        "/lib64",
        "/lib64",
        "--ro-bind-try",
        "/etc",
        "/etc",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(root),
        "/workspace",
        "--chdir",
        "/workspace",
        "--setenv",
        "HOME",
        "/tmp",
        "--",
        "/bin/sh",
        "-lc",
        command,
    ]


async def run_command(policy: Policy, command: str, timeout: int = 180, use_bwrap: bool = True) -> dict:
    d = policy.command(command)
    if not d.allowed:
        raise PermissionError(d.reason)

    env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TERM", "USER"}}
    argv = bwrap_argv(policy.root, command) if use_bwrap and shutil.which("bwrap") else ["/bin/sh", "-lc", command]

    p = await asyncio.create_subprocess_exec(
        *argv,
        cwd=policy.root,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        out, err = await asyncio.wait_for(p.communicate(), timeout)
    except TimeoutError:
        p.kill()
        await p.wait()
        return {"returncode": -1, "stdout": "", "stderr": f"Timed out after {timeout}s"}

    return {
        "returncode": p.returncode,
        "stdout": out.decode(errors="replace")[-100000:],
        "stderr": err.decode(errors="replace")[-100000:],
    }