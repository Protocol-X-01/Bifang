import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from bifang import server
from bifang.agent import Agent
from bifang.approvals import auto_approves_edit
from bifang.config import Config
from bifang.providers.types import ProviderConfig
from bifang.tools.commands import SandboxUnavailableError
from bifang.workspace import Workspace


def config(mode):
    return Config(approval_mode=mode, enable_memory=False, enable_conversation_history=False,
                  providers={"nebius": ProviderConfig("nebius", "fixture-key", default_model="fixture")})


@pytest.mark.parametrize("mode,isolated,expected_prompts", [
    ("manual", True, 1), ("auto", True, 0), ("auto", False, 1), ("full", True, 0),
])
def test_workspace_edit_approval_levels(tmp_path, monkeypatch, mode, isolated, expected_prompts):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = tmp_path / "worktree"
    root.mkdir()
    prompts = []

    async def scenario():
        agent = Agent(config(mode), Workspace(tmp_path / "source", root, isolated=isolated),
                      approve=lambda prompt: prompts.append(prompt) or True)
        try:
            assert await agent.tool("write_file", {"path": "fix.py", "content": "answer = 42\n"}) == "Wrote fix.py"
            assert (root / "fix.py").read_text() == "answer = 42\n"
            assert len(prompts) == expected_prompts
            rows = [json.loads(line) for line in agent.audit.path.read_text().splitlines()]
            approval = next(row for row in rows if row["event"] == "tool_approval")
            assert approval["approval_mode"] == mode
            assert approval["approved"] is True
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("relative", [".env", "src/credentials.json", ".github/workflows/ci.yml",
                                      "package.json", "pyproject.toml", "requirements-dev.txt",
                                      "../outside.py", "id_rsa", "deploy.sh"])
def test_auto_mode_does_not_auto_approve_sensitive_or_unknown_edits(tmp_path, relative):
    root = tmp_path / "worktree"
    root.mkdir()
    assert not auto_approves_edit(root, tmp_path / "source", True, {"path": relative, "content": "fixture"})


def test_auto_mode_resolves_symlinks_and_bounds_write_size(tmp_path):
    root = tmp_path / "worktree"
    root.mkdir()
    (root / "alias.py").symlink_to(tmp_path / "outside.py")
    assert not auto_approves_edit(root, tmp_path / "source", True, {"path": "alias.py", "content": "fixture"})
    assert not auto_approves_edit(root, tmp_path / "source", True, {"path": "fix.py", "content": "x" * 200001})
    assert not auto_approves_edit(root, root, True, {"path": "fix.py", "content": "fixture"})


@pytest.mark.parametrize("mode", ["manual", "auto", "full"])
def test_command_approvals_do_not_disable_sandbox_or_policy(tmp_path, monkeypatch, mode):
    prompts, calls = [], []

    async def missing_sandbox(policy, command, timeout, sandbox):
        calls.append(sandbox)
        raise SandboxUnavailableError("Synthetic missing Bubblewrap")

    monkeypatch.setattr("bifang.agent.run_command", missing_sandbox)

    async def scenario():
        agent = Agent(config(mode), Workspace(tmp_path, tmp_path),
                      approve=lambda prompt: prompts.append(prompt) or True)
        try:
            assert "DENIED" in await agent.tool("run_command", {"command": "sudo id"})
            assert prompts == [] and calls == []
            with pytest.raises(SandboxUnavailableError):
                await agent.tool("run_command", {"command": "pytest -q"})
            assert calls == [True]
            assert len(prompts) == (0 if mode == "full" else 1)
            with pytest.raises(PermissionError):
                await agent.tool("write_file", {"path": "../outside.py", "content": "fixture"})
            assert not (tmp_path.parent / "outside.py").exists()
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("tool", ["mcp_publish", "plugin_publish", "code_execute", "http_request"])
@pytest.mark.parametrize("mode", ["manual", "auto"])
def test_external_and_generated_code_tools_require_review(tmp_path, tool, mode):
    prompts = []

    async def scenario():
        agent = Agent(config(mode), Workspace(tmp_path, tmp_path),
                      approve=lambda prompt: prompts.append(prompt) or False)
        try:
            assert await agent.tool(tool, {}) == "DENIED by user"
            assert len(prompts) == 1
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_full_approval_never_overrides_observe_mode(tmp_path):
    async def scenario():
        cfg = config("full")
        cfg.mode = "observe"
        agent = Agent(cfg, Workspace(tmp_path, tmp_path), approve=lambda prompt: pytest.fail("Unexpected prompt"))
        try:
            assert await agent.tool("write_file", {"path": "fix.py", "content": "fixture"}) == "DENIED: observe mode"
            assert await agent.tool("mcp_publish", {}) == "DENIED: observe mode"
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("tool", ["mcp_publish", "plugin_publish", "code_execute"])
def test_full_mode_runs_enabled_tools_without_another_prompt(tmp_path, monkeypatch, tool):
    callback = AsyncMock(return_value="synthetic result")

    async def scenario():
        agent = Agent(config("full"), Workspace(tmp_path, tmp_path),
                      approve=lambda prompt: pytest.fail("Full mode requested another approval"))
        if tool.startswith("mcp_"):
            agent.mcp.call_tool = callback
        elif tool.startswith("plugin_"):
            monkeypatch.setattr(agent.plugins, "get_tool", lambda name: callback if name == tool else None)
        else:
            monkeypatch.setattr("bifang.agent.get_builtin_tool", lambda name: callback if name == tool else None)
        try:
            assert await agent.tool(tool, {}) == "synthetic result"
            callback.assert_awaited_once()
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_api_explicit_full_optin_and_request_default_reset(monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    monkeypatch.setattr(server, "sessions", {})
    cfg = config("full")
    observed = []

    async def ask(prompt, selection=None):
        observed.append(cfg.approval_mode)
        return "fixture"

    session = server.Session("fixture", SimpleNamespace(cfg=cfg, ask=ask, audit=Mock(),
                                                        provider=SimpleNamespace(requests=[])), 0)
    server.sessions[session.id] = session

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            assert (await client.post("/sessions/fixture/chat", json={"prompt": "fixture", "approval_mode": "full"})).status_code == 422
            for confirmation in ("true", "yes", 1):
                assert (await client.post("/sessions/fixture/chat", json={"prompt": "fixture", "approval_mode": "full",
                                                                        "full_access_confirmed": confirmation})).status_code == 422
            for value in ("unrestricted", "FULL", None):
                assert (await client.post("/sessions/fixture/chat", json={"prompt": "fixture", "approval_mode": value})).status_code == 422
            assert observed == []
            for payload in ({"approval_mode": "full", "full_access_confirmed": True}, {}, {"approval_mode": "auto"}):
                assert (await client.post("/sessions/fixture/chat", json={"prompt": "fixture", **payload})).status_code == 200
            assert observed == ["full", "manual", "auto"]
            session.busy = True
            assert (await client.post("/sessions/fixture/chat", json={"prompt": "fixture", "approval_mode": "full", "full_access_confirmed": True})).status_code == 409
            assert cfg.approval_mode == "auto"
            paused = await client.post("/sessions/fixture/pause-auto-approval")
            assert paused.status_code == 200
            assert cfg.approval_mode == "manual" and session.busy is True
            assert (await client.post("/sessions/missing/pause-auto-approval")).status_code == 404

    asyncio.run(scenario())


def test_invalid_environment_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("BIFANG_APPROVAL_MODE", "typo")
    with pytest.raises(ValueError, match="BIFANG_APPROVAL_MODE"):
        Config.load()


def test_new_session_never_inherits_full_approval_from_environment(tmp_path, monkeypatch):
    cfg = config("full")
    cfg.use_worktree = False
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("BIFANG_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(server, "sessions", {})
    monkeypatch.setattr(server.Config, "load", lambda: cfg)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            response = await client.post("/sessions", json={"workspace": "."})
            assert response.status_code == 200
            identity = response.json()["session_id"]
            try:
                details = await client.get(f"/sessions/{identity}")
                assert details.json()["approval_mode"] == "manual"
                assert server.sessions[identity].agent.cfg.approval_mode == "manual"
            finally:
                assert (await client.delete(f"/sessions/{identity}")).status_code == 200

    asyncio.run(scenario())
