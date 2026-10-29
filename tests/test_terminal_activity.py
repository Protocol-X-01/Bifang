import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import RichLog

from bifang.metrics import MetricsPanel
from bifang.reasoning import ReasoningPanel
from bifang.tools.tasks import TaskPlan


def test_terminal_plan_and_metrics_render_actual_state_without_markup_interpretation():
    agent = SimpleNamespace(tasks=TaskPlan(), provider=SimpleNamespace(requests=[]),
        context=SimpleNamespace(get_stats=lambda: {"current_tokens": 42, "max_tokens": 1000, "message_count": 3}))

    class ActivityApp(App):
        def compose(self) -> ComposeResult:
            yield ReasoningPanel(agent)
            yield MetricsPanel(agent)

    async def scenario():
        async with ActivityApp().run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            activity = pilot.app.query_one(ReasoningPanel)
            metrics = pilot.app.query_one(MetricsPanel)
            activity_log = activity.query_one(RichLog)
            metrics_log = metrics.query_one(RichLog)
            assert "No task plan" in "\n".join(line.text for line in activity_log.lines)
            assert "not reported yet" in "\n".join(line.text for line in metrics_log.lines)
            agent.tasks.replace([{"content": "[bold]Literal task[/bold]", "status": "in_progress", "priority": "high"}])
            agent.provider.requests.append({"provider": "nebius", "role": "balanced", "task_type": "chat",
                "requested_model": "requested", "reported_model": None, "usage": {"total_tokens": 25}})
            activity.refresh_reasoning()
            metrics.refresh_metrics()
            await pilot.pause()
            text = "\n".join(line.text for line in activity_log.lines)
            assert "[bold]Literal task[/bold]" in text
            assert "Requested: requested" in text
            assert "Server reported: not supplied" in text
            assert "no hidden chain-of-thought" in text
            text = "\n".join(line.text for line in metrics_log.lines)
            assert "Context estimate: 42 / 1,000 tokens" in text
            assert "Reported total tokens: 25 (1/1 receipts)" in text
            assert "prompt tokens: not reported" in text
            agent.tasks.replace([])
            activity.refresh_reasoning()
            await pilot.pause()
            assert "Literal task" not in "\n".join(line.text for line in activity_log.lines)

    asyncio.run(scenario())
