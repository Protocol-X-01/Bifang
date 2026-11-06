import asyncio
import json

import httpx
import pytest

from bifang.agent import Agent
from bifang.config import Config
from bifang.providers.types import ProviderConfig
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
        ("Partial review", "model_context_window_exceeded", "stopped", "output_limit"),
        ("", "model_context_window_exceeded", "stopped", "output_limit"),
        ("Partial review", "content_filter", "stopped", "provider_filter"),
        ("I cannot complete this review.", "refusal", "stopped", "provider_filter"),
        ("", "refusal", "stopped", "provider_filter"),
        ("Inspected the requested evidence.", "end_turn", "completed", None),
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
                else:
                    assert worker["analysis"] == (content or "")
                    assert worker["error"]
        finally:
            await parent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("stop_reason", "reason", "error"),
    [
        ("refusal", "provider_filter", "The provider stopped the review before a final answer."),
        ("model_context_window_exceeded", "output_limit",
         "The model reached its response limit before finishing the review."),
    ],
)
def test_anthropic_stop_reason_reaches_review_completion(
    tmp_path, monkeypatch, stop_reason, reason, error,
):
    content = "Partial review from Anthropic"
    requests = []
    client_type = httpx.AsyncClient

    def respond(request):
        assert request.method == "POST"
        assert request.url.host == "fixture.invalid"
        requests.append(request)
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": content}], "stop_reason": stop_reason,
        })

    monkeypatch.setattr(
        "bifang.providers.anthropic.httpx.AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )

    async def scenario():
        config = Config(
            default_provider="anthropic", enable_memory=False, enable_conversation_history=False,
            providers={"anthropic": ProviderConfig(
                name="anthropic", base_url="https://fixture.invalid/v1", default_model="fixture",
            )},
        )
        parent = Agent(config, Workspace(tmp_path, tmp_path))
        try:
            workflow = ReviewWorkflow(parent, "Review the supplied evidence")
            await workflow.run()
            result = workflow.snapshot()
            assert result["status"] == "failed"
            assert len(requests) == 2
            for worker in result["workers"]:
                assert worker["status"] == "stopped"
                assert worker["stop_reason"] == reason
                assert worker["error"] == error
                assert worker["analysis"] == content
                assert worker["routing"][0]["provider"] == "anthropic"
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
