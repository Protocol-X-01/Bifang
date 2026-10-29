import asyncio
import copy
from types import SimpleNamespace

import pytest

from bifang.agent import SYSTEM, Agent
from bifang.config import Config
from bifang.context.manager import ContextManager
from bifang.context.summarizer import ContextSummary, HeuristicSummarizer, LLMSummarizer
from bifang.routing import TieredProviderManager
from bifang.workspace import Workspace


def test_agent_and_context_share_system_and_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    agent = Agent(Config(enable_memory=False), Workspace(tmp_path, tmp_path))
    try:
        assert agent.messages is agent.context.get_messages()
        assert agent.messages[0] == {"role": "system", "content": SYSTEM}
    finally:
        asyncio.run(agent.close())


@pytest.mark.parametrize("use_llm", [False, True])
def test_compaction_keeps_tool_call_with_its_results(use_llm):
    messages = [
        {"role": "system", "content": "Keep the original instructions"},
        {"role": "user", "content": "old task " * 100},
        {"role": "assistant", "content": "old answer " * 100},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "read-1", "function": {"name": "read_file", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "read-1", "content": "source"},
        {"role": "assistant", "content": "latest answer"},
    ]
    async def complete(**kwargs):
        return {"content": "Old task and answer preserved as a summary."}

    summarizer = (LLMSummarizer(SimpleNamespace(complete=complete), "summary-model")
                  if use_llm else HeuristicSummarizer())
    compacted, _ = asyncio.run(summarizer.summarize_messages(
        messages, max_tokens=100, keep_recent=2,
    ))
    assert compacted[0] == messages[0]
    tool_index = next(index for index, message in enumerate(compacted) if message["role"] == "tool")
    assert compacted[tool_index - 1].get("tool_calls") == messages[3]["tool_calls"]
    assert [message for message in compacted if message["role"] == "system"] == [messages[0]]


def test_threshold_compaction_only_records_real_reductions(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    class RecordingSummarizer:
        budget = None

        async def summarize_messages(self, messages, max_tokens, **kwargs):
            self.budget = max_tokens
            return messages, ContextSummary("", 90, 90, 1.0)

    summarizer = RecordingSummarizer()
    manager = ContextManager(Config(max_context_tokens=100, summarization_threshold=0.8),
                             summarizer=summarizer)
    manager.add_message({"role": "user", "content": "x" * 360})
    assert manager.should_summarize()
    assert asyncio.run(manager.maybe_summarize()) is False
    assert summarizer.budget == 80
    assert manager.total_summarized == 0


def test_tool_arguments_count_after_compaction(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    class CompactingSummarizer:
        async def summarize_messages(self, messages, max_tokens, **kwargs):
            retained = messages[-1:]
            return retained, ContextSummary("kept call", 1, 1000, 0.01)

    manager = ContextManager(Config(max_context_tokens=100), summarizer=CompactingSummarizer())
    manager.add_message({"role": "user", "content": "x" * 4000})
    message = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "large-call", "function": {"name": "write_file", "arguments": "x" * 800}},
    ]}
    manager.add_message(message)
    original_messages = manager.get_messages()
    assert asyncio.run(manager.maybe_summarize())
    assert manager.get_messages() is original_messages
    assert manager.window.current_tokens > 200


@pytest.mark.parametrize("stream", [False, True])
def test_agent_after_compaction_appends_each_message_once(tmp_path, monkeypatch, stream):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def no_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    agent = Agent(Config(enable_memory=False, max_context_tokens=100), Workspace(tmp_path, tmp_path))
    snapshots = []

    async def complete(*args, **kwargs):
        snapshots.append(copy.deepcopy(args[0]))
        return {"role": "assistant", "content": "verified answer"}

    async def complete_stream(*args, **kwargs):
        yield await complete(*args, **kwargs)

    agent.provider.complete = complete
    agent.provider.complete_stream = complete_stream
    agent.context.summarizer = HeuristicSummarizer()
    for index in range(20):
        agent.context.add_message({"role": "user" if index % 2 == 0 else "assistant",
                                   "content": f"old message {index} " * 100})

    async def scenario():
        try:
            for prompt in ("first live task", "second live task"):
                if stream:
                    _ = [chunk async for chunk in agent.ask_stream(prompt)]
                else:
                    assert await agent.ask(prompt) == "verified answer"
            assert agent.context.total_summarized > 0
            assert agent.messages[0] == {"role": "system", "content": SYSTEM}
            assert sum(message.get("content") == "second live task" for message in agent.messages) == 1
            assert sum(message.get("content") == "verified answer" for message in agent.messages) == 2
            assert all(snapshot[0]["content"] == SYSTEM for snapshot in snapshots)
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_llm_summary_uses_tiered_provider_without_duplicate_keywords():
    calls = []

    async def complete(**kwargs):
        calls.append(kwargs)
        return {"content": "A compact summary"}

    manager = TieredProviderManager(SimpleNamespace(complete=complete), Config())
    summarizer = LLMSummarizer(manager, "configured-summary-model", "nebius")
    summary = asyncio.run(summarizer.summarize("old context " * 50, 100))
    assert summary.content == "A compact summary"
    assert calls[0]["provider"] == "nebius"
    assert calls[0]["model"] == "configured-summary-model"
