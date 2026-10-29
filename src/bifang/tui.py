from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from rich.markdown import Markdown as RichMarkdown
from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.events import Resize
from textual.theme import Theme
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.screen import ModalScreen
from textual import work
from textual.widget import Widget
from textual.widgets import (
    Button, DataTable, DirectoryTree, Footer, Header, Input, Label, Tabs,
    Log, Markdown, RichLog, Static, TabbedContent, TabPane, Tree
)
from textual.widgets._header import HeaderIcon

from .agent import Agent
from .config import Config
from .workspace import Workspace
from .terminal_engineering import TerminalEngineering
from .terminal_workbench import TerminalWorkbench
from .reasoning import ReasoningPanel
from .metrics import MetricsPanel
from .tui_github import run_github_panel


class FileTree(Widget):
    """File tree with diff indicators."""

    def __init__(self, workspace: Workspace):
        super().__init__()
        self.workspace = workspace
        self.file_tree = Tree("Files", id="file-tree")
        self.file_tree.show_root = False
        self.file_tree.guide_depth = 3

    def compose(self) -> ComposeResult:
        yield self.file_tree

    def on_mount(self):
        self.refresh_tree()

    def refresh_tree(self):
        self.file_tree.clear()
        self.current_diff = self.workspace.diff() if self.workspace.isolated else ""
        root_node = self.file_tree.root
        self._add_directory(root_node, self.workspace.root)
        self.file_tree.root.expand()

    def _add_directory(self, parent, path: Path):
        try:
            for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.is_symlink():
                    continue
                if item.name.startswith(".") and item.name not in [".github", ".gitignore"]:
                    continue
                if item.name in {"__pycache__", "node_modules", ".venv", "dist", "build"}:
                    continue

                if item.is_dir():
                    node = parent.add(Text(item.name), data={"path": item, "type": "dir"})
                    node.expand()
                    self._add_directory(node, item)
                else:
                    rel_path = item.relative_to(self.workspace.root)
                    label = item.name
                    if self.workspace.isolated:
                        try:
                            diff = self.current_diff
                            if diff and str(rel_path) in diff:
                                label = f"● {item.name}"
                        except Exception:
                            pass
                    parent.add_leaf(Text(label), data={"path": item, "type": "file"})
        except PermissionError:
            pass

    async def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        if node.data and node.data.get("type") == "file":
            self.post_message(FileSelected(node.data["path"]))


class FileSelected(Message):
    def __init__(self, path: Path):
        self.path = path
        super().__init__()


class DiffViewer(Widget):
    """Side-by-side diff viewer."""

    def __init__(self):
        super().__init__()
        self.current_file: Optional[Path] = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical():
                yield Label("Original", classes="diff-header")
                yield RichLog(id="diff-original", wrap=True, markup=True)
            with Vertical():
                yield Label("Modified", classes="diff-header")
                yield RichLog(id="diff-modified", wrap=True, markup=True)

    def show_diff(self, file_path: Path, workspace: Workspace):
        self.current_file = file_path
        try:
            diff_output = workspace.diff(file_path)
            if not diff_output:
                self._show_no_changes()
                return

            self._parse_and_show_diff(diff_output, file_path)
        except Exception as e:
            self._show_error(str(e))

    def _show_no_changes(self):
        orig = self.query_one("#diff-original", RichLog)
        mod = self.query_one("#diff-modified", RichLog)
        orig.clear()
        mod.clear()
        orig.write("[dim]No changes[/dim]")
        mod.write("[dim]No changes[/dim]")

    def _show_error(self, error: str):
        orig = self.query_one("#diff-original", RichLog)
        mod = self.query_one("#diff-modified", RichLog)
        orig.clear()
        mod.clear()
        orig.write(Text(f"Error: {error}", style="red"))

    def _parse_and_show_diff(self, diff_output: str, file_path: Path):
        orig = self.query_one("#diff-original", RichLog)
        mod = self.query_one("#diff-modified", RichLog)
        orig.clear()
        mod.clear()

        lines = diff_output.split("\n")
        for line in lines:
            if line.startswith("diff --git"):
                continue
            if line.startswith("+") and not line.startswith("+++"):
                mod.write(Text(line, style="green"))
                orig.write(Text("    ", style="dim"))
            elif line.startswith("-") and not line.startswith("---"):
                orig.write(Text(line, style="red"))
                mod.write(Text("    ", style="dim"))
            elif line.startswith(" "):
                orig.write(Text(line, style="dim"))
                mod.write(Text(line, style="dim"))


class AgentPanel(Widget):
    """Agent status and control panel."""

    def __init__(self, agent: Agent):
        super().__init__()
        self.agent = agent

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Agent Status", classes="panel-title")
            yield RichLog(id="agent-status", markup=True)
            yield Static("Tools", classes="panel-title")
            yield DataTable(id="tool-table", show_header=True)
            yield Static("Memory", classes="panel-title")
            yield RichLog(id="memory-log", markup=True)

    def on_mount(self):
        self.update_status()
        self.update_tools()

    def update_status(self):
        log = self.query_one("#agent-status", RichLog)
        log.clear()
        model = self.agent.cfg.get_default_model()
        log.write(f"[bold]Model:[/bold] {model}")
        log.write(f"[bold]Mode:[/bold] {self.agent.cfg.mode}")
        log.write(f"[bold]Steps:[/bold] {self.agent._step_count}/{self.agent.cfg.max_steps}")
        log.write(f"[bold]Provider:[/bold] {self.agent.cfg.default_provider}")
        if self.agent.memory:
            log.write(f"[bold]Memory:[/bold] Enabled")
        if self.agent.mcp.clients:
            log.write(f"[bold]MCP:[/bold] {len(self.agent.mcp.clients)} servers")

    def update_tools(self):
        table = self.query_one("#tool-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Tool", "Type", "Description")

        builtin = [
            ("list_files", "builtin", "List repository files"),
            ("read_file", "builtin", "Read file contents"),
            ("write_file", "builtin", "Write file contents"),
            ("search", "builtin", "Search codebase"),
            ("run_command", "builtin", "Execute command"),
            ("git_diff", "builtin", "Show git diff"),
        ]
        for name, t, desc in builtin:
            table.add_row(name, t, desc)

        for name in self.agent.plugins.get_tool.__self__.context.tools.keys():
            table.add_row(name, "plugin", "Plugin tool")

        for tool in self.agent.mcp.get_all_tools():
            table.add_row(f"mcp_{tool.server_name}_{tool.name}", "mcp", tool.description[:50])

        if self.agent.memory:
            for name in ["memory_recall", "memory_store", "memory_context"]:
                table.add_row(name, "memory", "Memory management")


class ChatPanel(Widget):
    """Chat interface panel."""

    def __init__(self, agent: Agent):
        super().__init__()
        self.agent = agent
        self.streaming = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield RichLog(id="chat-log", markup=True, wrap=True, highlight=True)
            yield Input(placeholder="Ask Bifang...", id="chat-input")

    def on_mount(self):
        log = self.query_one("#chat-log", RichLog)
        restored = [message for message in self.agent.messages
                    if message.get("role") in ("user", "assistant") and message.get("content")]
        if restored:
            log.write(Text("Resumed history. Verify current files before continuing.", style="yellow"))
        else:
            log.write(Text("B I F A N G", style="bold #FF8A5D"))
            log.write(Text("Build. Run. Verify.", style="bold #F7F7F7"))
            log.write(Text("\nInspect the source. Shape a patch. Keep the evidence.", style="#A0A8B8"))
            log.write(Text("\nF2  Checks     F3  Activity     F4  Receipts", style="#A0A8B8"))
        for message in restored:
            if message["role"] == "user":
                log.write(Text(f"You: {message['content']}", style="cyan"))
            else:
                log.write(RichMarkdown(message["content"]))
        self.query_one("#chat-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.streaming:
            return
        if getattr(self.app, "engineering_panel", None) and self.app.engineering_panel.busy:
            self.query_one("#chat-log", RichLog).write(Text("Finish or cancel the engineering action first."))
            return
        prompt = event.value.strip()
        event.input.value = ""
        if not prompt:
            return
        if prompt.startswith("/") and hasattr(self.app, "terminal_command"):
            self.app.terminal_command(prompt)
            return

        log = self.query_one("#chat-log", RichLog)
        log.write(Text(f"You: {prompt}", style="cyan"))

        event.input.disabled = True
        self.streaming = True
        self.run_prompt(prompt)

    @work(exclusive=True)
    async def run_prompt(self, prompt: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        field = self.query_one("#chat-input", Input)
        try:
            parts = []
            stopped = None
            async for chunk in self.agent.ask_stream(prompt):
                if chunk.startswith("Stopped after"):
                    stopped = chunk
                elif chunk:
                    parts.append(chunk)
            if parts:
                log.write(RichMarkdown("".join(parts)))
            if stopped:
                log.write(Text(stopped, style="yellow"))
        except asyncio.CancelledError:
            log.write(Text("Request cancelled. Inspect existing changes before continuing.", style="yellow"))
            raise
        except Exception as e:
            log.write(Text(f"Error: {e}", style="bold red"))
        finally:
            if field.is_mounted:
                field.disabled = False
                field.focus()
            self.streaming = False


class ToolApprovalScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "deny", "Deny")]
    DEFAULT_CSS = """
    ToolApprovalScreen { align: center middle; background: $background 80%; }
    #approval-dialog { width: 90%; max-width: 90; height: 80%; border: round #FF8A5D;
        background: #1A2338; padding: 1 2; }
    #approval-details { height: 1fr; }
    #approval-buttons { height: 3; align-horizontal: right; }
    #approval-buttons Button { margin-left: 1; min-width: 12; }
    """

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-dialog"):
            yield Static(Text("Approve this action?", style="bold #FF8A5D"))
            with VerticalScroll(id="approval-details"):
                yield Static(Text(self.prompt))
            yield Static(Text("Review the exact action. Escape denies; no answer grants nothing."))
            with Horizontal(id="approval-buttons"):
                yield Button("Deny", id="approval-deny")
                yield Button("Approve", id="approval-allow", variant="warning")

    def on_mount(self):
        self.query_one("#approval-deny", Button).focus()

    def action_deny(self):
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        self.dismiss(event.button.id == "approval-allow")


class BifangApp(App):
    CSS = """
    Screen {
        background: #0F1728;
        color: #F7F7F7;
    }

    #main-container {
        layout: horizontal;
        height: 1fr;
    }

    #left-panel {
        width: 26;
        min-width: 0;
        border-right: solid #2D3A50;
    }

    #center-panel {
        width: 1fr;
        min-width: 0;
        border-right: solid #2D3A50;
    }

    #right-panel {
        width: 44;
        min-width: 0;
        border-right: solid #2D3A50;
    }

    #far-right-panel {
        width: 38;
        min-width: 0;
    }

    Screen.compact #left-panel, Screen.narrow #right-panel, Screen.narrow #far-right-panel,
    Screen.standard #far-right-panel {
        display: none;
    }

    Screen.narrow.inspector-open #right-panel {
        display: block;
        width: 1fr;
    }

    Screen.narrow.inspector-open #center-panel, Screen.narrow.inspector-open #left-panel {
        display: none;
    }

    Header, Footer {
        background: #1A2338;
        color: #F7F7F7;
    }

    TabbedContent, ContentSwitcher, TabPane, FileTree, ChatPanel, DiffViewer,
    ChatPanel > Vertical, DiffViewer > Vertical {
        height: 1fr;
    }

    Input:focus {
        border: tall #E63946;
    }

    .panel-title {
        background: $primary;
        color: $text;
        padding: 0 1;
        height: 1;
        text-style: bold;
    }

    .diff-header {
        background: $secondary;
        color: $text;
        padding: 0 1;
        height: 1;
        text-style: bold;
        text-align: center;
    }

    #file-tree {
        height: 1fr;
    }

    #chat-log {
        height: 1fr;
        border: solid $primary;
    }

    #agent-status, #memory-log {
        height: auto;
        min-height: 10;
        border: solid $primary;
    }

    #tool-table {
        height: auto;
        min-height: 15;
        border: solid $primary;
    }

    #diff-original, #diff-modified {
        height: 1fr;
        border: solid $primary;
    }

    #chat-input {
        dock: bottom;
        height: 3;
    }

    #verify-panel, #reasoning-panel, #metrics-panel, #github-panel {
        height: 1fr;
        border: solid $primary;
    }

    .panel-title {
        background: $primary;
        color: $text;
        padding: 0 1;
        height: 1;
        text-style: bold;
    }

    .diff-header {
        background: $secondary;
        color: $text;
        padding: 0 1;
        height: 1;
        text-style: bold;
        text-align: center;
    }

    #file-tree {
        height: 1fr;
    }

    #chat-log {
        height: 1fr;
        border: solid $primary;
    }

    #agent-status, #memory-log {
        height: auto;
        min-height: 10;
        border: solid $primary;
    }

    #tool-table {
        height: auto;
        min-height: 15;
        border: solid $primary;
    }

    #diff-original, #diff-modified {
        height: 1fr;
        border: solid $primary;
    }

    #chat-input {
        dock: bottom;
        height: 3;
    }

    RichLog {
        border: solid $primary;
    }

    DataTable {
        border: solid $primary;
    }

    .panel-title, .diff-header {
        background: #1A2338;
        color: #FF8A5D;
    }

    RichLog, DataTable, #chat-log, #diff-original, #diff-modified,
    #verify-panel, #reasoning-panel, #metrics-panel, #github-panel {
        border: round #2D3A50;
    }

    .verify-stamp-verified { border-left: solid $success; }
    .verify-stamp-failed { border-left: solid $error; }
    .verify-stamp-partial { border-left: solid $warning; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_log", "Clear Log"),
        Binding("ctrl+t", "toggle_theme", "Toggle Theme"),
        Binding("ctrl+r", "refresh_tree", "Refresh Files"),
        Binding("ctrl+d", "show_diff", "Show Diff"),
        Binding("ctrl+v", "toggle_verify", "Verify Panel"),
        Binding("ctrl+y", "toggle_reasoning", "Activity"),
        Binding("ctrl+m", "toggle_metrics", "Metrics"),
        Binding("ctrl+g", "toggle_github", "GitHub"),
        Binding("ctrl+k", "toggle_reasoning", "Activity Panel"),
        Binding("ctrl+x", "cancel_request", "Cancel Request", priority=True),
        Binding("f1", "help", "Help"),
        Binding("f2", "toggle_verify", "Verify Panel"),
        Binding("f3", "toggle_reasoning", "Activity"),
        Binding("f4", "toggle_metrics", "Metrics"),
        Binding("f5", "toggle_github", "GitHub"),
        Binding("f6", "engineering_setup", "Engineering Setup"),
        Binding("f7", "engineering_evidence", "Engineering Evidence"),
        Binding("f8", "workbench", "Workbench"),
    ]

    def __init__(self, agent: Agent):
        super().__init__()
        self.register_theme(Theme(name="bifang-ember", primary="#E63946", secondary="#FF8A5D",
                                  accent="#FF8A5D", foreground="#F7F7F7", background="#0F1728",
                                  surface="#1A2338", panel="#1A2338", dark=True))
        self.theme = "bifang-ember"
        self.agent = agent
        self.chat_panel = ChatPanel(agent)
        self.engineering_panel = TerminalEngineering(agent)
        self.previous_approve = agent.approve
        self.agent.approve = self.request_tool_approval
        self.current_file: Optional[Path] = None
        self.show_verify = False
        self.show_reasoning = False
        self.show_metrics = False
        self.show_github = False

    async def request_tool_approval(self, prompt: str) -> bool:
        screen = ToolApprovalScreen(prompt)
        try:
            return await self.push_screen_wait(screen) is True
        finally:
            if screen.is_mounted and self.screen is screen:
                screen.dismiss(False)

    async def on_unmount(self):
        self.agent.approve = self.previous_approve
        await self.engineering_panel.close()

    def action_cancel_request(self):
        self.workers.cancel_node(self.chat_panel)
        self.workers.cancel_node(self.engineering_panel)
        for screen in tuple(self.screen_stack):
            if isinstance(screen, TerminalWorkbench):
                self.workers.cancel_node(screen)

    def action_workbench(self):
        if any(isinstance(screen, ModalScreen) for screen in self.screen_stack):
            return
        if self.chat_panel.streaming or self.engineering_panel.busy:
            self.notify("Wait for the current request or cancel it before opening Workbench.")
            return
        self.push_screen(TerminalWorkbench(self.agent.ws.source, self.request_tool_approval,
                         lambda: self.chat_panel.streaming or self.engineering_panel.busy),
                         lambda _: self.chat_panel.query_one("#chat-input", Input).focus())

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, name="Bifang")

        with Horizontal(id="main-container"):
            # Left panel - File tree
            with Vertical(id="left-panel"):
                yield FileTree(self.agent.ws)

            # Center-left - Chat + Diff
            with Vertical(id="center-panel"):
                with TabbedContent():
                    with TabPane("Chat", id="chat-tab"):
                        yield self.chat_panel
                    with TabPane("Diff", id="diff-tab"):
                        yield DiffViewer()

            # Center-right - Verify + Reasoning + Metrics + GitHub
            with Vertical(id="right-panel"):
                with TabbedContent():
                    with TabPane("Verify", id="verify-tab"):
                        yield self.engineering_panel
                    with TabPane("Activity", id="reasoning-tab"):
                        yield ReasoningPanel(self.agent)
                    with TabPane("Metrics", id="metrics-tab"):
                        yield MetricsPanel(self.agent)
                    with TabPane("GitHub", id="github-tab"):
                        yield Static("GitHub integration - Press Ctrl+G to toggle")

            # Far right - Agent status + Memory + Metrics compact
            with Vertical(id="far-right-panel"):
                yield AgentPanel(self.agent)
                yield MetricsPanel(self.agent, compact=True)

        yield Footer()

    def on_mount(self):
        self.title = "Bifang"
        self._adapt_layout(self.size.width)
        self.sub_title = f"{self.agent.cfg.get_default_model() or 'Model not configured'} | {self.agent.ws.root.name}"
        self.load_github_token()

    def _adapt_layout(self, width: int):
        self.screen.set_class(width < 100, "compact")
        self.screen.set_class(width < 150, "narrow")
        self.screen.set_class(width < 210, "standard")

    def on_resize(self, event: Resize):
        self._adapt_layout(event.size.width)

    def load_github_token(self):
        """Check for GitHub token."""
        if os.getenv("GITHUB_TOKEN"):
            self.query_one("#chat-log", RichLog).write("[green]GitHub token detected - GitHub integration ready[/]")

    async def on_file_selected(self, event: FileSelected) -> None:
        """Handle file selection from tree."""
        self.current_file = event.path
        diff_viewer = self.query_one(DiffViewer)
        diff_viewer.show_diff(event.path, self.agent.ws)
        self.query_one("#center-panel TabbedContent").active = "diff-tab"

    def action_refresh_tree(self):
        """Refresh the file tree."""
        tree = self.query_one(FileTree)
        tree.refresh_tree()

    def action_show_diff(self):
        """Show diff for current file."""
        if self.current_file:
            diff_viewer = self.query_one(DiffViewer)
            diff_viewer.show_diff(self.current_file, self.agent.ws)
            self.query_one("#center-panel TabbedContent").active = "diff-tab"

    def action_clear_log(self):
        """Clear chat log."""
        chat = self.query_one(ChatPanel)
        chat.query_one("#chat-log", RichLog).clear()

    def action_toggle_theme(self):
        """Toggle dark/light theme."""
        self.dark = not self.dark

    def action_toggle_verify(self):
        """Toggle verify panel visibility."""
        self.toggle_inspector("verify-tab")

    def action_toggle_reasoning(self):
        """Toggle reasoning panel visibility."""
        self.toggle_inspector("reasoning-tab")

    def action_toggle_metrics(self):
        """Toggle metrics panel visibility."""
        self.toggle_inspector("metrics-tab")

    def action_toggle_github(self):
        """Toggle GitHub panel visibility."""
        self.toggle_inspector("github-tab")

    def toggle_inspector(self, tab: str):
        tabs = self.query_one("#right-panel TabbedContent")
        opened = not (self.screen.has_class("inspector-open") and tabs.active == tab)
        tabs.active = tab
        self.screen.set_class(opened, "inspector-open")
        self.show_verify = opened and tab == "verify-tab"
        self.show_reasoning = opened and tab == "reasoning-tab"
        self.show_metrics = opened and tab == "metrics-tab"
        self.show_github = opened and tab == "github-tab"
        if not opened:
            field = self.chat_panel.query_one("#chat-input", Input)
            (self.chat_panel.query_one("#chat-log", RichLog) if field.disabled else field).focus()
        elif tab == "verify-tab":
            if self.engineering_panel.query_one("#engineering-tabs", TabbedContent).active == "engineering-setup":
                self.engineering_panel.focus_setup()
            else:
                self.engineering_panel.focus_evidence()
        elif tab in {"reasoning-tab", "metrics-tab"}:
            self.query_one(f"#{tab} RichLog", RichLog).focus()
        else:
            tabs.query_one(Tabs).focus()

    def action_engineering_setup(self):
        if self.engineering_panel.busy:
            return
        if (not self.screen.has_class("inspector-open")
                or self.query_one("#right-panel TabbedContent").active != "verify-tab"):
            self.toggle_inspector("verify-tab")
        self.engineering_panel.focus_setup()

    def action_engineering_evidence(self):
        if (not self.screen.has_class("inspector-open")
                or self.query_one("#right-panel TabbedContent").active != "verify-tab"):
            self.toggle_inspector("verify-tab")
        self.engineering_panel.focus_evidence()

    def terminal_command(self, command: str):
        log = self.chat_panel.query_one("#chat-log", RichLog)
        actions = {"/help": self.action_help, "/checks": self.action_toggle_verify,
                   "/verify": self.action_toggle_verify, "/activity": self.action_toggle_reasoning,
                   "/metrics": self.action_toggle_metrics, "/workbench": self.action_workbench,
                   "/quit": self.exit}
        if command in actions:
            actions[command]()
        elif command == "/diff":
            log.write(Text(self.agent.ws.diff() or "No worktree changes."))
        elif command == "/status":
            log.write(Text(json.dumps({"workspace": str(self.agent.ws.root),
                "original": str(self.agent.ws.source), "isolated": self.agent.ws.isolated,
                "mode": self.agent.cfg.mode, "approvals": self.agent.cfg.approval_mode}, indent=2)))
        else:
            log.write(Text("Unknown terminal command. Use /help. No model request sent.", style="yellow"))

    def action_help(self):
        """Show help."""
        if self.screen.has_class("inspector-open"):
            self.toggle_inspector(self.query_one("#right-panel TabbedContent").active)
        self.query_one("#center-panel TabbedContent").active = "chat-tab"
        log = self.query_one("#chat-log", RichLog)
        log.write("""
[bold]Bifang Commands:[/bold]
  [cyan]/help[/cyan]     - Show this help
  [cyan]/status[/cyan]   - Show workspace status
  [cyan]/diff[/cyan]     - Show current diff
  [cyan]/checks[/cyan]   - Open selected-file engineering workflow
  [cyan]/activity[/cyan] - Show task and model activity
  [cyan]/metrics[/cyan]  - Show metrics panel
  [cyan]/workbench[/cyan] - Review plugins and language setup
  [cyan]/quit[/cyan]     - Exit

[bold]Keybindings:[/bold]
  [cyan]Ctrl+C[/cyan]    - Quit
  [cyan]Ctrl+L[/cyan]    - Clear log
  [cyan]Ctrl+T[/cyan]    - Toggle theme
  [cyan]Ctrl+R[/cyan]    - Refresh file tree
  [cyan]Ctrl+D[/cyan]    - Show diff for selected file
  [cyan]Ctrl+V[/cyan]    - Toggle Verify panel
  [cyan]Ctrl+Y[/cyan]    - Toggle Reasoning panel
  [cyan]Ctrl+M[/cyan]    - Toggle Metrics panel
  [cyan]Ctrl+G[/cyan]    - Toggle GitHub panel
  [cyan]Ctrl+X[/cyan]    - Cancel active request
  [cyan]F1[/cyan]        - This help
  [cyan]F2[/cyan]        - Verify panel
  [cyan]F3[/cyan]        - Reasoning panel
  [cyan]F4[/cyan]        - Metrics panel
  [cyan]F5[/cyan]        - GitHub panel
  [cyan]F6[/cyan]        - Engineering setup and first field
  [cyan]F7[/cyan]        - Engineering evidence and scrollable output
  [cyan]F8[/cyan]        - Plugin and language workbench
        """)


async def run_tui(agent: Agent):
    """Run the TUI application."""
    app = BifangApp(agent)
    await app.run_async()
