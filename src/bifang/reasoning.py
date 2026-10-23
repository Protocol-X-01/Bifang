from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, RichLog
from textual.widget import Widget
from textual.binding import Binding


class ReasoningPanel(Widget):
    """Reasoning panel showing agent's chain-of-thought."""
    
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("ctrl+o", "toggle_raw", "Toggle Raw"),
    ]
    
    def __init__(self, session_id: str | None = None):
        super().__init__()
        self.session_id = session_id
        self.show_raw = False
    
    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Reasoning Panel", classes="panel-title"),
            RichLog(id="reasoning-content", markup=True, wrap=True),
            id="reasoning-panel"
        )
    
    def on_mount(self):
        self.refresh_reasoning()
    
    def refresh_reasoning(self):
        """Refresh reasoning display."""
        pass
    
    def action_refresh(self):
        self.refresh_reasoning()
    
    def action_toggle_raw(self):
        """Toggle raw CoT display."""
        self.show_raw = not self.show_raw