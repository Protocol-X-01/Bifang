from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, RichLog, Select, Static, TabbedContent, TabPane

from .package_setup import run_setup, setup_plan
from .workbench import dispatch


class TerminalWorkbench(ModalScreen[None]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "close", "Back to editor")]
    DEFAULT_CSS = """
    TerminalWorkbench { align: center middle; background: $background 80%; }
    #terminal-workbench { width: 96%; max-width: 110; height: 95%;
        border: round #FF8A5D; background: #0F1728; padding: 0 1; }
    #workbench-title, #workbench-status { height: auto; max-height: 2; }
    #workbench-tabs { height: 1fr; }
    #workbench-plugin-select { height: 3; }
    #workbench-setup-profile { width: 20; min-width: 0; height: 3; }
    #workbench-plugin-review, #workbench-languages, #workbench-system, #workbench-setup { height: 1fr; }
    .workbench-actions { height: 3; }
    .workbench-actions Button { width: 1fr; min-width: 8; padding: 0; }
    """

    def __init__(self, workspace: Path, approve: Callable[[str], Awaitable[bool]], busy: Callable[[], bool]):
        super().__init__()
        self.workspace = workspace
        self.approve = approve
        self.agent_busy = busy
        self.busy = False
        self.reviewed: dict | None = None
        self.view_serial = 0
        self.operation_view = "workbench-plugins-tab"
        self.setup_reviewed: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="terminal-workbench"):
            yield Static(Text("Your forge, extended · plugin and language workbench"), id="workbench-title")
            with TabbedContent(id="workbench-tabs"):
                with TabPane("Plugins", id="workbench-plugins-tab"):
                    yield Select([], prompt="Choose a local plugin", id="workbench-plugin-select")
                    yield RichLog(id="workbench-plugin-review", markup=False, wrap=True)
                with TabPane("Languages", id="workbench-languages-tab"):
                    yield RichLog(id="workbench-languages", markup=False, wrap=True)
                with TabPane("Forge pulse", id="workbench-system-tab"):
                    yield RichLog(id="workbench-system", markup=False, wrap=True)
                with TabPane("Packages", id="workbench-setup-tab"):
                    yield RichLog(id="workbench-setup", markup=False, wrap=True)
            yield Static(Text("Review local code before enabling. Language commands are previews."), id="workbench-status")
            with Horizontal(classes="workbench-actions"):
                yield Button("Review", id="workbench-review")
                yield Button("Enable", id="workbench-enable", variant="warning", disabled=True)
                yield Button("Disable", id="workbench-disable")
            with Horizontal(classes="workbench-actions"):
                yield Button("Refresh", id="workbench-refresh")
                yield Button("Sample", id="workbench-sample")
                yield Button("Close", id="workbench-close")
            with Horizontal(classes="workbench-actions"):
                yield Select([("JavaScript / npm", "javascript-npm"), ("Python / wheels", "python-uv"),
                              ("Python / builds", "python-uv-build"), ("Rust / fetch", "rust-cargo"),
                              ("Rust / check", "rust-cargo-build")], value="javascript-npm", allow_blank=False, id="workbench-setup-profile")
                yield Button("Plan offline", id="workbench-setup-offline")
                yield Button("Plan network", id="workbench-setup-network")
                yield Button("Install", id="workbench-setup-install", disabled=True)

    def request(self, action: str, **extra) -> dict:
        return dispatch({"version": 1, "action": action, "workspace": str(self.workspace), **extra})

    def on_mount(self):
        self.query_one("#workbench-setup", RichLog).write(Text(
            "Choose npm, Python or Rust. Review an offline or network plan, then Install. "
            "Build-code variants require separate permission; Ctrl+X cancels execution."))
        self.launch("refresh")

    def status(self, text: str):
        self.query_one("#workbench-status", Static).update(Text(text))

    def controls(self):
        for button in self.query(Button):
            button.disabled = (self.busy or (button.id == "workbench-enable" and self.reviewed is None)
                               or (button.id == "workbench-setup-install" and self.setup_reviewed is None))
        self.query_one("#workbench-plugin-select", Select).disabled = self.busy
        self.query_one("#workbench-setup-profile", Select).disabled = self.busy

    def selected(self) -> str:
        identity = self.query_one("#workbench-plugin-select", Select).value
        if not isinstance(identity, str):
            raise TypeError("Choose a plugin first")
        return identity

    def on_select_changed(self, event: Select.Changed):
        if event.select.id == "workbench-setup-profile":
            self.setup_reviewed = None
            self.controls()
            return
        if event.select.id == "workbench-plugin-select":
            self.reviewed = None
            self.query_one("#workbench-plugin-review", RichLog).clear()
            self.controls()

    def action_close(self):
        if not self.busy:
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        action = (event.button.id or "").removeprefix("workbench-")
        if action == "close":
            self.action_close()
        else:
            self.launch(action)

    def launch(self, action: str):
        if self.busy:
            return
        if self.agent_busy():
            self.status("Wait for the active request, or cancel it before workbench actions.")
            return
        self.busy = True
        self.view_serial += 1
        self.operation_view = self.query_one("#workbench-tabs", TabbedContent).active
        self.controls()
        self.perform(action)

    def refresh_catalog(self):
        self.reviewed = None
        self.setup_reviewed = None
        catalog = self.request("plugins.list")
        self.query_one("#workbench-plugin-select", Select).set_options([
            (Text(f"{item['name']} {item['version']} · {item['state']} · {item['id']}"), item["id"])
            for item in catalog["plugins"]
        ])
        log = self.query_one("#workbench-plugin-review", RichLog)
        log.clear()
        log.write(Text(catalog["execution"]))
        if not catalog["plugins"]:
            log.write(Text("Add a Python file and matching .plugin.json to the original project's .bifang/plugins, then refresh."))
        for error in catalog["errors"]:
            log.write(Text(f"{error['error']}: {error['path']}"))
        languages = self.request("toolchains.inspect")
        log = self.query_one("#workbench-languages", RichLog)
        log.clear()
        log.write(Text("Root-manifest bootstrap previews · no installation runs here."))
        if not languages["profiles"]:
            log.write(Text("No supported Python, JavaScript/TypeScript or Rust root manifest found."))
        for profile in languages["profiles"]:
            log.write(Text(f"\n{profile['label']} · {profile['manager']} · "
                           f"{'found on PATH' if profile['available'] else 'not found on PATH'}\n"
                           f"Manifests: {', '.join(profile['manifests'])}\n"
                           f"Argv: {json.dumps(profile['bootstrap_argv'])}\n"
                           f"May execute dependency build code: {profile['may_execute_dependency_code']}"))
            if profile.get("manager_selection_required"):
                log.write(Text("Choose the lockfile's manager; npm substitution is not selected."))

    @work(exclusive=True)
    async def perform(self, action: str):
        active = self.operation_view
        serial = self.view_serial
        focus = "workbench-plugin-select"
        try:
            if action == "refresh":
                self.refresh_catalog()
                self.status("Choose a plugin, then Review. Language setup is read-only.")
            elif action == "review":
                reviewed = self.request("plugins.review", id=self.selected())
                if len(reviewed["source"].splitlines()) > 5000:
                    self.reviewed = None
                    self.status("Source exceeds 5000 lines. Use desktop or external review before CLI trust.")
                    return
                self.reviewed = reviewed
                self.query_one("#workbench-tabs", TabbedContent).active = "workbench-plugins-tab"
                active = "workbench-plugins-tab"
                focus = "workbench-plugin-review"
                log = self.query_one("#workbench-plugin-review", RichLog)
                log.clear()
                log.write(Text(f"{reviewed['name']} {reviewed['version']}\n{reviewed['description']}\n"
                               f"{reviewed['source_path']}\nManifest: {reviewed['manifest_path']}\n"
                               f"Capabilities: {', '.join(reviewed['capabilities'])}\n"
                               f"SHA-256: {reviewed['sha256']}\n\n{reviewed['source']}"))
                log.focus()
                self.status("Review the source; Enable asks separate full-host trust confirmation.")
            elif action == "enable":
                if not self.reviewed or self.selected() != self.reviewed["id"]:
                    raise ValueError("Review this selection first")
                reviewed = self.reviewed
                allowed = await self.approve(
                    f"Enable this exact local Python plugin?\nName: {reviewed['name']}\n"
                    f"Source: {reviewed['source_path']}\nSHA-256: {reviewed['sha256']}\n"
                    f"{reviewed['execution']}\nDependencies are not covered by the two-file fingerprint.")
                if allowed is True and not self.agent_busy():
                    self.request("plugins.trust", id=reviewed["id"], sha256=reviewed["sha256"], confirmed=True)
                    self.refresh_catalog()
                    self.status("Exact reviewed plugin enabled. It loads on the agent's next refresh.")
                else:
                    self.status("Enable denied or another request became active; trust unchanged.")
            elif action == "disable":
                self.request("plugins.disable", id=self.selected())
                self.refresh_catalog()
                self.status("Plugin disabled. Prior host-code side effects are not undone.")
            elif action == "sample":
                result = await asyncio.to_thread(self.request, "metrics.sample")
                log = self.query_one("#workbench-system", RichLog)
                log.clear()
                log.write(Text(json.dumps(result, indent=2)))
                self.query_one("#workbench-tabs", TabbedContent).active = "workbench-system-tab"
                active = "workbench-system-tab"
                log.focus()
                self.status("One local host sample · separate from model usage. Nothing sent to providers.")
            elif action in ("setup-offline", "setup-network", "setup-install"):
                active = "workbench-setup-tab"
                focus = "workbench-setup"
                self.query_one("#workbench-tabs", TabbedContent).active = active
                log = self.query_one("#workbench-setup", RichLog)
                if action != "setup-install":
                    self.setup_reviewed = None
                    choice = self.query_one("#workbench-setup-profile", Select).value
                    if not isinstance(choice, str):
                        raise ValueError("Choose a setup profile")
                    builds = choice.endswith("-build")
                    profile = choice.removesuffix("-build") if builds else choice
                    plan = await asyncio.to_thread(setup_plan, self.workspace, network=action == "setup-network", profile=profile, allow_builds=builds)
                    self.setup_reviewed = plan
                    log.clear()
                    log.write(Text(json.dumps(plan, indent=2)))
                    self.status("Review this locked plan. Install asks confirmation; Ctrl+X cancels execution.")
                else:
                    if self.setup_reviewed is None:
                        raise ValueError("Review setup first")
                    plan = self.setup_reviewed
                    self.setup_reviewed = None
                    if plan.get("allow_builds") and await self.approve("Separately authorize build code for this exact plan?\n" + plan["execution"] + "\nSHA-256: " + plan["sha256"]) is not True:
                        self.status("Build-code permission denied; no setup process started.")
                        return
                    allowed = await self.approve("Install this exact setup plan?\n" + json.dumps(plan, indent=2))
                    if allowed is not True or self.agent_busy():
                        self.status("Setup denied or agent became active; no installation started.")
                        return
                    receipt = await run_setup(self.workspace, plan["sha256"], confirmed=True,
                                              network=plan["network"] == "host-network",
                                              registry=plan["registry"], profile=plan["profile"], allow_builds=plan.get("allow_builds", False),
                                              on_output=lambda stream, value: log.write(Text(value)))
                    log.write(Text(json.dumps(receipt, indent=2)))
                    self.status(f"Setup {receipt['status']} · receipt {'saved' if receipt['receipt_saved'] else 'not saved; copy the result'}.")
        except asyncio.CancelledError:
            if self.is_mounted:
                self.status("Cancelled. Inspect current plugin state before continuing.")
            raise
        except (OSError, ValueError, TypeError, RuntimeError):
            self.reviewed = None
            self.setup_reviewed = None
            self.status("Could not verify this action. Check project manifests, then refresh and review again.")
        finally:
            if self.is_mounted:
                if active == "workbench-languages-tab":
                    focus = "workbench-languages"
                elif active == "workbench-system-tab":
                    focus = "workbench-system"
                elif active == "workbench-setup-tab":
                    focus = "workbench-setup"
                self.call_after_refresh(self.restore_view, active, focus, serial)
            else:
                self.busy = False

    def restore_view(self, active: str, focus: str, serial: int):
        if self.is_mounted and serial == self.view_serial:
            self.query_one("#workbench-tabs", TabbedContent).active = active
            self.call_after_refresh(self.focus_view, focus, serial)

    def focus_view(self, focus: str, serial: int):
        if self.is_mounted and serial == self.view_serial and self.app.screen is self:
            if focus != "workbench-plugin-select":
                self.query_one(f"#{focus}").focus()
            self.busy = False
            self.controls()
            self.query_one(f"#{focus}").focus()
