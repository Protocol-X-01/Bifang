import asyncio

from bifang.agent import Agent
from bifang.config import Config
from bifang.tui import BifangApp
from bifang.workspace import Workspace


def test_branded_terminal_fits_normal_width_and_inspector_is_keyboard_accessible(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    async def scenario():
        agent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path))
        app = BifangApp(agent)
        try:
            async with app.run_test(size=(100, 36)) as pilot:
                await pilot.pause()
                assert app.query_one("#center-panel").region.width > 50
                assert app.query_one("#chat-input").region.height == 3
                assert app.query_one("#chat-input").region.bottom <= 35
                assert not app.query_one("#right-panel").display
                app.action_toggle_verify()
                await pilot.pause()
                assert app.query_one("#right-panel").display
                assert not app.query_one("#center-panel").display
                app.action_toggle_verify()
                await pilot.pause()
                assert app.query_one("#center-panel").display
                await pilot.resize_terminal(80, 24)
                await pilot.pause()
                assert not app.query_one("#left-panel").display
                assert app.query_one("#center-panel").region.width == 80
                await pilot.resize_terminal(220, 50)
                await pilot.pause()
                assert app.query_one("#far-right-panel").display
        finally:
            await agent.close()

    asyncio.run(scenario())
