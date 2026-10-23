from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, RichLog
from textual.widget import Widget
from textual.binding import Binding

from .config import Config
from .verify_panel import VerifyPanelImpl


class VerifyPanel(Widget):
    """Verify panel wrapper for TUI."""
    
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("ctrl+e", "export", "Export Report"),
    ]
    
    def __init__(self, cfg: Config, session_id: str | None = None):
        super().__init__()
        self.cfg = cfg
        self.session_id = session_id
        self.verify_panel = VerifyPanelImpl(session_id=session_id)

    def compose(self) -> ComposeResult:
        yield self.verify_panel