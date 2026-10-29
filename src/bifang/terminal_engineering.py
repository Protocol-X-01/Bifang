from __future__ import annotations

import asyncio
import hashlib
import json

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Input, RichLog, Static, TabbedContent, TabPane

from .agent import Agent
from .implementation import EngineeringWorkflow


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class TerminalEngineering(Widget):
    DEFAULT_CSS = """
    TerminalEngineering { height: 1fr; }
    TerminalEngineering > Vertical { height: 1fr; }
    #engineering-tabs { height: 1fr; }
    #engineering-form { height: 1fr; }
    #engineering-form Static { height: auto; }
    #engineering-form Input { height: 3; }
    #engineering-receipt { height: 1fr; }
    .engineering-actions { height: 3; }
    .engineering-actions Button { width: 1fr; min-width: 8; padding: 0; }
    #engineering-status { height: auto; }
    """

    def __init__(self, agent: Agent):
        super().__init__()
        self.agent = agent
        self.workflow: EngineeringWorkflow | None = None
        self.busy = False
        self.reviewed_sha256: str | None = None
        self.reviewed_patch_sha256: str | None = None
        self.staged_patch_sha256: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Selected files → candidate → check → review → stage → Apply", id="engineering-status")
            with TabbedContent(id="engineering-tabs"):
                with TabPane("Setup", id="engineering-setup"), VerticalScroll(id="engineering-form"):
                        yield Static("Implementation brief")
                        yield Input(placeholder="Fix the failing boundary test", id="engineering-prompt")
                        yield Static("Existing source files (JSON array; [] for a new project)")
                        yield Input(placeholder='["bounds.py", "test_bounds.py"]', id="engineering-files")
                        yield Static("Writable paths (JSON array)")
                        yield Input(placeholder='["bounds.py"]', id="engineering-writable")
                        yield Static("Independent check argv (JSON array, no shell)")
                        yield Input(value='["python3", "-B", "-m", "unittest", "discover", "-v"]',
                                    id="engineering-command")
                with TabPane("Evidence", id="engineering-evidence"):
                    yield RichLog(id="engineering-receipt", wrap=True, markup=False)
            with Horizontal(classes="engineering-actions"):
                yield Button("Build", id="engineering-build")
                yield Button("Check", id="engineering-check")
                yield Button("Review", id="engineering-review")
            with Horizontal(classes="engineering-actions"):
                yield Button("Stage", id="engineering-stage")
                yield Button("Apply", id="engineering-apply", variant="warning")
                yield Button("Cancel", id="engineering-cancel")

    def report(self, message: str):
        self.query_one("#engineering-receipt", RichLog).write(Text(message))
        self.query_one("#engineering-tabs", TabbedContent).active = "engineering-evidence"
        if self.is_on_screen:
            self.query_one("#engineering-receipt", RichLog).focus()

    def focus_setup(self):
        if not self.busy:
            self.query_one("#engineering-tabs", TabbedContent).active = "engineering-setup"
            self.query_one("#engineering-prompt", Input).focus()

    def focus_evidence(self):
        self.query_one("#engineering-tabs", TabbedContent).active = "engineering-evidence"
        self.query_one("#engineering-receipt", RichLog).focus()

    def array(self, selector: str, *, allow_empty: bool = False) -> list[str]:
        value = json.loads(self.query_one(selector, Input).value)
        if (not isinstance(value, list) or not (0 if allow_empty else 1) <= len(value) <= 128
                or any(not isinstance(part, str) or not part for part in value)):
            raise ValueError("Provide a bounded JSON array of strings; commands cannot be empty")
        return value

    def current(self) -> EngineeringWorkflow:
        if self.workflow is None:
            raise ValueError("Build a selected-file candidate first")
        return self.workflow

    def reviewed(self) -> EngineeringWorkflow:
        workflow = self.current()
        if (self.reviewed_sha256 != workflow.candidate.describe()["candidate_sha256"]
                or self.reviewed_patch_sha256 != text_digest(workflow.candidate.patch())):
            raise ValueError("Review the current candidate patch before staging")
        return workflow

    def set_busy(self, value: bool):
        self.busy = value
        for button in self.query(Button):
            button.disabled = value and button.id != "engineering-cancel"
        for field in self.query(Input):
            field.disabled = value
        status = self.workflow.status if self.workflow else "idle"
        self.query_one("#engineering-status", Static).update(Text(f"Engineering: {status}"))

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        action = event.button.id.removeprefix("engineering-")
        if action == "cancel":
            self.workers.cancel_node(self)
            return
        if self.busy or self.app.chat_panel.streaming:
            self.report("Wait for the current request, or cancel it before another action.")
            return
        self.set_busy(True)
        self.perform(action)

    @work(exclusive=True)
    async def perform(self, action: str):
        try:
            if action == "build":
                await self.build()
            elif action == "check":
                await self.check()
            elif action == "review":
                workflow = self.current()
                patch = workflow.candidate.patch()
                if len(patch.encode()) > 200_000:
                    raise ValueError("Select a smaller candidate for terminal patch review")
                self.reviewed_sha256 = workflow.candidate.describe()["candidate_sha256"]
                self.reviewed_patch_sha256 = text_digest(patch)
                self.report(f"{patch or 'No changes'}\nREVIEW candidate {self.reviewed_sha256}")
            elif action == "stage":
                workflow = self.reviewed()
                if workflow.status != "verified":
                    raise ValueError("A passing independent check is required before staging")
                if self.agent.ws.diff():
                    raise ValueError("Isolated worktree changed; rebuild from a clean worktree before staging")
                if await self.app.request_tool_approval(
                    f"Stage reviewed candidate {self.reviewed_sha256} into the isolated worktree?\n"
                    "The original checkout stays unchanged."
                ):
                    workflow = self.reviewed()
                    if self.agent.ws.diff():
                        raise ValueError("Isolated worktree changed during staging confirmation")
                    result = workflow.stage(self.reviewed_sha256)
                    self.staged_patch_sha256 = text_digest(self.agent.ws.diff())
                    self.report(f"STAGED · original checkout unchanged\n"
                                f"Files: {', '.join(result['changed_files'])}\n"
                                f"Candidate: {result['candidate_sha256']}")
                else:
                    self.report("Stage denied. No staging action performed.")
            elif action == "apply":
                await self.apply()
        except asyncio.CancelledError:
            self.report("Cancelled. Inspect existing candidate/worktree changes before continuing.")
            raise
        except (ValueError, OSError, RuntimeError) as error:
            self.report(f"Action stopped: {type(error).__name__}: {error}")
        finally:
            if self.is_mounted:
                self.set_busy(False)

    async def build(self):
        if not self.agent.ws.isolated:
            raise ValueError("Engineering requires an isolated workspace")
        if self.agent.ws.diff():
            raise ValueError("Start from a clean isolated worktree; preserve or discard its current changes first")
        prompt = self.query_one("#engineering-prompt", Input).value.strip()
        if not 1 <= len(prompt) <= 4000:
            raise ValueError("Provide a brief between one and 4000 characters")
        files = self.array("#engineering-files", allow_empty=True)
        writable = self.array("#engineering-writable", allow_empty=True)
        workflow = EngineeringWorkflow(self.agent, files, writable, prompt)
        adopted = False
        try:
            if not await self.app.request_tool_approval(
                f"Share selected source files with configured model routing for up to six implementer steps?\n"
                f"Files: {json.dumps(files)}\nWritable: {json.dumps(writable)}\nBrief: {prompt}"
            ):
                self.report("Build denied. No model request started.")
                return
            if self.workflow:
                await self.workflow.close()
            self.workflow = workflow
            adopted = True
            self.reviewed_sha256 = self.reviewed_patch_sha256 = self.staged_patch_sha256 = None
            await workflow.run()
            description = workflow.candidate.describe()
            analysis = (workflow.result or {}).get("analysis") or workflow.error or "No model analysis returned."
            self.report(f"{analysis}\nCandidate: {description['candidate_sha256']}\n"
                        f"Files: {', '.join(description['changed_files']) or 'No changes'}\n"
                        f"MODEL PROPOSAL · {workflow.status} · independently check before trusting")
        finally:
            if not adopted:
                await workflow.close()

    async def check(self):
        workflow = self.current()
        if workflow.status not in {"ready", "verified", "check_failed"}:
            raise ValueError("Finish implementation before checking")
        command = self.array("#engineering-command")
        digest = workflow.candidate.describe()["candidate_sha256"]
        if await self.app.request_tool_approval(
            f"Execute this exact argv in Bubblewrap against candidate {digest}?\n{json.dumps(command)}\n"
            "Timeout: 30 seconds. No unsandboxed fallback."
        ):
            if digest != workflow.candidate.describe()["candidate_sha256"]:
                raise ValueError("Candidate changed during check confirmation")
            await workflow.check(command, 30)
            receipt = workflow.receipt
            if receipt:
                self.report(f"Candidate: {receipt['candidate_sha256']}\n"
                            f"Argv: {json.dumps(command)}\n"
                            f"stdout:\n{receipt.get('stdout', {}).get('text') or '(empty)'}\n"
                            f"stderr:\n{receipt.get('stderr', {}).get('text') or '(empty)'}\n"
                            f"Scope: {receipt.get('scope', 'Exact selected-file check')}\n"
                            f"CHECK {workflow.status} · exit {receipt['returncode']} · "
                            f"timeout {receipt.get('timed_out', False)}")
            else:
                self.report(f"CHECK {workflow.status} · {workflow.error or 'No executed-check receipt'}")
        else:
            self.report("Check denied. No verification command started.")

    async def apply(self):
        workflow = self.current()
        if workflow.status != "staged" or not self.staged_patch_sha256:
            raise ValueError("Stage a verified, reviewed candidate before original-checkout Apply")
        patch = self.agent.ws.diff()
        if text_digest(patch) != self.staged_patch_sha256:
            raise ValueError("Worktree changed after stage; original-checkout Apply refused")
        if len(patch.encode()) > 200_000:
            raise ValueError("Select a smaller patch for terminal Apply review")
        if await self.app.request_tool_approval(
            f"Apply this staged worktree patch to the ORIGINAL checkout {self.agent.ws.source}?\n"
            f"Patch SHA256: {self.staged_patch_sha256}\n{patch}"
        ):
            applied = self.agent.ws.apply(expected_patch_sha256=self.staged_patch_sha256)
            self.report(f"ORIGINAL APPLY: {'applied' if applied else 'no changes'}")
            if applied:
                workflow.status = "applied"
        else:
            self.report("Original-checkout Apply denied. Original remains unchanged.")

    async def close(self):
        if self.workflow:
            await self.workflow.close()
