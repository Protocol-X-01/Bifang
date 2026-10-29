import asyncio

from textual.widgets import Input, RichLog, TabbedContent

from bifang.agent import Agent
from bifang.config import Config
from bifang.tui import BifangApp
from bifang.workspace import Workspace


def test_keyboard_setup_tab_order_and_evidence_never_leave_focus_hidden(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    agent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path))

    async def scenario():
        app = BifangApp(agent)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.press("f2")
                await pilot.pause()
                assert app.screen.focused.id == "engineering-prompt"
                for identity in ("engineering-files", "engineering-writable", "engineering-command",
                                 "engineering-build", "engineering-check", "engineering-review",
                                 "engineering-stage", "engineering-apply", "engineering-cancel"):
                    await pilot.press("tab")
                    await pilot.pause()
                    assert app.screen.focused.id == identity
                    assert app.screen.focused.region.width > 0
                    assert 0 <= app.screen.focused.region.y < 23
                app.engineering_panel.report("Literal [bold]receipt[/bold]")
                await pilot.pause()
                assert app.screen.focused.id == "engineering-receipt"
                assert app.screen.focused.region.height > 0
                await pilot.press("tab")
                await pilot.pause()
                assert app.screen.focused.id == "engineering-build"
                await pilot.press("f6")
                await pilot.pause()
                assert app.screen.focused.id == "engineering-prompt"
                await pilot.press("f7")
                await pilot.pause()
                assert app.screen.focused.id == "engineering-receipt"
                await pilot.press("f2")
                await pilot.pause()
                assert app.screen.focused.id == "chat-input"
                assert app.screen.focused.region.height == 3
                app.engineering_panel.report("Background result while inspector is closed.")
                await pilot.pause()
                assert app.screen.focused.id == "chat-input"
                assert app.query_one("#center-panel").display
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_keyboard_shortcuts_restore_correct_view_after_direct_tab_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    agent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path))

    async def scenario():
        app = BifangApp(agent)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.press("f6")
                await pilot.pause()
                app.query_one("#right-panel TabbedContent", TabbedContent).active = "metrics-tab"
                await pilot.pause()
                await pilot.press("f6")
                await pilot.pause()
                assert app.screen.focused.id == "engineering-prompt"
                await pilot.press("f1")
                await pilot.pause()
                assert app.query_one("#center-panel").display
                assert app.query_one("#center-panel TabbedContent").active == "chat-tab"
                text = "\n".join(line.text for line in app.query_one("#chat-log", RichLog).lines)
                assert "Engineering setup and first field" in text
                app.query_one("#chat-input", Input).value = "/quit"
                await pilot.press("enter")
        finally:
            await agent.close()

    asyncio.run(scenario())
