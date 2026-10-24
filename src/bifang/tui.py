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
from textual.widget import Widget
from textual.widgets import (
    Button, DataTable, DirectoryTree, Footer, Header, Input, Label, 
    Log, Markdown, RichLog, Static, TabbedContent, TabPane, Tree
)
from textual.widgets._header import HeaderIcon

from .agent import Agent
from .config import Config
from .workspace import Workspace
from .verify import VerifyPanel
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
        root_node = self.file_tree.root
        self._add_directory(root_node, self.workspace.root)
        self.file_tree.root.expand()

    def _add_directory(self, parent, path: Path):
        try:
            for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.name.startswith(".") and item.name not in [".github", ".gitignore"]:
                    continue
                if item.name in {"__pycache__", "node_modules", ".venv", "dist", "build"}:
                    continue

                if item.is_dir():
                    node = parent.add(item.name, data={"path": item, "type": "dir"})
                    node.expand()
                    self._add_directory(node, item)
                else:
                    rel_path = item.relative_to(self.workspace.root)
                    label = item.name
                    if self.workspace.isolated:
                        try:
                            diff = self.workspace.diff()
                            if diff and str(rel_path) in diff:
                                label = f"● {item.name}"
                        except Exception:
                            pass
                    parent.add_leaf(label, data={"path": item, "type": "file"})
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
            diff_output = workspace.diff()
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
        orig.write(f"[red]Error: {error}[/red]")

    def _parse_and_show_diff(self, diff_output: str, file_path: Path):
        orig = self.query_one("#diff-original", RichLog)
        mod = self.query_one("#diff-modified", RichLog)
        orig.clear()
        mod.clear()

        lines = diff_output.split("\n")
        in_target_file = False
        for line in lines:
            if line.startswith("diff --git"):
                in_target_file = str(file_path) in line
                continue
            if in_target_file:
                if line.startswith("+") and not line.startswith("+++"):
                    mod.write(f"[green]{line}[/green]")
                    orig.write("[dim]    [/dim]")
                elif line.startswith("-") and not line.startswith("---"):
                    orig.write(f"[red]{line}[/red]")
                    mod.write("[dim]    [/dim]")
                elif line.startswith(" "):
                    orig.write(f"[dim]{line}[/dim]")
                    mod.write(f"[dim]{line}[/dim]")


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
        prompt = event.value.strip()
        event.input.value = ""
        if not prompt:
            return

        log = self.query_one("#chat-log", RichLog)
        log.write(Text(f"You: {prompt}", style="cyan"))

        event.input.disabled = True
        self.streaming = True

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
        except Exception as e:
            log.write(Text(f"Error: {e}", style="bold red"))
        finally:
            event.input.disabled = False
            event.input.focus()
            self.streaming = False


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
        Binding("ctrl+s", "sudo_grant", "Sudo Grant"),
        Binding("ctrl+k", "toggle_reasoning", "Activity Panel"),
        Binding("f1", "help", "Help"),
        Binding("f2", "toggle_verify", "Verify Panel"),
        Binding("f3", "toggle_reasoning", "Activity"),
        Binding("f4", "toggle_metrics", "Metrics"),
        Binding("f5", "toggle_github", "GitHub"),
    ]

    def __init__(self, agent: Agent):
        super().__init__()
        self.register_theme(Theme(name="bifang-ember", primary="#E63946", secondary="#FF8A5D",
                                  accent="#FF8A5D", foreground="#F7F7F7", background="#0F1728",
                                  surface="#1A2338", panel="#1A2338", dark=True))
        self.theme = "bifang-ember"
        self.agent = agent
        self.current_file: Optional[Path] = None
        self.show_verify = False
        self.show_reasoning = False
        self.show_metrics = False
        self.show_github = False

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
                        yield ChatPanel(self.agent)
                    with TabPane("Diff", id="diff-tab"):
                        yield DiffViewer()

            # Center-right - Verify + Reasoning + Metrics + GitHub
            with Vertical(id="right-panel"):
                with TabbedContent():
                    with TabPane("Verify", id="verify-tab"):
                        yield VerifyPanel(self.agent.cfg, session_id=self.agent.cfg.get_default_model())
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
        self.show_verify = not self.show_verify
        tabs = self.query_one("#right-panel TabbedContent")
        if self.show_verify:
            tabs.active = "verify-tab"
        self.screen.set_class(self.show_verify, "inspector-open")

    def action_toggle_reasoning(self):
        """Toggle reasoning panel visibility."""
        self.show_reasoning = not self.show_reasoning
        tabs = self.query_one("#right-panel TabbedContent")
        if self.show_reasoning:
            tabs.active = "reasoning-tab"
        self.screen.set_class(self.show_reasoning, "inspector-open")

    def action_toggle_metrics(self):
        """Toggle metrics panel visibility."""
        self.show_metrics = not self.show_metrics
        tabs = self.query_one("#right-panel TabbedContent")
        if self.show_metrics:
            tabs.active = "metrics-tab"
        self.screen.set_class(self.show_metrics, "inspector-open")

    def action_toggle_github(self):
        """Toggle GitHub panel visibility."""
        self.show_github = not self.show_github
        tabs = self.query_one("#right-panel TabbedContent")
        if self.show_github:
            tabs.active = "github-tab"
        self.screen.set_class(self.show_github, "inspector-open")

    def action_sudo_grant(self):
        """Grant sudo privilege for a command."""
        # Would open a dialog in real implementation
        log = self.query_one("#chat-log", RichLog)
        log.write("[yellow]Sudo grant: Use /sudo grant <command> to grant sudo for a command[/]")

    def action_help(self):
        """Show help."""
        log = self.query_one("#chat-log", RichLog)
        log.write("""
[bold]Bifang Commands:[/bold]
  [cyan]/help[/cyan]     - Show this help
  [cyan]/status[/cyan]   - Show workspace status
  [cyan]/map[/cyan]      - Show file map
  [cyan]/diff[/cyan]     - Show current diff
  [cyan]/tests[/cyan]    - Run test-and-repair workflow
  [cyan]/memory[/cyan]   - Show memory contents
  [cyan]/verify[/cyan]   - Show verification panel
  [cyan]/reasoning[/cyan] - Show reasoning panel
  [cyan]/metrics[/cyan]  - Show metrics panel
  [cyan]/github[/cyan]   - GitHub integration
  [cyan]/sudo[/cyan]     - Sudo privilege management
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
  [cyan]Ctrl+S[/cyan]    - Sudo grant
  [cyan]F1[/cyan]        - This help
  [cyan]F2[/cyan]        - Verify panel
  [cyan]F3[/cyan]        - Reasoning panel
  [cyan]F4[/cyan]        - Metrics panel
  [cyan]F5[/cyan]        - GitHub panel
        """)


async def run_tui(agent: Agent):
    """Run the TUI application."""
    app = BifangApp(agent)
    await app.run_async()
