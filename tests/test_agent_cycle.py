import asyncio
import json

import httpx
import pytest

from bifang.agent import SYSTEM, Agent
from bifang.config import Config
from bifang.context.summarizer import HeuristicSummarizer
from bifang.providers.types import ProviderConfig
from bifang.workspace import Workspace


@pytest.mark.parametrize("compact_history", [False, True])
def test_agent_completes_model_tool_model_cycle(tmp_path, monkeypatch, compact_history):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "receipt.py").write_text("amount = 5\n")
    cfg = Config(default_provider="nebius", enable_memory=False,
                 enable_summarization=compact_history, max_context_tokens=16000,
                 providers={"nebius": ProviderConfig(name="nebius", api_key="test-key", default_model="demo-model")})
    requests = []

    async def no_external_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_external_services)

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == "demo-model"
        assert body["messages"][0] == {"role": "system", "content": SYSTEM}
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
        if compact_history:
            agent.context.summarizer = HeuristicSummarizer()
            for index in range(20):
                agent.context.add_message({"role": "user" if index % 2 == 0 else "assistant",
                                           "content": "old context " * 400})
        provider = agent.provider.provider_manager.registry.get("nebius")
        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://example.invalid/v1")
        try:
            assert await agent.ask("Read receipt.py") == "Read receipt.py successfully"
            assert len(requests) == 2
            assert agent.context.total_summarized == int(compact_history)
            assert sum(message.get("tool_call_id") == "read-1" for message in agent.messages) == 1
            assert agent.context.window.current_tokens < cfg.max_context_tokens
        finally:
            await provider.close()

    asyncio.run(scenario())
