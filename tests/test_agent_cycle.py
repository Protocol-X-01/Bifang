import asyncio
import json

import httpx

from bifang.agent import Agent
from bifang.config import Config
from bifang.providers.registry import ProviderRegistry
from bifang.providers.types import ProviderConfig
from bifang.workspace import Workspace


def test_agent_completes_model_tool_model_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "receipt.py").write_text("amount = 5\n")
    registry = ProviderRegistry()
    monkeypatch.setattr("bifang.provider.get_registry", lambda: registry)
    cfg = Config(default_provider="nebius", enable_memory=False, enable_summarization=False,
                 providers={"nebius": ProviderConfig(name="nebius", api_key="test-key", default_model="demo-model")})
    requests = []

    async def no_external_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_external_services)

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == "demo-model"
        assert any(tool["function"]["name"] == "read_file" for tool in body["tools"])
        if len(requests) == 1:
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "read-1", "type": "function", "function": {
                    "name": "read_file", "arguments": '{"path":"receipt.py"}',
                },
            }]}
        else:
            assert body["messages"][-2]["role"] == "assistant"
            assert body["messages"][-1]["role"] == "tool"
            assert "amount = 5" in body["messages"][-1]["content"]
            message = {"role": "assistant", "content": "Read receipt.py successfully"}
        return httpx.Response(200, json={
            "choices": [{"message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                      "prompt_tokens_details": {"cached_tokens": 0}},
        })

    async def scenario():
        agent = Agent(cfg, Workspace(tmp_path, tmp_path))
        provider = registry.get("nebius")
        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://example.invalid/v1")
        try:
            assert await agent.ask("Read receipt.py") == "Read receipt.py successfully"
            assert len(requests) == 2
        finally:
            await provider.close()

    asyncio.run(scenario())
