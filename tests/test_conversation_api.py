import asyncio
import subprocess
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from bifang import server
from bifang.agent import SYSTEM, Agent
from bifang.config import Config
from bifang.context import ContextManager
from bifang.provider import ProviderManager
from bifang.providers.types import ProviderConfig


def test_history_listing_pages_metadata_without_loading_full_transcripts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BIFANG_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    config = Config(use_worktree=False, enable_memory=False)
    monkeypatch.setattr(server.Config, "load", lambda: config)

    async def scenario():
        context = ContextManager(config, project_path=tmp_path)
        await context.initialize()
        cache = context.conversation_cache.cache
        for index in range(25):
            cache.create_session(f"conversation-{index:02}")
        cache.close()
        monkeypatch.setattr(type(cache), "get_session", lambda *args: pytest.fail("Transcript loaded"))
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = (await client.get("/conversations", params={"limit": 20})).json()
            second = (await client.get("/conversations", params={"limit": 20, "offset": 20})).json()
            assert len(first) == 20
            assert len(second) == 5
            assert len({item["conversation_id"] for item in first + second}) == 25
            assert all(item["turn_count"] == 0 for item in first + second)
            assert all(set(item) == {"conversation_id", "created_at", "updated_at", "turn_count"}
                       for item in first + second)
            for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
                assert (await client.get("/conversations", params=params)).status_code == 422
        await context.close()

    asyncio.run(scenario())


def test_api_lists_and_resumes_only_the_selected_projects_history(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BIFANG_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    monkeypatch.delenv("BIFANG_ALLOW_ABSOLUTE_WORKSPACES", raising=False)
    monkeypatch.setattr(server, "sessions", {})
    monkeypatch.setattr(server.Config, "load", lambda: Config(use_worktree=False, enable_memory=False))
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    calls = []

    async def no_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)

    async def complete(messages, **kwargs):
        calls.append(list(messages))
        return {"role": "assistant", "content": "retained answer"}

    async def scenario():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/sessions", json={"workspace": "one"})
            assert created.status_code == 200
            identity = created.json()["session_id"]
            conversation = created.json()["conversation_id"]
            server.sessions[identity].agent.provider.complete = complete
            assert (await client.post(f"/sessions/{identity}/chat", json={"prompt": "original question"})).status_code == 200
            assert (await client.delete(f"/sessions/{identity}")).status_code == 200
            listed = (await client.get("/conversations", params={"workspace": "one"})).json()
            assert len(listed) == 1
            assert listed[0]["conversation_id"] == conversation
            assert listed[0]["turn_count"] == 1
            assert (await client.get("/conversations", params={"workspace": "two"})).json() == []
            rejected = await client.post("/sessions", json={"workspace": "two", "conversation_id": conversation})
            assert rejected.status_code == 404
            resumed = await client.post("/sessions", json={"workspace": "one", "conversation_id": conversation})
            assert resumed.status_code == 200
            restored_id = resumed.json()["session_id"]
            try:
                history = (await client.get(f"/sessions/{restored_id}/history")).json()
                assert history[0]["user_message"] == "original question"
                assert history[0]["assistant_response"] == "retained answer"
                assert history[0]["status"] == "completed"
                assert len(calls) == 1
                agent = server.sessions[restored_id].agent
                assert agent.messages[0] == {"role": "system", "content": SYSTEM}
                assert agent.messages[-1]["content"] == "retained answer"
                agent.provider.complete = complete
                assert (await client.post(f"/sessions/{restored_id}/chat", json={"prompt": "follow-up"})).status_code == 200
                assert len((await client.get(f"/sessions/{restored_id}/history")).json()) == 2
            finally:
                await client.delete(f"/sessions/{restored_id}")
        assert server.sessions == {}

    asyncio.run(scenario())


def test_provider_managers_do_not_replace_or_close_other_sessions_clients():
    config = Config(providers={"nebius": ProviderConfig("nebius", "test-key")})

    async def scenario():
        first = ProviderManager(config)
        second = ProviderManager(config)
        try:
            assert first.registry is not second.registry
            first_client = first.registry.get("nebius").client
            second_client = second.registry.get("nebius").client
            assert first_client is not second_client
            await first.close()
            assert first_client.is_closed
            assert not second_client.is_closed
        finally:
            await first.close()
            await second.close()

    asyncio.run(scenario())


def test_repository_promotion_cannot_escape_the_server_workspace_root(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    child = tmp_path / "restricted"
    child.mkdir()
    monkeypatch.setenv("BIFANG_WORKSPACE_ROOT", str(child))
    monkeypatch.setenv("BIFANG_SERVER_HOST", "0.0.0.0")
    monkeypatch.delenv("BIFANG_ALLOW_ABSOLUTE_WORKSPACES", raising=False)
    with pytest.raises(HTTPException) as error:
        server.resolve_workspace(".", repository=True)
    assert error.value.status_code == 403


def test_workspace_is_discarded_even_if_agent_close_fails(monkeypatch):
    discarded = []

    async def fail_close():
        raise RuntimeError("synthetic close failure")

    agent = SimpleNamespace(close=fail_close, tracer=SimpleNamespace(),
                            ws=SimpleNamespace(discard=lambda: discarded.append(True)))
    with pytest.raises(RuntimeError, match="synthetic"):
        asyncio.run(server.dispose_session(server.Session("test", agent, 0)))
    assert discarded == [True]


def test_failed_agent_initialization_discards_its_new_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("BIFANG_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    monkeypatch.setattr(server.Config, "load", lambda: Config(use_worktree=False))
    discarded = []
    workspace = SimpleNamespace(discard=lambda: discarded.append(True))
    monkeypatch.setattr(server.Workspace, "create", lambda *args: workspace)

    def fail(*args, **kwargs):
        raise ValueError("synthetic initialization failure")

    monkeypatch.setattr(server, "Agent", fail)
    with pytest.raises(ValueError, match="initialization"):
        asyncio.run(server.create_session(server.SessionCreate()))
    assert discarded == [True]
