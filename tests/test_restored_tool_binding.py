import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from bifang.agent import Agent
from bifang.config import Config
from bifang.workspace import Workspace

PRIVATE = "synthetic-private-note-without-a-credential-pattern"
PUBLIC = "ordinary public fixture"


def tool_call(identity, name="read_file", arguments=None):
    return {
        "id": identity,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps({"path": "src/public.py"} if arguments is None else arguments),
        },
    }


def tool_result(identity, content):
    return {"role": "tool", "tool_call_id": identity, "content": content}


def turn(call, content):
    return [
        {"role": "user", "content": "Inspect this synthetic fixture"},
        {"role": "assistant", "content": None, "tool_calls": [call]},
        tool_result(call["id"], content),
        {"role": "assistant", "content": "Fixture inspected"},
    ]


class RecordingProvider:
    def __init__(self):
        self.requests = []
        self.calls = []

    async def complete(self, messages, **kwargs):
        self.calls.append(("complete", copy.deepcopy(messages)))
        return {"role": "assistant", "content": "continued"}

    async def complete_stream(self, messages, **kwargs):
        self.calls.append(("complete_stream", copy.deepcopy(messages)))
        yield {"content": "continued", "finish_reason": "stop"}

    async def close(self):
        pass


@pytest.fixture
def restored_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def no_services(self):
        pass

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)

    def create(turns, approved=True):
        provider = RecordingProvider()
        prompts = []
        monkeypatch.setattr("bifang.agent.create_tiered_provider", lambda cfg: provider)
        agent = Agent(
            Config(enable_memory=False, enable_conversation_history=False,
                   enable_summarization=False, enable_tracing=False, providers={}),
            Workspace(tmp_path, tmp_path),
            approve=lambda prompt: prompts.append(prompt) or approved,
            restored_conversation=True,
        )
        agent.context._restore_history([
            SimpleNamespace(metadata={"status": "completed", "messages": messages})
            for messages in turns
        ])
        return agent, provider, prompts

    return create


async def continue_history(agent, streaming):
    if streaming:
        return "".join([part async for part in agent.ask_stream("Continue")])
    return await agent.ask("Continue")


@pytest.mark.parametrize("streaming", [False, True], ids=["ask", "ask_stream"])
@pytest.mark.parametrize("reuse_id", [True, False], ids=["repeated_id", "distinct_ids"])
@pytest.mark.parametrize("later_tool", ["read_file", "git_diff"])
def test_history_results_bind_to_their_own_batch(restored_agent, streaming, reuse_id, later_tool):
    async def scenario():
        agent, provider, prompts = restored_agent([
            turn(tool_call("read-1", arguments={"path": "secrets.json"}), PRIVATE),
            turn(tool_call("read-1" if reuse_id else "read-2", later_tool,
                           {"path": "src/public.py"} if later_tool == "read_file" else {}), PUBLIC),
        ])
        try:
            assert await continue_history(agent, streaming) == "continued"
            assert len(prompts) == 1
            assert "saved conversation history" in prompts[0]
            assert len(provider.calls) == 1
            mode, messages = provider.calls[0]
            assert mode == ("complete_stream" if streaming else "complete")
            results = [message["content"] for message in messages if message["role"] == "tool"]
            assert PRIVATE not in json.dumps(messages)
            assert "omitted on restore" in results[0]
            assert results[1] == PUBLIC
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("streaming", [False, True], ids=["ask", "ask_stream"])
def test_denied_history_never_invokes_provider(restored_agent, streaming):
    async def scenario():
        agent, provider, prompts = restored_agent([
            turn(tool_call("reused", arguments={"path": "secrets.json"}), PRIVATE),
            turn(tool_call("reused"), PUBLIC),
        ], approved=False)
        try:
            assert (await continue_history(agent, streaming)).startswith("DENIED:")
            assert len(prompts) == 1
            assert provider.calls == []
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("streaming", [False, True], ids=["ask", "ask_stream"])
def test_distinct_batch_results_keep_filters_and_all_existing_redaction(restored_agent, streaming):
    user_value = "synthetic-user-assignment-value"
    assistant_value = "synthetic-assistant-assignment-value"
    argument_value = "synthetic-argument-assignment-value"
    result_value = "synthetic-result-assignment-value"
    messages = [
        {"role": "user", "content": f"NVIDIA_API_KEY={user_value}"},
        {"role": "assistant", "content": f"API_KEY={assistant_value}", "tool_calls": [
            tool_call("public"),
            tool_call("private", arguments={"path": "secrets.json"}),
            tool_call("list", "list_files", {}),
            tool_call("search", "search", {"query": f"client_secret={argument_value}"}),
        ]},
        tool_result("search", f"secrets.json:1:{PRIVATE}\nsrc/public.py:2:{PUBLIC}"),
        tool_result("private", PRIVATE),
        tool_result("list", "secrets.json\n.bifang/state.json\nsrc/public.py"),
        tool_result("public", f"1: {PUBLIC}\n2: TOKEN={result_value}"),
        {"role": "assistant", "content": "Fixture inspected"},
    ]

    async def scenario():
        agent, provider, _ = restored_agent([messages])
        try:
            assert await continue_history(agent, streaming) == "continued"
            assert len(provider.calls) == 1
            captured = provider.calls[0][1]
            results = {message["tool_call_id"]: message["content"]
                       for message in captured if message["role"] == "tool"}
            assert results["search"] == f"src/public.py:2:{PUBLIC}"
            assert results["list"] == "src/public.py"
            assert PUBLIC in results["public"]
            assert "omitted on restore" in results["private"]
            serialized = json.dumps(captured)
            for value in (PRIVATE, user_value, assistant_value, argument_value, result_value):
                assert value not in serialized
            assert "[REDACTED]" in results["public"]
            assistant = next(message for message in captured if message.get("tool_calls"))
            assert "[REDACTED]" in assistant["content"]
            assert "[REDACTED]" in assistant["tool_calls"][3]["function"]["arguments"]
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("other_tool", ["read_file", "git_diff"])
def test_duplicate_call_ids_in_one_batch_are_unverifiable(reverse, other_tool):
    calls = [tool_call("duplicate", arguments={"path": "secrets.json"}),
             tool_call("duplicate", other_tool)]
    if reverse:
        calls.reverse()
    messages = [{"role": "assistant", "tool_calls": calls}, tool_result("duplicate", PRIVATE)]

    Agent._sanitize_restored_tool_history(messages)

    assert PRIVATE not in messages[1]["content"]
    assert "omitted on restore" in messages[1]["content"]


def test_duplicate_results_in_one_batch_are_both_unverifiable():
    messages = [
        {"role": "assistant", "tool_calls": [tool_call("duplicate")]},
        tool_result("duplicate", PRIVATE),
        tool_result("duplicate", "another synthetic private note"),
    ]

    Agent._sanitize_restored_tool_history(messages)

    assert all("omitted on restore" in message["content"] for message in messages[1:])


@pytest.mark.parametrize("boundary", [None, "assistant", "user", "system"])
def test_orphan_results_cannot_borrow_a_past_or_future_batch(boundary):
    messages = []
    if boundary is not None:
        messages.extend([
            {"role": "assistant", "tool_calls": [tool_call("reused")]},
            {"role": boundary, "content": "Batch boundary"},
        ])
    orphan = tool_result("reused", PRIVATE)
    messages.extend([orphan, {"role": "assistant", "tool_calls": [tool_call("reused")]}])

    Agent._sanitize_restored_tool_history(messages)

    assert PRIVATE not in orphan["content"]
    assert "omitted on restore" in orphan["content"]


@pytest.mark.parametrize("identity", ["unknown", None, "", ["invalid"]])
def test_missing_unknown_and_invalid_result_ids_fail_closed(identity):
    messages = [
        {"role": "assistant", "tool_calls": [tool_call("expected")]},
        tool_result(identity, PRIVATE),
    ]

    Agent._sanitize_restored_tool_history(messages)

    assert PRIVATE not in messages[1]["content"]
    assert "omitted on restore" in messages[1]["content"]
