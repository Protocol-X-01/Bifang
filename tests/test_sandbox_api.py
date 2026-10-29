import asyncio
import json

import httpx
import pytest

from bifang import server
from bifang.agent import Agent
from bifang.config import Config
from bifang.providers.types import ProviderConfig
from bifang.workspace import Workspace


def test_missing_sandbox_is_actionable_and_never_runs_command(tmp_path, monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    monkeypatch.setattr(server, "sessions", {})
    monkeypatch.setattr("bifang.tools.commands.shutil.which", lambda command: None)
    approvals = []

    async def forbidden_process(*args, **kwargs):
        pytest.fail("Missing sandbox must never start a subprocess")

    async def no_external_services(self):
        return None

    monkeypatch.setattr("bifang.tools.commands.asyncio.create_subprocess_exec", forbidden_process)
    monkeypatch.setattr(Agent, "_ensure_services_started", no_external_services)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant", "content": None, "tool_calls": [{
                "id": "command-1", "type": "function", "function": {
                    "name": "run_command", "arguments": '{"command":"printf synthetic-fixture"}',
                },
            }],
        }}]})

    async def scenario():
        config = Config(mode="assist", use_bwrap=True, enable_memory=False,
                        enable_conversation_history=False, default_provider="nebius",
                        providers={"nebius": ProviderConfig("nebius", "synthetic-test-key",
                                                            default_model="fixture-model")})
        agent = Agent(config, Workspace(tmp_path, tmp_path),
                      approve=lambda prompt: approvals.append(prompt) or True)
        provider = agent.provider.provider_manager.registry.get("nebius")
        await provider.client.aclose()
        provider.client = httpx.AsyncClient(base_url="https://synthetic.invalid/v1",
                                           transport=httpx.MockTransport(respond))
        session = server.Session(id="sandbox-fixture", agent=agent, created_at=0)
        server.sessions[session.id] = session
        try:
            transport = httpx.ASGITransport(app=server.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/sessions/sandbox-fixture/chat", json={"prompt": "Run fixture"})
            assert response.status_code == 503
            assert "Bubblewrap" in response.json()["detail"]
            assert "refusing unsandboxed execution" in response.json()["detail"]
            assert "synthetic-test-key" not in response.text
            assert len(requests) == 1
            assert len(approvals) == 1
            assert session.busy is False
            assert session.message_count == 0
        finally:
            await agent.close()

    asyncio.run(scenario())
