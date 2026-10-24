from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import signal

from .candidate import Candidate
from .tools.commands import SandboxUnavailableError


def verification_argv(root, command: list[str]) -> list[str]:
    return ["bwrap", "--die-with-parent", "--unshare-all", "--clearenv",
            "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin",
            "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", str(root), "/workspace", "--chdir", "/workspace",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--", *command]


async def verify_candidate(candidate: Candidate, command: list[str], *, confirmed: bool = False,
                           timeout: int = 30) -> dict:
    if confirmed is not True:
        raise PermissionError("Engineer confirmation is required for the exact verification command")
    if (not isinstance(command, list) or not 1 <= len(command) <= 64
            or any(not isinstance(part, str) or not part or len(part) > 4096 or "\0" in part for part in command)
            or type(timeout) is not int or not 1 <= timeout <= 60):
        raise ValueError("Provide a bounded argument vector and a timeout between one and 60 seconds")
    if not shutil.which("bwrap"):
        raise SandboxUnavailableError("Verification requires Bubblewrap; no unsandboxed fallback is allowed")
    before = candidate.describe()
    if not before["source_unchanged"]:
        raise RuntimeError("Selected original source changed; rebuild the candidate before verification")
    files = [name for name, content in candidate.snapshot().items() if content is not None]

    async def capture(stream):
        digest = hashlib.sha256()
        retained = bytearray()
        size = 0
        while chunk := await stream.read(65536):
            digest.update(chunk)
            size += len(chunk)
            retained.extend(chunk[:max(0, 16000 - len(retained))])
        return {"sha256": digest.hexdigest(), "bytes": size, "truncated": size > len(retained),
                "text": retained.decode(errors="replace")}

    with Candidate(candidate.root, files, sorted(candidate.paths)) as frozen:
        if frozen.describe()["candidate_sha256"] != before["candidate_sha256"]:
            raise RuntimeError("Candidate changed while preparing verification")
        process = await asyncio.create_subprocess_exec(
            *verification_argv(frozen.root, command), cwd=frozen.root,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, start_new_session=True,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        readers = [asyncio.create_task(capture(process.stdout)), asyncio.create_task(capture(process.stderr))]
        captured = asyncio.gather(*readers)
        timed_out = False

        async def stop():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()

        try:
            try:
                async with asyncio.timeout(timeout):
                    await process.wait()
                    output = await asyncio.shield(captured)
            except TimeoutError:
                timed_out = True
                await stop()
                output = await captured
        except BaseException:
            await stop()
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            await asyncio.gather(captured, return_exceptions=True)
            raise
        after = candidate.describe()
        unchanged = after["candidate_sha256"] == before["candidate_sha256"] and after["source_unchanged"]
        return {"verification": "executed_check", "candidate_sha256": before["candidate_sha256"],
                "command": list(command), "returncode": process.returncode, "timed_out": timed_out,
                "candidate_unchanged": unchanged, "stdout": output[0], "stderr": output[1],
                "passed": process.returncode == 0 and not timed_out and unchanged,
                "scope": "This exact command and selected-file snapshot only"}
