import asyncio
import os
import sqlite3

import pytest

from bifang.agent import SYSTEM, Agent
from bifang.config import Config
from bifang.context.kv_cache import ConversationKVCache
from bifang.context.manager import ContextManager
from bifang.workspace import Workspace


def manager(tmp_path, project="project"):
    context = ContextManager(Config(conversation_cache_path=str(tmp_path / project)))
    context.add_message({"role": "system", "content": SYSTEM})
    return context


def complete_turn(context, question="quoted CSV", answer="Use csv.reader"):
    context.add_message({"role": "user", "content": question})
    context.add_message({"role": "assistant", "content": answer})


def test_complete_tool_history_is_durable_and_resumes_without_tool_execution(tmp_path):
    async def scenario():
        original = manager(tmp_path)
        identity = await original.start_session()
        assert original.get_current_session_id() == identity
        original.add_message({"role": "user", "content": "Read receipts.py"})
        original.add_message({"role": "assistant", "content": None, "tool_calls": [
            {"id": "read-1", "type": "function", "function": {
                "name": "read_file", "arguments": '{"path":"receipts.py"}',
            }},
        ]})
        original.add_message({"role": "tool", "tool_call_id": "read-1", "content": "original source"})
        original.add_message({"role": "assistant", "content": "Read and verified"})
        expected = list(original.get_messages())
        second = manager(tmp_path)
        await second.start_session(identity)
        assert second.get_messages() == expected
        assert second.get_conversation_stats()["turn_count"] == 1
        assert second.get_conversation_context("receipts.py")
        await second.start_session(identity)
        assert second.get_conversation_stats()["turn_count"] == 1
        await original.close()
        await second.close()
        if os.name == "posix":
            assert (tmp_path / "project/conversations.db").stat().st_mode & 0o777 == 0o600

    asyncio.run(scenario())


def test_new_session_has_no_previous_context_and_alias_survives(tmp_path):
    async def scenario():
        context = manager(tmp_path)
        messages = context.get_messages()
        first = await context.start_conversation()
        complete_turn(context)
        second = await context.start_session()
        assert first != second
        assert context.get_messages() is messages
        assert messages == [{"role": "system", "content": SYSTEM}]
        assert await context.end_conversation(first) == first
        assert context.get_current_session_id() == second
        complete_turn(context, "new project decision", "confirmed")
        await context.end_conversation()
        assert context.get_current_session_id() is None
        assert context.get_messages() == [{"role": "system", "content": SYSTEM}]
        third = await context.start_session()
        assert third not in (first, second)
        assert context.get_conversation_stats()["turn_count"] == 0
        await context.close()

    asyncio.run(scenario())


def test_independent_writers_do_not_overwrite_each_others_sessions(tmp_path):
    async def scenario():
        first = manager(tmp_path)
        second = manager(tmp_path)
        first_id = await first.start_session()
        second_id = await second.start_session()
        complete_turn(first, "first writer", "first response")
        complete_turn(second, "second writer", "second response")
        complete_turn(first, "another first turn", "retained")
        await second.close()
        await first.close()
        fresh = manager(tmp_path)
        await fresh.initialize()
        sessions = fresh.conversation_cache.cache.list_sessions()
        assert {session.session_id: len(session.turns) for session in sessions} == {
            first_id: 2, second_id: 1,
        }
        await fresh.start_session(first_id)
        assert "second writer" not in str(fresh.get_messages())
        await fresh.close()

    asyncio.run(scenario())


def test_same_session_append_does_not_replace_existing_turns(tmp_path):
    async def scenario():
        first = manager(tmp_path)
        second = manager(tmp_path)
        identity = await first.start_session()
        await second.start_session(identity)
        complete_turn(first, "first append", "one")
        complete_turn(second, "second append", "two")
        turns = first.conversation_cache.cache.get_session(identity).turns
        assert [turn.user_message for turn in turns] == ["first append", "second append"]
        await first.close()
        await second.close()

    asyncio.run(scenario())


def test_rapid_session_ids_do_not_collide(tmp_path):
    cache = ConversationKVCache(tmp_path)
    try:
        identities = {cache.create_session().session_id for _ in range(50)}
        assert len(identities) == 50
        assert len(cache.list_sessions()) == 50
    finally:
        cache.close()


def test_corrupt_database_is_not_silently_replaced(tmp_path):
    (tmp_path / "conversations.db").write_bytes(b"not a SQLite database")
    cache = ConversationKVCache(tmp_path)
    with pytest.raises(sqlite3.DatabaseError):
        asyncio.run(cache.load())
    assert (tmp_path / "conversations.db").read_bytes() == b"not a SQLite database"


@pytest.mark.parametrize("stream", [False, True])
def test_agent_automatically_records_complete_turns(tmp_path, monkeypatch, stream):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def no_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    agent = Agent(Config(enable_memory=False), Workspace(tmp_path, tmp_path))

    async def complete(*args, **kwargs):
        return {"role": "assistant", "content": "actual answer"}

    async def complete_stream(*args, **kwargs):
        yield await complete(*args, **kwargs)

    agent.provider.complete = complete
    agent.provider.complete_stream = complete_stream

    async def scenario():
        try:
            if stream:
                _ = [chunk async for chunk in agent.ask_stream("real question")]
            else:
                assert await agent.ask("real question") == "actual answer"
            assert agent.context.get_conversation_stats()["turn_count"] == 1
            turn = agent.context.conversation_cache.get_current_session().turns[0]
            assert turn.user_message == "real question"
            assert turn.assistant_response == "actual answer"
            assert turn.metadata["status"] == "completed"
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_failed_tool_turn_is_recorded_but_not_replayed(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def no_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    agent = Agent(Config(enable_memory=False), Workspace(tmp_path, tmp_path))

    async def complete(*args, **kwargs):
        return {"role": "assistant", "content": None, "tool_calls": [
            {"id": "read-1", "function": {"name": "read_file", "arguments": "{}"}},
        ]}

    async def failed_tool(*args):
        raise RuntimeError("synthetic tool failure")

    agent.provider.complete = complete
    agent.tool = failed_tool

    async def scenario():
        try:
            with pytest.raises(RuntimeError, match="synthetic"):
                await agent.ask("read something")
            identity = agent.context.get_current_session_id()
            turn = agent.context.conversation_cache.get_current_session().turns[0]
            assert turn.metadata["status"] == "failed"
            assert agent.messages == [{"role": "system", "content": SYSTEM}]
            await agent.context.start_session(identity)
            assert agent.messages == [{"role": "system", "content": SYSTEM}]
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_cancelled_turn_releases_lock_and_does_not_leave_orphan_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def no_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    agent = Agent(Config(enable_memory=False), Workspace(tmp_path, tmp_path))

    async def scenario():
        started = asyncio.Event()

        async def wait(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        agent.provider.complete = wait
        request = asyncio.create_task(agent.ask("interrupted question"))
        try:
            await asyncio.wait_for(started.wait(), 2)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            assert agent.context.conversation_cache.get_current_session().turns[0].metadata["status"] == "cancelled"
            assert agent.messages == [{"role": "system", "content": SYSTEM}]

            async def complete(*args, **kwargs):
                return {"role": "assistant", "content": "recovered"}

            agent.provider.complete = complete
            assert await asyncio.wait_for(agent.ask("new question"), 2) == "recovered"
        finally:
            if not request.done():
                request.cancel()
            await agent.close()

    asyncio.run(scenario())


def test_disabled_history_writes_no_conversation_database(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    context = ContextManager(Config(enable_conversation_history=False,
                                    conversation_cache_path=str(tmp_path / "disabled")))
    context.add_message({"role": "system", "content": SYSTEM})
    context.begin_request()
    complete_turn(context)
    assert context.get_conversation_stats() == {"active": False}
    with pytest.raises(ValueError, match="disabled"):
        asyncio.run(context.start_session())
    asyncio.run(context.close())
    assert not (tmp_path / "disabled").exists()


def test_add_conversation_turn_and_clear_keep_instructions_and_alias(tmp_path):
    async def scenario():
        context = manager(tmp_path)
        await context.start_session()
        context.add_conversation_turn("manual question", "manual answer")
        assert context.get_conversation_stats()["turn_count"] == 1
        context.add_message({"role": "user", "content": "unfinished question"})
        messages = context.get_messages()
        context.clear()
        assert context.get_messages() is messages
        assert messages == [{"role": "system", "content": SYSTEM}]
        assert context.get_conversation_stats()["turn_count"] == 2
        await context.close()

    asyncio.run(scenario())


def test_default_history_is_separated_by_original_project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def scenario():
        first = ContextManager(Config(), project_path=tmp_path / "one")
        second = ContextManager(Config(), project_path=tmp_path / "two")
        shared = ContextManager(Config(), project_path=tmp_path / "one")
        try:
            identity = await first.start_session()
            complete_turn(first, "project-one knowledge", "only here")
            await second.initialize()
            assert second.conversation_cache.cache.get_session(identity) is None
            await shared.start_session(identity)
            assert shared.get_conversation_stats()["turn_count"] == 1
        finally:
            await first.close()
            await second.close()
            await shared.close()

    asyncio.run(scenario())


def test_resume_rejects_orphan_tool_results(tmp_path):
    async def scenario():
        context = manager(tmp_path)
        identity = await context.start_session()
        context.add_conversation_turn("question", "answer", metadata={
            "status": "completed", "messages": [
                {"role": "tool", "tool_call_id": "missing", "content": "unpaired output"},
            ],
        })
        try:
            with pytest.raises(ValueError, match="orphan tool"):
                await context.start_session(identity)
        finally:
            await context.close()

    asyncio.run(scenario())
