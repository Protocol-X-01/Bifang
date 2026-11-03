import asyncio

import pytest

from bifang.policy import Policy
from bifang.tools.commands import bwrap_argv, run_command


def test_missing_requested_sandbox_never_starts_host_shell(tmp_path, monkeypatch):
    monkeypatch.setattr("bifang.tools.commands.shutil.which", lambda command: None)

    async def forbidden_process(*args, **kwargs):
        pytest.fail("Host shell started while the requested sandbox was unavailable")

    monkeypatch.setattr("bifang.tools.commands.asyncio.create_subprocess_exec", forbidden_process)
    with pytest.raises(RuntimeError, match="refusing unsandboxed execution"):
        asyncio.run(run_command(Policy(tmp_path, "trusted"), "printf synthetic-fixture", use_bwrap=True))


def test_bubblewrap_hides_private_state_and_credentials_but_keeps_git_metadata(tmp_path):
    (tmp_path / ".bifang" / "sessions").mkdir(parents=True)
    (tmp_path / ".bifang" / "sessions" / "fixture.jsonl").write_text("private session fixture")
    (tmp_path / ".env").write_text("TOKEN=synthetic-fixture")
    (tmp_path / ".aws").mkdir()
    (tmp_path / ".aws" / "credentials").write_text("synthetic fixture")
    (tmp_path / ".config" / "gcloud").mkdir(parents=True)
    (tmp_path / ".config" / "gcloud" / "credentials.db").write_text("synthetic cloud fixture")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n")

    arguments = bwrap_argv(tmp_path, "true")
    pairs = list(zip(arguments, arguments[1:]))
    triples = list(zip(arguments, arguments[1:], arguments[2:]))

    assert ("--tmpfs", "/workspace/.bifang") in pairs
    assert ("--tmpfs", "/workspace/.aws") in pairs
    assert ("--tmpfs", "/workspace/.config/gcloud") in pairs
    assert ("--ro-bind", "/dev/null", "/workspace/.env") in triples
    assert not any("/workspace/.git" in argument for argument in arguments)


def test_bubblewrap_refuses_sensitive_symlink_paths(tmp_path):
    (tmp_path / ".env").symlink_to(tmp_path / "elsewhere")

    with pytest.raises(RuntimeError, match="sensitive symbolic link"):
        bwrap_argv(tmp_path, "true")


def test_workspace_mask_scan_skips_build_and_dependency_stores(tmp_path):
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / ".env").write_text("synthetic build fixture")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / ".env").write_text("synthetic source fixture")

    arguments = bwrap_argv(tmp_path, "true")

    assert ("--ro-bind", "/dev/null", "/workspace/src/.env") in list(zip(arguments, arguments[1:], arguments[2:]))
    assert "/workspace/target/.env" not in arguments


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
