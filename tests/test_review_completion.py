import asyncio
import json

import httpx
import pytest

from bifang.agent import Agent
from bifang.config import Config
from bifang.review_workflow import ReviewWorkflow
from bifang.workspace import Workspace


@pytest.mark.parametrize(
    ("content", "finish_reason", "expected", "reason"),
    [
        (None, "stop", "stopped", "empty_analysis"),
        (" \n\t", "stop", "stopped", "empty_analysis"),
        ("Partial review", "length", "stopped", "output_limit"),
        ("", "length", "stopped", "output_limit"),
        ("Partial review", "max_tokens", "stopped", "output_limit"),
        ("Partial review", "content_filter", "stopped", "provider_filter"),
        ("Inspected the requested evidence.", "stop", "completed", None),
        ("Inspected the requested evidence.", None, "completed", None),
    ],
)
def test_review_requires_a_finished_nonempty_answer(tmp_path, monkeypatch, content, finish_reason, expected, reason):
    class Provider:
        def __init__(self):
            self.requests = []

        async def complete(self, messages, **kwargs):
            return {"role": "assistant", "content": content, "finish_reason": finish_reason}

        async def close(self):
            pass

    monkeypatch.setattr("bifang.agent.create_tiered_provider", lambda config: Provider())

    async def scenario():
        parent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path))
        try:
            workflow = ReviewWorkflow(parent, "Review the supplied evidence")
            await workflow.run()
            result = workflow.snapshot()
            assert result["status"] == ("completed" if expected == "completed" else "failed")
            for worker in result["workers"]:
                assert worker["status"] == expected
                assert worker.get("stop_reason") == reason
                assert worker["verification"] == "unverified_model_analysis"
                if expected == "completed":
                    assert worker["analysis"] == content
                    assert "error" not in worker
        finally:
            await parent.close()

    asyncio.run(scenario())


def test_review_reports_only_provider_http_status_not_response_or_credentials(tmp_path, monkeypatch):
    marker = "synthetic-private-response-marker"

    class Provider:
        def __init__(self):
            self.requests = []

        async def complete(self, messages, **kwargs):
            request = httpx.Request("POST", "https://fixture.invalid/chat", headers={"Authorization": marker})
            response = httpx.Response(404, text=marker, request=request)
            raise httpx.HTTPStatusError(marker, request=request, response=response)

        async def close(self):
            pass

    monkeypatch.setattr("bifang.agent.create_tiered_provider", lambda config: Provider())

    async def scenario():
        parent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path))
        try:
            workflow = ReviewWorkflow(parent, "Review the supplied evidence")
            await workflow.run()
            result = workflow.snapshot()
            assert result["status"] == "failed"
            assert marker not in json.dumps(result)
            for worker in result["workers"]:
                assert worker["status"] == "failed"
                assert worker["provider_http_status"] == 404
                assert worker["error"] == "The provider rejected the review request (HTTP 404)."
        finally:
            await parent.close()

    asyncio.run(scenario())
