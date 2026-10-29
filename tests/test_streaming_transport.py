import asyncio
import json

import httpx
import pytest

from bifang.agent import Agent
from bifang.config import Config
from bifang.providers.base import ChatMessage
from bifang.providers.nebius import NebiusProvider
from bifang.providers.nvidia import NVIDIAProvider
from bifang.providers.types import ProviderConfig
from bifang.workspace import Workspace


def event(delta=None, finish=None, **fields):
    return {"model": "server-model", "choices": [{"index": 0, "delta": delta or {},
            "finish_reason": finish}], **fields}


def wire(events, done=True):
    return ("".join("data: " + json.dumps(item) + "\n\n" for item in events) +
            ("data: [DONE]\n\n" if done else "")).encode()


async def collect(provider_type, payload):
    provider = provider_type(ProviderConfig(name="test", api_key="synthetic", base_url="https://fixture.invalid/v1"))
    await provider.close()
    provider.client = httpx.AsyncClient(base_url="https://fixture.invalid/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload)))
    try:
        return [chunk async for chunk in provider.complete_stream([ChatMessage(role="user", content="fixture")], "requested-model")]
    finally:
        await provider.close()


@pytest.mark.parametrize("provider_type", [NVIDIAProvider, NebiusProvider])
def test_stream_assembles_interleaved_arguments_once_and_preserves_usage(provider_type):
    events = [event({"tool_calls": [{"index": 0, "id": "read", "type": "function", "function": {
        "name": "read_file", "arguments": '{"path":'}}, {"index": 1, "id": "plan", "type": "function",
        "function": {"name": "todo_read", "arguments": "{"}}]}),
        event({"tool_calls": [{"index": 1, "function": {"arguments": "}"}},
                              {"index": 0, "function": {"arguments": '"fixture.txt"}'}}]}),
        event(finish="tool_calls"),
        {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}}]
    chunks = asyncio.run(collect(provider_type, wire(events)))
    calls = [call for chunk in chunks for call in chunk.tool_calls or []]
    assert [call.id for call in calls] == ["read", "plan"]
    assert json.loads(calls[0].function.arguments) == {"path": "fixture.txt"}
    assert json.loads(calls[1].function.arguments) == {}
    assert any(chunk.usage == events[-1]["usage"] for chunk in chunks)
    assert all(chunk.model == "requested-model" and chunk.reported_model == "server-model" for chunk in chunks)


@pytest.mark.parametrize("finish", ["length", "content_filter"])
def test_truncated_or_filtered_tool_calls_raise_instead_of_emitting_actions(finish):
    events = [event({"tool_calls": [{"index": 0, "id": "read", "type": "function", "function": {
        "name": "read_file", "arguments": '{"path":'}}]}), event(finish=finish)]
    with pytest.raises(ValueError):
        asyncio.run(collect(NebiusProvider, wire(events)))


@pytest.mark.parametrize("payload", [b'data: {"SYNTHETIC-PRIVATE":\n\n',
    wire([event({"content": "partial"})], done=False),
    wire([{"error": {"message": "SYNTHETIC-PRIVATE"}}])])
def test_malformed_error_or_abrupt_stream_is_visible_without_raw_payload(payload):
    with pytest.raises(ValueError) as error:
        asyncio.run(collect(NebiusProvider, payload))
    assert "SYNTHETIC-PRIVATE" not in str(error.value)


def test_text_and_multiline_sse_data_without_space_are_supported():
    payload = b'data:{"model":"actual","choices":[\ndata:{"index":0,"delta":{"content":"hello"},"finish_reason":null}]}\n\n'
    payload += wire([event({"content": " world"}), event(finish="stop")])
    chunks = asyncio.run(collect(NebiusProvider, payload))
    assert "".join(chunk.content or "" for chunk in chunks) == "hello world"


@pytest.mark.parametrize("events", [
    [event(finish="tool_calls")],
    [event({"tool_calls": [{"index": 0, "id": "read", "function": {"name": "read_file", "arguments": "[]"}}]}), event(finish="tool_calls")],
    [event({"tool_calls": [{"index": 0, "id": "read", "function": {"name": "read_file", "arguments": "{}"}}]}),
     event({"tool_calls": [{"index": 0, "id": "changed"}]}), event(finish="tool_calls")],
])
def test_invalid_tool_identity_or_argument_shape_never_produces_a_call(events):
    async def scenario():
        with pytest.raises(ValueError):
            await collect(NebiusProvider, wire(events))
    asyncio.run(scenario())


def test_real_streaming_adapter_agent_tool_cycle_and_durable_receipts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "fixture.txt").write_text("synthetic stream fixture")
    config = Config(enable_memory=False, mode="observe", max_steps=3, providers={"nebius": ProviderConfig(
        name="nebius", api_key="synthetic", default_model="requested-model", base_url="https://fixture.invalid/v1")})
    agent = Agent(config, Workspace(tmp_path, tmp_path))
    requests = []
    tools = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == "requested-model" and payload["stream"] is True
        if len(requests) == 1:
            events = [event({"tool_calls": [{"index": 0, "id": "read", "type": "function", "function": {
                "name": "read_file", "arguments": '{"path":'}}]}),
                event({"tool_calls": [{"index": 0, "function": {"arguments": '"fixture.txt"}'}}]}),
                event(finish="tool_calls")]
        else:
            assert len(requests) == 2
            assert payload["messages"][-1]["role"] == "tool"
            assert "synthetic stream fixture" in payload["messages"][-1]["content"]
            events = [event({"content": "Verified "}), event({"content": "answer"}), event(finish="stop")]
        events.append({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}})
        return httpx.Response(200, content=wire(events))

    async def no_services():
        return

    async def scenario():
        provider = agent.provider.provider_manager.registry.get("nebius")
        await provider.close()
        provider.client = httpx.AsyncClient(base_url="https://fixture.invalid/v1", transport=httpx.MockTransport(handler))
        agent._ensure_services_started = no_services
        agent.on_tool = lambda name, arguments: tools.append((name, arguments))
        try:
            await agent.context.start_session()
            assert "".join([part async for part in agent.ask_stream("Read fixture.txt")]) == "Verified answer"
            assert tools == [("read_file", {"path": "fixture.txt"})]
            assert len(agent.provider.requests) == 2
            assert all(receipt["usage"]["total_tokens"] == 12 for receipt in agent.provider.requests)
            assert all(receipt["reported_model"] == "server-model" for receipt in agent.provider.requests)
            messages = agent.context.conversation_cache.get_current_session().turns[-1].metadata["messages"]
            assistants = [message for message in messages if message["role"] == "assistant"]
            assert len(assistants) == 2
            assert all(message["routing"]["reported_model"] == "server-model" for message in assistants)
            assert assistants[0]["tool_calls"][0]["function"]["arguments"] == '{"path":"fixture.txt"}'
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_closing_stream_releases_http_response_without_waiting_for_more_data():
    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield wire([event({"content": "partial"})], done=False)
            await asyncio.Event().wait()

        async def aclose(self):
            self.closed = True

    async def scenario():
        body = Body()
        provider = NebiusProvider(ProviderConfig(name="test"))
        await provider.close()
        provider.client = httpx.AsyncClient(base_url="https://fixture.invalid/v1",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)))
        try:
            response = provider.complete_stream([], "requested")
            assert (await anext(response)).content == "partial"
            await response.aclose()
            assert body.closed
        finally:
            await provider.close()

    asyncio.run(scenario())


def test_closing_agent_stream_closes_every_transport_layer(tmp_path):
    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield wire([event({"content": "partial"})], done=False)
            await asyncio.Event().wait()

        async def aclose(self):
            self.closed = True

    async def no_services():
        return

    async def scenario():
        body = Body()
        config = Config(enable_memory=False, enable_conversation_history=False, providers={"nebius": ProviderConfig(
            name="nebius", default_model="requested", base_url="https://fixture.invalid/v1")})
        agent = Agent(config, Workspace(tmp_path, tmp_path))
        agent._ensure_services_started = no_services
        provider = agent.provider.provider_manager.registry.get("nebius")
        await provider.close()
        provider.client = httpx.AsyncClient(base_url="https://fixture.invalid/v1",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)))
        try:
            response = agent.ask_stream("hello")
            assert await anext(response) == "partial"
            await response.aclose()
            assert body.closed
        finally:
            await agent.close()

    asyncio.run(scenario())
