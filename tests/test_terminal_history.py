import asyncio
from types import SimpleNamespace

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog

from bifang.agent import Agent
from bifang.cli import amain
from bifang.config import Config
from bifang.tui import ChatPanel
from bifang.workspace import Workspace


def test_terminal_shows_resumed_history_and_actual_streamed_response(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def no_services(self):
        return None

    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)
    agent = Agent(Config(enable_memory=False), Workspace(tmp_path, tmp_path))

    class ChatApp(App):
        def compose(self) -> ComposeResult:
            yield ChatPanel(agent)

    async def complete_stream(*args, **kwargs):
        yield {"content": "New "}
        yield {"content": "verified answer"}

    agent.provider.complete_stream = complete_stream

    async def scenario():
        try:
            await agent.context.start_session()
            agent.context.add_message({"role": "user", "content": "Previous question"})
            agent.context.add_message({"role": "assistant", "content": "Previous answer"})
            async with ChatApp().run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                log = pilot.app.query_one("#chat-log", RichLog)
                text = "\n".join(line.text for line in log.lines)
                assert "Previous question" in text
                assert "Previous answer" in text
                field = pilot.app.query_one("#chat-input", Input)
                field.value = "Follow-up question"
                await pilot.press("enter")
                await pilot.pause()
                text = "\n".join(line.text for line in log.lines)
                assert "New verified answer" in text
                assert agent.context.get_conversation_stats()["turn_count"] == 2
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_cli_lists_history_without_creating_a_worktree_or_model_request(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    config = Config(use_worktree=False, enable_memory=False)
    monkeypatch.setattr("bifang.cli.Config.load", lambda: config)
    agent = Agent(config, Workspace(tmp_path, tmp_path))

    async def scenario():
        identity = await agent.context.start_session()
        agent.context.add_conversation_turn("question", "answer")
        await agent.close()
        await amain(SimpleNamespace(cmd="conversations", workspace=str(tmp_path), provider=None))
        return identity

    identity = asyncio.run(scenario())
    assert identity in capsys.readouterr().out


@pytest.mark.parametrize("known", [False, True])
def test_cli_resume_selects_only_an_existing_conversation(tmp_path, monkeypatch, known):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    config = Config(use_worktree=False, enable_memory=False)
    monkeypatch.setattr("bifang.cli.Config.load", lambda: config)
    opened = []

    class TestApp:
        def __init__(self, agent):
            self.agent = agent

        async def run_async(self):
            opened.append(self.agent.messages[-1]["content"])

    monkeypatch.setattr("bifang.tui.BifangApp", TestApp)

    async def scenario():
        agent = Agent(config, Workspace(tmp_path, tmp_path))
        identity = await agent.context.start_session()
        agent.context.add_conversation_turn("earlier question", "saved answer")
        await agent.close()
        arguments = SimpleNamespace(cmd="chat", workspace=str(tmp_path), provider=None,
                                    session=identity if known else "unknown")
        if known:
            await amain(arguments)
            assert opened == ["saved answer"]
        else:
            with pytest.raises(RuntimeError, match="not found"):
                await amain(arguments)
            assert opened == []

    asyncio.run(scenario())
