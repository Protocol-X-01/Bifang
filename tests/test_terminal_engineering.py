import asyncio
import json
import os
import subprocess

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, RichLog

from bifang.agent import Agent
from bifang.config import Config
from bifang.tui import BifangApp, DiffViewer, FileTree, ToolApprovalScreen
from bifang.workspace import Workspace

IMMUTABLE_TEST = (
    "import unittest\nfrom bounds import answer\n"
    "class BoundsTest(unittest.TestCase):\n"
    "    def test_answer(self):\n        self.assertEqual(answer, 42)\n"
)


def repository(tmp_path):
    source = tmp_path / "source"
    box = tmp_path / "box"
    source.mkdir()
    for command in (["init", str(source)], ["-C", str(source), "config", "user.name", "Fixture"],
                    ["-C", str(source), "config", "user.email", "fixture@example.test"]):
        subprocess.run(["git", *command], check=True, capture_output=True)
    (source / "bounds.py").write_text("answer = 0\n")
    (source / "test_bounds.py").write_text(IMMUTABLE_TEST)
    for command in (["add", "."], ["commit", "-m", "fixture"], ["worktree", "add", "--detach", str(box), "HEAD"]):
        subprocess.run(["git", "-C", str(source), *command], check=True, capture_output=True)
    return Workspace(source, box, isolated=True)


async def wait_for(pilot, predicate):
    for _attempt in range(100):
        if predicate():
            return
        await pilot.pause(0.01)
    raise AssertionError("Expected terminal state did not arrive")


async def press_action(app, pilot, name):
    app.engineering_panel.query_one(f"#engineering-{name}", Button).focus()
    await pilot.press("enter")
    await pilot.pause()


async def approve(app, pilot, expected, allow=True):
    await wait_for(pilot, lambda: isinstance(app.screen, ToolApprovalScreen) and expected in app.screen.prompt)
    app.screen.query_one("#approval-allow" if allow else "#approval-deny", Button).focus()
    await pilot.press("enter")
    await pilot.pause()


def fixture_provider(monkeypatch):
    providers = []

    class Provider:
        def __init__(self):
            self.requests = []
            self.closed = False
            providers.append(self)

        async def complete(self, *args, **kwargs):
            self.requests.append({"provider": "synthetic"})
            if len(self.requests) == 1:
                return {"role": "assistant", "content": "", "tool_calls": [{"id": "write", "type": "function",
                    "function": {"name": "write_file", "arguments": json.dumps({
                        "path": "bounds.py", "content": "answer = 42\n"})}}]}
            return {"role": "assistant", "content": "Tests passed: unsupported model claim"}

        async def close(self):
            self.closed = True

    monkeypatch.setattr("bifang.agent.create_tiered_provider", lambda config: Provider())
    return providers


def setup_fields(app):
    panel = app.engineering_panel
    for selector, value in {
        "prompt": "Fix bounds.py; keep the tests unchanged.",
        "files": '["bounds.py", "test_bounds.py"]',
        "writable": '["bounds.py"]',
        "command": '["fixture-check"]',
    }.items():
        panel.query_one(f"#engineering-{selector}", Input).value = value


@pytest.mark.parametrize("real_check", [False, pytest.param(True, marks=pytest.mark.skipif(
    os.getenv("BIFANG_TEST_REAL_BWRAP") != "1", reason="Explicit real Bubblewrap execution opt-in"))])
def test_terminal_candidate_check_review_stage_and_separate_original_apply(tmp_path, monkeypatch, real_check):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    workspace = repository(tmp_path)
    providers = fixture_provider(monkeypatch)
    checks = []
    executed_receipts = []

    async def check(candidate, command, **kwargs):
        assert command == ["fixture-check"]
        checks.append(candidate.describe()["candidate_sha256"])
        return {"passed": len(checks) == 2, "returncode": 1 if len(checks) == 1 else 0,
                "candidate_sha256": checks[-1], "scope": "synthetic UI orchestration only"}

    if not real_check:
        monkeypatch.setattr("bifang.implementation.verify_candidate", check)
    agent = Agent(Config(enable_memory=False, enable_conversation_history=False), workspace)

    async def scenario():
        app = BifangApp(agent)
        try:
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.press("f2")
                setup_fields(app)
                panel = app.engineering_panel
                if real_check:
                    panel.query_one("#engineering-command", Input).value = json.dumps(
                        ["python3", "-B", "-c", "raise SystemExit(1)"])
                await press_action(app, pilot, "build")
                await approve(app, pilot, "Share selected source", allow=False)
                await wait_for(pilot, lambda: not panel.busy)
                assert len(providers) == 1 and not providers[0].requests
                assert panel.workflow is None
                await press_action(app, pilot, "build")
                await approve(app, pilot, "Share selected source")
                await approve(app, pilot, "write bounds.py")
                await wait_for(pilot, lambda: not panel.busy)
                assert panel.workflow.status == "ready"
                assert panel.workflow.result["verification"] == "unverified_model_analysis"
                assert (workspace.root / "bounds.py").read_text() == "answer = 0\n"
                assert (workspace.source / "bounds.py").read_text() == "answer = 0\n"
                await press_action(app, pilot, "stage")
                await wait_for(pilot, lambda: not panel.busy)
                assert panel.workflow.status == "ready"
                await press_action(app, pilot, "review")
                await wait_for(pilot, lambda: not panel.busy)
                await press_action(app, pilot, "check")
                await approve(app, pilot, "exact argv")
                await wait_for(pilot, lambda: not panel.busy)
                assert panel.workflow.status == "check_failed"
                if real_check:
                    assert panel.workflow.receipt["verification"] == "executed_check"
                    assert panel.workflow.receipt["returncode"] == 1
                    executed_receipts.append(dict(panel.workflow.receipt))
                    panel.query_one("#engineering-command", Input).value = json.dumps(
                        ["python3", "-B", "-m", "unittest", "discover", "-v"])
                await press_action(app, pilot, "stage")
                await wait_for(pilot, lambda: not panel.busy)
                assert panel.workflow.status == "check_failed"
                await press_action(app, pilot, "check")
                await approve(app, pilot, "exact argv")
                await wait_for(pilot, lambda: not panel.busy)
                assert panel.workflow.status == "verified"
                if real_check:
                    assert panel.workflow.receipt["returncode"] == 0
                    assert "OK" in panel.workflow.receipt["stderr"]["text"]
                    executed_receipts.append(dict(panel.workflow.receipt))
                (panel.workflow.candidate.root / "bounds.py").write_text("unreviewed mutation\n")
                await press_action(app, pilot, "stage")
                await wait_for(pilot, lambda: not panel.busy)
                assert not isinstance(app.screen, ToolApprovalScreen)
                assert (workspace.root / "bounds.py").read_text() == "answer = 0\n"
                (panel.workflow.candidate.root / "bounds.py").write_text("answer = 42\n")
                await press_action(app, pilot, "stage")
                await approve(app, pilot, "Stage reviewed", allow=False)
                await wait_for(pilot, lambda: not panel.busy)
                assert (workspace.root / "bounds.py").read_text() == "answer = 0\n"
                await press_action(app, pilot, "stage")
                await approve(app, pilot, "Stage reviewed")
                await wait_for(pilot, lambda: not panel.busy)
                assert (workspace.root / "bounds.py").read_text() == "answer = 42\n"
                assert (workspace.source / "bounds.py").read_text() == "answer = 0\n"
                (workspace.root / "bounds.py").write_text("stale staged mutation\n")
                await press_action(app, pilot, "apply")
                await wait_for(pilot, lambda: not panel.busy)
                assert not isinstance(app.screen, ToolApprovalScreen)
                assert (workspace.source / "bounds.py").read_text() == "answer = 0\n"
                (workspace.root / "bounds.py").write_text("answer = 42\n")
                await press_action(app, pilot, "apply")
                await approve(app, pilot, "ORIGINAL checkout", allow=False)
                await wait_for(pilot, lambda: not panel.busy)
                assert (workspace.source / "bounds.py").read_text() == "answer = 0\n"
                await press_action(app, pilot, "apply")
                await wait_for(pilot, lambda: isinstance(app.screen, ToolApprovalScreen))
                (workspace.root / "bounds.py").write_text("mutation during confirmation\n")
                await approve(app, pilot, "ORIGINAL checkout")
                await wait_for(pilot, lambda: not panel.busy)
                assert panel.workflow.status == "staged"
                assert (workspace.source / "bounds.py").read_text() == "answer = 0\n"
                (workspace.root / "bounds.py").write_text("answer = 42\n")
                await press_action(app, pilot, "apply")
                await approve(app, pilot, "ORIGINAL checkout")
                await wait_for(pilot, lambda: not panel.busy)
                assert panel.workflow.status == "applied"
                assert (workspace.source / "bounds.py").read_text() == "answer = 42\n"
                assert (workspace.source / "test_bounds.py").read_text() == IMMUTABLE_TEST
                log = "\n".join(line.text for line in panel.query_one("#engineering-receipt", RichLog).lines)
                assert "CHECK check_failed" in log
                assert "CHECK verified" in log
                assert "ORIGINAL APPLY: applied" in log
                candidate_root = panel.workflow.candidate.root
            assert not candidate_root.exists()
            if real_check:
                (tmp_path / "terminal-proof.json").write_text(json.dumps({
                    "scope": "Headless Textual 80x24 keyboard UI; synthetic model; actual host Bubblewrap checks",
                    "status": "passed", "checks": executed_receipts,
                    "original_unchanged_before_separate_apply": True,
                    "stale_candidate_and_staged_patch_rejected": True,
                    "mutation_during_apply_confirmation_rejected": True,
                    "original_apply_exact": True, "tests_unchanged": True,
                    "candidate_storage_removed_on_exit": True,
                    "hosted_model_requests": 0,
                }, indent=2) + "\n")
        finally:
            await agent.close()
        assert all(provider.closed for provider in providers)

    asyncio.run(scenario())


def test_workspace_expected_patch_digest_blocks_stale_review(tmp_path):
    workspace = repository(tmp_path)
    (workspace.root / "bounds.py").write_text("answer = 42\n")
    try:
        workspace.apply(expected_patch_sha256="0" * 64)
    except RuntimeError as error:
        assert "changed after review" in str(error)
    else:
        raise AssertionError("Stale patch digest must refuse Apply")
    assert (workspace.source / "bounds.py").read_text() == "answer = 0\n"


def test_terminal_diff_selects_exact_file_and_keeps_markup_literal(tmp_path):
    workspace = repository(tmp_path)
    (workspace.root / "bounds.py").write_text("[bold]literal source[/bold]\n")
    (workspace.root / "bounds.py.extra").write_text("wrong file must not appear\n")

    class Viewer(App):
        def compose(self) -> ComposeResult:
            yield DiffViewer()

    async def scenario():
        async with Viewer().run_test(size=(100, 30)) as pilot:
            viewer = pilot.app.query_one(DiffViewer)
            viewer.show_diff(workspace.root / "bounds.py", workspace)
            await pilot.pause()
            modified = "\n".join(line.text for line in viewer.query_one("#diff-modified", RichLog).lines)
            original = "\n".join(line.text for line in viewer.query_one("#diff-original", RichLog).lines)
            assert "[bold]literal source[/bold]" in modified
            assert "wrong file" not in modified
            assert "answer = 0" in original

    asyncio.run(scenario())


def test_terminal_tree_skips_symlink_cycle_and_uses_literal_labels(tmp_path):
    (tmp_path / "cycle").symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / "[bold]source.py").write_text("fixture\n")

    class Files(App):
        def compose(self) -> ComposeResult:
            yield FileTree(Workspace(tmp_path, tmp_path))

    async def scenario():
        async with Files().run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            labels = [node.label.plain for node in pilot.app.query_one(FileTree).file_tree.root.children]
            assert labels == ["[bold]source.py"]

    asyncio.run(scenario())


def test_terminal_local_commands_and_inspector_switches_do_not_invoke_models(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    providers = fixture_provider(monkeypatch)
    agent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path))

    async def scenario():
        try:
            app = BifangApp(agent)
            async with app.run_test(size=(80, 24)) as pilot:
                field = app.query_one("#chat-input", Input)
                for command in ("/help", "/status", "/sudo grant anything", "/diff"):
                    field.value = command
                    await pilot.press("enter")
                    await pilot.pause()
                assert not providers[0].requests
                text = "\n".join(line.text for line in app.query_one("#chat-log", RichLog).lines)
                assert "Unknown terminal command" in text
                assert "No model request sent" in text
                for key in ("f2", "f3", "f2"):
                    await pilot.press(key)
                    await pilot.pause()
                    assert app.query_one("#right-panel").display
                await pilot.press("f2")
                await pilot.pause()
                assert app.query_one("#center-panel").display
                field.focus()
                field.value = "/quit"
                await pilot.press("enter")
        finally:
            await agent.close()

    asyncio.run(scenario())
