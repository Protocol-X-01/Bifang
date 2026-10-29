import asyncio
import json

import pytest
from textual.widgets import Button, Input, RichLog, Static

from bifang.agent import Agent
from bifang.config import Config
from bifang.tui import BifangApp, ChatPanel, ToolApprovalScreen
from bifang.workspace import Workspace


@pytest.mark.parametrize("decision,approved", [("approve", True), ("deny", False),
                                               ("escape", False), ("enter", False), ("cancel", False)])
def test_terminal_approval_keeps_ui_responsive_and_requires_explicit_allow(tmp_path, monkeypatch,
                                                                         decision, approved):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    async def no_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    cfg = Config(enable_memory=False, enable_conversation_history=False, approval_mode="manual")
    agent = Agent(cfg, Workspace(tmp_path, tmp_path))
    calls = []

    async def completion(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            yield {"tool_calls": [{"id": "terminal-write", "type": "function", "function": {
                "name": "write_file", "arguments": json.dumps({"path": "fix.py", "content": "answer = 42\n"})}}]}
        else:
            yield {"content": "Finished the requested turn."}

    agent.provider.complete_stream = completion
    previous = agent.approve

    async def scenario():
        try:
            app = BifangApp(agent)
            async with app.run_test(size=(80, 24)) as pilot:
                field = app.query_one("#chat-input", Input)
                field.value = "Please write the fixture file."
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(app.screen, ToolApprovalScreen)
                assert app.screen.focused.id == "approval-deny"
                assert not (tmp_path / "fix.py").exists()
                assert field.disabled
                assert len(calls) == 1
                assert app.screen.query_one("#approval-dialog").region.bottom <= 24
                if decision == "cancel":
                    await pilot.press("ctrl+x")
                elif decision in {"escape", "enter"}:
                    await pilot.press(decision)
                else:
                    button = app.screen.query_one("#approval-allow" if approved else "#approval-deny", Button)
                    button.focus()
                    await pilot.press("enter")
                if decision != "cancel":
                    await app.workers.wait_for_complete()
                await pilot.pause()
                assert not isinstance(app.screen, ToolApprovalScreen)
                assert not field.disabled
                assert not app.query_one(ChatPanel).streaming
                assert (tmp_path / "fix.py").exists() is approved
                if approved:
                    assert (tmp_path / "fix.py").read_text() == "answer = 42\n"
                rows = [json.loads(line) for line in agent.audit.path.read_text().splitlines()]
                approvals = [row for row in rows if row["event"] == "tool_approval"]
                if decision == "cancel":
                    assert not approvals
                    assert not any(message.get("tool_calls") for message in agent.messages)
                    field.value = "Continue without the cancelled action."
                    await pilot.press("enter")
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                    assert not (tmp_path / "fix.py").exists()
                    assert "Finished the requested turn." in "\n".join(
                        line.text for line in app.query_one("#chat-log", RichLog).lines)
                else:
                    assert approvals[0]["approved"] is approved
                    assert "Finished the requested turn." in "\n".join(
                        line.text for line in app.query_one("#chat-log", RichLog).lines)
            assert agent.approve == previous
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_terminal_approval_prompt_is_literal_text(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    agent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path))

    async def scenario():
        try:
            app = BifangApp(agent)
            async with app.run_test(size=(80, 24)) as pilot:
                screen = ToolApprovalScreen("[bold]untrusted[/bold]\nDo not auto approve")
                app.push_screen(screen)
                await pilot.pause()
                content = screen.query_one("#approval-details Static", Static)
                assert content.renderable.plain == "[bold]untrusted[/bold]\nDo not auto approve"
                await pilot.press("escape")
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_terminal_cancel_closes_provider_stream_and_allows_next_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def no_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    agent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path))
    started = asyncio.Event()
    closed = asyncio.Event()
    calls = []

    async def completion(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            try:
                started.set()
                await asyncio.Event().wait()
                yield {"content": "never"}
            finally:
                closed.set()
        else:
            yield {"content": "Next turn works."}

    agent.provider.complete_stream = completion

    async def scenario():
        try:
            app = BifangApp(agent)
            async with app.run_test(size=(100, 30)) as pilot:
                field = app.query_one("#chat-input", Input)
                field.value = "Wait until cancelled."
                await pilot.press("enter")
                await asyncio.wait_for(started.wait(), 2)
                await pilot.press("ctrl+x")
                await asyncio.wait_for(closed.wait(), 2)
                await pilot.pause()
                assert not field.disabled
                assert not app.query_one(ChatPanel).streaming
                field.value = "Try again."
                await pilot.press("enter")
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert "Next turn works." in "\n".join(
                    line.text for line in app.query_one("#chat-log", RichLog).lines)
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_terminal_shutdown_does_not_approve_pending_write(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def no_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    agent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path))
    previous = agent.approve

    async def completion(*args, **kwargs):
        yield {"tool_calls": [{"id": "pending-write", "type": "function", "function": {
            "name": "write_file", "arguments": json.dumps({"path": "pending.py", "content": "must not exist"})}}]}

    agent.provider.complete_stream = completion

    async def scenario():
        try:
            app = BifangApp(agent)
            async with app.run_test(size=(80, 24)) as pilot:
                app.query_one("#chat-input", Input).value = "Wait for my approval."
                await pilot.press("enter")
                await pilot.pause()
                assert isinstance(app.screen, ToolApprovalScreen)
            assert not (tmp_path / "pending.py").exists()
            assert agent.approve == previous
        finally:
            await agent.close()

    asyncio.run(scenario())
