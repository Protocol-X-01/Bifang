from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, RichLog
from textual.widget import Widget


class MetricsPanel(Widget):
    """Displays actual request receipts and labeled context estimates."""
    
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh"),
    ]
    
    def __init__(self, agent, compact: bool = False):
        super().__init__()
        self.agent = agent
        self.compact = compact
    
    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Request Metrics", classes="panel-title"),
            RichLog(id="metrics-content", markup=False, wrap=True),
            id="metrics-panel"
        )
    
    def on_mount(self):
        self.refresh_metrics()
        self.set_interval(1, self.refresh_metrics)
    
    def refresh_metrics(self):
        log = self.query_one("#metrics-content", RichLog)
        log.clear()
        stats = self.agent.context.get_stats()
        log.write(Text(f"Context estimate: {stats['current_tokens']:,} / {stats['max_tokens']:,} tokens"))
        log.write(Text(f"Context messages: {stats['message_count']}"))
        receipts = self.agent.provider.requests
        log.write(Text(f"Latest request model receipts: {len(receipts)}"))
        if not receipts:
            log.write(Text("Token usage: not reported yet"))
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            values = [receipt.get("usage", {}).get(key) for receipt in receipts]
            reported = [value for value in values if type(value) is int and value >= 0]
            label = key.replace("_", " ")
            if reported:
                log.write(Text(f"Reported {label}: {sum(reported):,} ({len(reported)}/{len(receipts)} receipts)"))
            else:
                log.write(Text(f"{label}: not reported"))
        if not self.compact:
            log.write(Text("Context counts are estimates. No GPU memory, pricing or throughput measurement is implied."))
    
    def action_refresh(self):
        self.refresh_metrics()
