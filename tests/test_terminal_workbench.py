import asyncio
import json
import os
import platform
import subprocess
from pathlib import Path

import pytest
from textual.widgets import Button, RichLog, Select, TabbedContent

from bifang.agent import Agent
from bifang.config import Config
from bifang.package_setup import sandbox_argv
from bifang.plugins.catalog import PluginCatalog, plugin_directories
from bifang.terminal_workbench import TerminalWorkbench
from bifang.tui import BifangApp, ToolApprovalScreen
from bifang.workspace import Workspace

HOST_RUSTUP_HOME = os.getenv("RUSTUP_HOME", str(Path.home() / ".rustup"))


@pytest.fixture
def setup_workbench(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "project"
    project.mkdir()
    plugins = project / ".bifang/plugins"
    plugins.mkdir(parents=True)
    source = plugins / "fixture.py"
    source.write_text('from pathlib import Path\nPath(__file__).with_suffix(".executed").write_text("no")\n# [bold]literal fixture[/bold]\n')
    (plugins / "fixture.plugin.json").write_text(json.dumps({"name": "fixture", "version": "1",
        "description": "[bold]literal description[/bold]", "capabilities": ["process"]}))
    (project / "package.json").write_text('{"scripts":{"postinstall":"must-not-run"}}')
    (project / "pnpm-lock.yaml").write_text("lockfileVersion: 9\n")
    agent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(project, project))
    return agent, source, PluginCatalog(plugin_directories(project))


async def wait_for(pilot, condition):
    for _attempt in range(100):
        if condition():
            return
        await pilot.pause(.01)
    raise AssertionError("Expected workbench state did not arrive")


async def click_action(app, pilot, action):
    app.screen.query_one(f"#workbench-{action}", Button).focus()
    await pilot.press("enter")
    await pilot.pause()


async def open_review(app, pilot, identity):
    await pilot.press("f8")
    await wait_for(pilot, lambda: isinstance(app.screen, TerminalWorkbench) and not app.screen.busy)
    assert app.screen.focused.id == "workbench-plugin-select"
    app.screen.query_one("#workbench-plugin-select", Select).value = identity
    await pilot.pause()
    await click_action(app, pilot, "review")
    await wait_for(pilot, lambda: app.screen.reviewed is not None and not app.screen.busy)


@pytest.mark.parametrize("size", [(80, 24), (120, 36)])
def test_tui_review_default_deny_exact_trust_disable_and_literal_language_preview(setup_workbench, size):
    agent, source, catalog = setup_workbench
    candidate = catalog.discover()[0][0]
    async def scenario():
        app = BifangApp(agent)
        agent.cfg.approval_mode = "full"
        try:
            async with app.run_test(size=size) as pilot:
                await open_review(app, pilot, candidate.identity)
                screen = app.screen
                assert screen.focused.id == "workbench-plugin-review"
                assert screen.focused.region.height > 0
                review = "\n".join(line.text for line in screen.query_one("#workbench-plugin-review", RichLog).lines)
                assert "[bold]literal description[/bold]" in review
                assert "[bold]literal fixture[/bold]" in review
                assert candidate.sha256 in review
                assert not source.with_suffix(".executed").exists()
                await pilot.click("#--content-tab-workbench-languages-tab")
                await pilot.pause()
                languages = "\n".join(line.text for line in screen.query_one("#workbench-languages", RichLog).lines)
                assert 'Argv: []' in languages
                assert "npm substitution is not selected" in languages
                assert not (source.parents[2] / "node_modules").exists()
                screen.query_one("#workbench-tabs", TabbedContent).active = "workbench-plugins-tab"
                await pilot.pause()
                await click_action(app, pilot, "enable")
                await wait_for(pilot, lambda: isinstance(app.screen, ToolApprovalScreen))
                assert app.screen.focused.id == "approval-deny"
                assert "full host access" in app.screen.prompt
                await pilot.press("enter")
                await wait_for(pilot, lambda: app.screen is screen and not screen.busy)
                assert not catalog.approved(candidate)
                await click_action(app, pilot, "enable")
                await wait_for(pilot, lambda: isinstance(app.screen, ToolApprovalScreen))
                app.screen.query_one("#approval-allow", Button).focus()
                await pilot.press("enter")
                await wait_for(pilot, lambda: app.screen is screen and not screen.busy)
                assert catalog.approved(candidate)
                assert not source.with_suffix(".executed").exists()
                screen.query_one("#workbench-plugin-select", Select).value = candidate.identity
                await pilot.pause()
                await click_action(app, pilot, "disable")
                await wait_for(pilot, lambda: not screen.busy)
                assert not catalog.approved(candidate)
                await pilot.press("escape")
                await pilot.pause()
                assert app.screen.focused.id == "chat-input"
        finally:
            await agent.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("decision", ["deny", "allow", "changed", "cancel"])
def test_terminal_setup_requires_explicit_fingerprint_approval_even_in_full_mode(setup_workbench, decision, monkeypatch):
    if platform.system() != "Linux" or not Path("/usr/bin/npm").is_file() or not Path("/usr/bin/bwrap").is_file():
        pytest.skip("This setup adapter requires Linux system npm and Bubblewrap")
    probe = subprocess.run(["/usr/bin/bwrap", "--unshare-all", "--ro-bind", "/", "/", "--", "/usr/bin/true"], capture_output=True, check=False)
    if probe.returncode:
        pytest.skip("Current system does not permit Bubblewrap namespaces")
    agent, _, _ = setup_workbench
    project = agent.ws.source
    (project / "pnpm-lock.yaml").unlink()
    (project / "package.json").write_text('{"name":"setup-fixture","version":"1.0.0","scripts":{"postinstall":"touch HOOK_EXECUTED"}}')
    (project / "package-lock.json").write_text('{"name":"setup-fixture","version":"1.0.0","lockfileVersion":3,"packages":{"":{"name":"setup-fixture","version":"1.0.0"}}}')
    agent.cfg.approval_mode = "full"
    if decision == "cancel":
        def workload(plan):
            arguments = sandbox_argv(plan)
            return arguments[:arguments.index("--") + 1] + ["/usr/bin/python3", "-c", "import time; print('SETUP_READY', flush=True); time.sleep(20)"]
        monkeypatch.setattr("bifang.package_setup.sandbox_argv", workload)

    async def scenario():
        app = BifangApp(agent)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.press("f8")
                await wait_for(pilot, lambda: isinstance(app.screen, TerminalWorkbench) and not app.screen.busy)
                screen = app.screen
                await click_action(app, pilot, "setup-offline")
                await wait_for(pilot, lambda: not screen.busy)
                assert screen.setup_reviewed is not None
                assert screen.focused.id == "workbench-setup" and screen.focused.region.height > 0
                fingerprint = screen.setup_reviewed["sha256"]
                await click_action(app, pilot, "setup-install")
                await wait_for(pilot, lambda: isinstance(app.screen, ToolApprovalScreen))
                if decision == "deny":
                    await pilot.press("escape")
                else:
                    if decision == "changed":
                        (project / "package.json").write_text('{"name":"changed"}')
                    app.screen.query_one("#approval-allow", Button).focus()
                    await pilot.press("enter")
                    if decision == "cancel":
                        await wait_for(pilot, lambda: app.screen is screen and any("SETUP_READY" in line.text for line in screen.query_one("#workbench-setup", RichLog).lines))
                        await pilot.press("ctrl+x")
                await wait_for(pilot, lambda: app.screen is screen and not screen.busy)
                await pilot.pause()
                assert screen.setup_reviewed is None
                assert not (project / "HOOK_EXECUTED").exists()
                receipts = list((project.parent / "state/bifang/setup-receipts").glob("*.json"))
                if decision in ("allow", "cancel"):
                    assert len(receipts) == 1
                    result = json.loads(receipts[0].read_text())
                    assert result["status"] == ("succeeded" if decision == "allow" else "cancelled")
                    assert result["plan_sha256"] == fingerprint
                else:
                    assert receipts == []
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("finish", ["changed", "cancel", "escape"])
def test_tui_revalidates_confirmation_and_cancels_pending_trust(setup_workbench, finish):
    agent, source, catalog = setup_workbench
    candidate = catalog.discover()[0][0]
    async def scenario():
        app = BifangApp(agent)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                await open_review(app, pilot, candidate.identity)
                screen = app.screen
                await click_action(app, pilot, "enable")
                await wait_for(pilot, lambda: isinstance(app.screen, ToolApprovalScreen))
                if finish == "changed":
                    source.write_text("changed = True\n")
                    app.screen.query_one("#approval-allow", Button).focus()
                    await pilot.press("enter")
                elif finish == "cancel":
                    await pilot.press("ctrl+x")
                else:
                    await pilot.press("escape")
                await wait_for(pilot, lambda: app.screen is screen and not screen.busy)
                assert not catalog.approved(catalog.select(candidate.identity))
                assert not source.with_suffix(".executed").exists()
        finally:
            await agent.close()
    asyncio.run(scenario())


def test_tui_refresh_keeps_focus_on_visible_language_tab_and_long_source_cannot_enable(setup_workbench):
    agent, source, catalog = setup_workbench
    source.write_text("pass\n" * 5001)
    candidate = catalog.discover()[0][0]
    async def scenario():
        app = BifangApp(agent)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.press("f8")
                await wait_for(pilot, lambda: isinstance(app.screen, TerminalWorkbench) and not app.screen.busy)
                screen = app.screen
                await pilot.click("#--content-tab-workbench-languages-tab")
                await pilot.pause()
                assert screen.query_one("#workbench-tabs", TabbedContent).active == "workbench-languages-tab"
                screen.query_one("#workbench-refresh", Button).focus()
                await pilot.pause()
                assert screen.focused.id == "workbench-refresh"
                assert screen.query_one("#workbench-tabs", TabbedContent).active == "workbench-languages-tab"
                await click_action(app, pilot, "refresh")
                await wait_for(pilot, lambda: not screen.busy)
                await pilot.pause()
                assert screen.focused.id == "workbench-languages"
                assert screen.focused.region.height > 0
                screen.query_one("#workbench-tabs", TabbedContent).active = "workbench-plugins-tab"
                screen.query_one("#workbench-plugin-select", Select).value = candidate.identity
                await pilot.pause()
                await click_action(app, pilot, "review")
                await wait_for(pilot, lambda: not screen.busy)
                assert screen.reviewed is None
                assert screen.query_one("#workbench-enable", Button).disabled
                assert not catalog.approved(candidate)
        finally:
            await agent.close()
    asyncio.run(scenario())


def test_tui_workbench_blocks_active_agent_and_samples_local_system(setup_workbench):
    agent, _, _ = setup_workbench
    async def scenario():
        app = BifangApp(agent)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                app.engineering_panel.busy = True
                await pilot.press("f8")
                await pilot.pause()
                assert not isinstance(app.screen, TerminalWorkbench)
                app.engineering_panel.busy = False
                await pilot.press("f8")
                await wait_for(pilot, lambda: isinstance(app.screen, TerminalWorkbench) and not app.screen.busy)
                screen = app.screen
                await click_action(app, pilot, "sample")
                await wait_for(pilot, lambda: not screen.busy)
                await pilot.pause()
                assert screen.query_one("#workbench-tabs", TabbedContent).active == "workbench-system-tab"
                text = "\n".join(line.text for line in screen.query_one("#workbench-system", RichLog).lines)
                assert '"sampled_at"' in text and '"cpu"' in text
                assert '"GPU telemetry is not configured"' in text
        finally:
            await agent.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("decision", ["deny-build", "deny-install", "allow"])
def test_rust_workbench_build_permission_is_separate_from_install_approval(setup_workbench, monkeypatch, decision):
    if platform.system() != "Linux" or not Path("/usr/bin/bwrap").is_file():
        pytest.skip("Linux Bubblewrap adapter")
    probe = subprocess.run(["/usr/bin/bwrap", "--unshare-all", "--ro-bind", "/", "/", "--", "/usr/bin/true"], capture_output=True, check=False)
    if probe.returncode:
        pytest.skip("Namespaces unavailable")
    agent, _, _ = setup_workbench
    monkeypatch.setenv("RUSTUP_HOME", HOST_RUSTUP_HOME)
    root = agent.ws.source
    (root / "Cargo.toml").write_text('[package]\nname="workbench-fixture"\nversion="1.0.0"\nedition="2021"\nbuild="build.rs"\n')
    (root / "Cargo.lock").write_text('version=4\n[[package]]\nname="workbench-fixture"\nversion="1.0.0"\n')
    (root / "src").mkdir()
    (root / "src/lib.rs").write_text('pub fn answer() -> u32 { 42 }\n')
    (root / "build.rs").write_text('fn main() { std::fs::write("WORKBENCH_BUILD_EXECUTED", "allowed").unwrap(); }\n')
    agent.cfg.approval_mode = "full"

    async def scenario():
        app = BifangApp(agent)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.press("f8")
                await wait_for(pilot, lambda: isinstance(app.screen, TerminalWorkbench) and not app.screen.busy)
                screen = app.screen
                screen.query_one("#workbench-setup-profile", Select).value = "rust-cargo-build"
                await pilot.pause()
                await click_action(app, pilot, "setup-offline")
                await wait_for(pilot, lambda: not screen.busy)
                assert screen.setup_reviewed["allow_builds"]
                await click_action(app, pilot, "setup-install")
                await wait_for(pilot, lambda: isinstance(app.screen, ToolApprovalScreen))
                if decision == "deny-build":
                    await pilot.press("escape")
                else:
                    build_prompt = app.screen
                    app.screen.query_one("#approval-allow", Button).focus()
                    await pilot.press("enter")
                    await wait_for(pilot, lambda: isinstance(app.screen, ToolApprovalScreen) and app.screen is not build_prompt)
                    if decision == "deny-install":
                        await pilot.press("escape")
                    else:
                        app.screen.query_one("#approval-allow", Button).focus()
                        await pilot.press("enter")
                await wait_for(pilot, lambda: app.screen is screen and not screen.busy)
                assert (root / "WORKBENCH_BUILD_EXECUTED").exists() is (decision == "allow")
        finally:
            await agent.close()

    asyncio.run(scenario())
