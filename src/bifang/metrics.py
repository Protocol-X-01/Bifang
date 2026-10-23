from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, RichLog
from textual.widget import Widget


class MetricsPanel(Widget):
    """Metrics panel showing system metrics."""
    
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh"),
    ]
    
    def __init__(self, compact: bool = False):
        super().__init__()
        self.compact = compact
    
    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("System Metrics", classes="panel-title"),
            RichLog(id="metrics-content", markup=True, wrap=True),
            id="metrics-panel"
        )
    
    def on_mount(self):
        self.refresh_metrics()
    
    def refresh_metrics(self):
        """Refresh metrics display."""
        pass
    
    def action_refresh(self):
        self.refresh_metrics()