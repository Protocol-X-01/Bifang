import asyncio
import json

import pytest
import httpx

from bifang import server
from bifang.agent import Agent
from bifang.config import Config
from bifang.tools.tasks import TaskPlan
from bifang.workspace import Workspace


def item(**changes):
    return {"content": "Inspect files", "status": "pending", "priority": "high", **changes}


def test_plan_replaces_clears_and_does_not_expose_mutable_state():
    plan = TaskPlan()
    incoming = [item()]
    assert plan.replace(incoming) == {"revision": 1, "todos": incoming}
    incoming[0]["content"] = "External mutation"
    snapshot = plan.snapshot()
    snapshot["todos"][0]["content"] = "Another mutation"
    assert plan.snapshot()["todos"][0]["content"] == "Inspect files"
    assert plan.replace([item(status="completed")])["revision"] == 2
    assert plan.replace([]) == {"revision": 3, "todos": []}


@pytest.mark.parametrize("invalid", [None, {}, [item(content=" ")], [item(content="x" * 1001)],
    [item(status="invented")], [item(priority="urgent")], [item(extra="field")],
    [item(status="in_progress"), item(content="Second", status="in_progress")],
    [item()] * 101])
def test_rejected_updates_preserve_last_valid_state(invalid):
    plan = TaskPlan()
    valid = plan.replace([item()])
    with pytest.raises(ValueError):
        plan.replace(invalid)
    assert plan.snapshot() == valid


def test_agent_tool_state_isolated_and_readable_in_observe_mode(tmp_path):
    config = Config(enable_memory=False, enable_conversation_history=False, mode="observe")
    first = Agent(config, Workspace(tmp_path, tmp_path))
    second = Agent(config, Workspace(tmp_path, tmp_path))

    async def scenario():
        try:
            updated = json.loads(await first.tool("todo_write", {"todos": [item()]}))
            assert json.loads(await first.tool("todo_read", {})) == updated
            assert json.loads(await second.tool("todo_read", {})) == {"revision": 0, "todos": []}
            assert "error" in (await first.tool("todo_write", {"todos": [item(status="invalid")]})).lower()
            assert json.loads(await first.tool("todo_read", {})) == updated
            names = {schema["function"]["name"] for schema in first._get_tools_schema()}
            assert {"todo_write", "todo_read"} <= names
        finally:
            await first.close()
            await second.close()

    asyncio.run(scenario())


def test_task_plan_http_read_is_session_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    plan = TaskPlan()
    snapshot = plan.replace([item()])
    from types import SimpleNamespace
    session = server.Session(id="one", agent=SimpleNamespace(tasks=plan), created_at=0)
    monkeypatch.setattr(server, "sessions", {"one": session})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            response = await client.get("/sessions/one/tasks")
            assert response.status_code == 200
            assert response.json() == snapshot
            assert (await client.get("/sessions/absent/tasks")).status_code == 404
        assert plan.snapshot() == snapshot

    asyncio.run(scenario())
