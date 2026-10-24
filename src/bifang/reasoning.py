from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, RichLog
from textual.widget import Widget
from textual.binding import Binding


class ReasoningPanel(Widget):
    """Public agent activity and task plan, never hidden model reasoning."""
    
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh"),
    ]
    
    def __init__(self, agent):
        super().__init__()
        self.agent = agent
    
    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Agent Activity", classes="panel-title"),
            RichLog(id="reasoning-content", markup=False, wrap=True),
            id="reasoning-panel"
        )
    
    def on_mount(self):
        self.refresh_reasoning()
        self.set_interval(1, self.refresh_reasoning)
    
    def refresh_reasoning(self):
        log = self.query_one("#reasoning-content", RichLog)
        log.clear()
        log.write(Text("Observable plan and routing only; no hidden chain-of-thought."))
        snapshot = self.agent.tasks.snapshot()
        log.write(Text(f"Session task plan · revision {snapshot['revision']}"))
        if not snapshot["todos"]:
            log.write(Text("No task plan recorded."))
        for index, item in enumerate(snapshot["todos"], 1):
            log.write(Text(f"{index}. [{item['status']}] ({item['priority']}) {item['content']}"))
        for receipt in self.agent.provider.requests[-10:]:
            log.write(Text(f"{receipt['provider']} · {receipt['role']} · {receipt['task_type']}"))
            log.write(Text(f"Requested: {receipt['requested_model']}"))
            log.write(Text(f"Server reported: {receipt.get('reported_model') or 'not supplied'}"))
    
    def action_refresh(self):
        self.refresh_reasoning()
