import asyncio

import pytest

from bifang.policy import Policy
from bifang.tools.commands import run_command


def test_missing_requested_sandbox_never_starts_host_shell(tmp_path, monkeypatch):
    monkeypatch.setattr("bifang.tools.commands.shutil.which", lambda command: None)

    async def forbidden_process(*args, **kwargs):
        pytest.fail("Host shell started while the requested sandbox was unavailable")

    monkeypatch.setattr("bifang.tools.commands.asyncio.create_subprocess_exec", forbidden_process)
    with pytest.raises(RuntimeError, match="refusing unsandboxed execution"):
        asyncio.run(run_command(Policy(tmp_path, "trusted"), "printf synthetic-fixture", use_bwrap=True))


def test_explicit_sandbox_optout_remains_explicit(tmp_path, monkeypatch):
    calls = []

    class Process:
        returncode = 0

        async def communicate(self):
            return b"synthetic-fixture", b""

    async def create_process(*args, **kwargs):
        calls.append(args)
        assert "BIFANG_SYNTHETIC_PRIVATE" not in kwargs["env"]
        return Process()

    monkeypatch.setenv("BIFANG_SYNTHETIC_PRIVATE", "not-for-child")
    monkeypatch.setattr("bifang.tools.commands.asyncio.create_subprocess_exec", create_process)
    report = asyncio.run(run_command(Policy(tmp_path, "trusted"), "printf synthetic-fixture", use_bwrap=False))
    assert report["returncode"] == 0
    assert calls == [("/bin/sh", "-lc", "printf synthetic-fixture")]
