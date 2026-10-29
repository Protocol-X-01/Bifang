import asyncio
import json

import pytest

from bifang.remote_coding import CodingJobs, CodingRequest
from bifang.remote_proposal import ProposalWorker, generate_proposal


def request():
    return CodingRequest(provider="nebius", model="synthetic-model", question="Fix the boundary",
                         files=[{"path": "bounds.py", "content": "synthetic baseline"}],
                         writable=["bounds.py"], check_command=["python", "-m", "unittest"], sharing_confirmed=True)


class Manager:
    def __init__(self, response, models=None):
        self.response = response
        self.models = ["synthetic-model"] if models is None else models
        self.called = False
        self.closed = False

    async def verified_model_ids(self, provider):
        assert provider == "nebius"
        return self.models

    async def complete(self, messages, **options):
        self.called = True
        assert options["tools"] is None
        assert options["provider"] == "nebius" and options["model"] == "synthetic-model"
        assert options["max_tokens"] == 4096
        payload = json.loads(messages[-1]["content"])
        assert payload["writable"] == ["bounds.py"]
        assert payload["independent_check_command"] == ["python", "-m", "unittest"]
        return self.response

    async def close(self):
        self.closed = True


def test_pinned_tool_free_proposal_does_not_accept_execution_claims():
    manager = Manager({"content": json.dumps({"writes": {"bounds.py": "candidate"}})})
    result = asyncio.run(generate_proposal(None, request().model_dump(), manager_factory=lambda config: manager))
    assert result == {"bounds.py": "candidate"} and manager.closed and manager.called
    assert result.generation["requested_model"] == "synthetic-model"
    assert result.generation["reported_model"] is None and result.generation["usage"] == {}


@pytest.mark.parametrize("response", [
    {"content": "tests passed"}, {"content": '{"writes":{},"passed":true}'},
    {"content": '{"writes":[]}'}, {"content": "[]"}, {"content": ""},
    {"content": "x" * 128001}, {"content": '{"writes":{}}', "tool_calls": [{"name": "run"}]},
])
def test_invalid_proposal_is_rejected_and_provider_closed(response):
    manager = Manager(response)
    with pytest.raises(ValueError):
        asyncio.run(generate_proposal(None, request().model_dump(), manager_factory=lambda config: manager))
    assert manager.closed


def test_missing_catalog_model_does_not_request_inference():
    manager = Manager({}, models=[])
    with pytest.raises(ValueError):
        asyncio.run(generate_proposal(None, request().model_dump(), manager_factory=lambda config: manager))
    assert manager.closed and not manager.called


def test_worker_persists_only_pending_human_proposal_and_never_applies(tmp_path):
    async def scenario():
        store = CodingJobs(tmp_path / "state")
        job, created = store.submit_coding("owner", "synthetic_worker_key", request())
        assert created
        original = store.project("owner", job["project_id"])

        async def runner(payload):
            return {"bounds.py": "candidate"}

        worker = ProposalWorker(store, runner)
        assert await worker.once() is True
        assert store.get_coding("owner", job["id"])["status"] == "awaiting_write_approval"
        assert store.project("owner", job["project_id"]) == original
        assert await worker.once() is False

    asyncio.run(scenario())


def test_real_provider_metadata_path_persists_allowlisted_usage_and_model_ids(tmp_path):
    async def scenario():
        manager = Manager({"content": '{"writes":{"bounds.py":"candidate"}}', "reported_model": "reported-model",
                           "usage": {"total_tokens": 42, "prompt_tokens": True, "raw_prompt": "not telemetry"}})
        store = CodingJobs(tmp_path / "state")
        job, created = store.submit_coding("owner", "synthetic_generation_receipt", request())
        assert created

        async def runner(payload):
            return await generate_proposal(None, payload, manager_factory=lambda config: manager)

        await ProposalWorker(store, runner).once()
        resumed = CodingJobs(tmp_path / "state").get_coding("owner", job["id"])
        assert resumed["generation"] == {"provider": "nebius", "requested_model": "synthetic-model",
                                         "reported_model": "reported-model", "usage": {"total_tokens": 42},
                                         "verification": "unverified_model_proposal"}
        assert resumed["status"] == "awaiting_write_approval" and manager.closed

    asyncio.run(scenario())


def test_cancellation_fences_late_model_and_worker_shutdown_does_not_replay(tmp_path):
    async def scenario():
        store = CodingJobs(tmp_path / "state")
        job, created = store.submit_coding("owner", "synthetic_cancel_key", request())
        assert created
        started, release = asyncio.Event(), asyncio.Event()

        async def runner(payload):
            started.set()
            await release.wait()
            return {"bounds.py": "late"}

        worker = ProposalWorker(store, runner)
        task = asyncio.create_task(worker.once())
        await started.wait()
        store.cancel_coding("owner", job["id"])
        release.set()
        await task
        assert store.get_coding("owner", job["id"])["status"] == "cancelled"
        assert await worker.once() is False
        job, created = store.submit_coding("owner", "synthetic_shutdown_key", request())
        assert created
        started.clear()
        release.clear()
        task = asyncio.create_task(worker.once())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert store.get_coding("owner", job["id"])["status"] == "interrupted"
        assert await worker.once() is False

    asyncio.run(scenario())


def test_bad_write_and_timeout_fail_closed(tmp_path):
    async def scenario():
        store = CodingJobs(tmp_path / "state")
        for name in ("invalid", "timeout"):
            job, created = store.submit_coding("owner", "synthetic_failure_" + name, request())
            assert created

            async def runner(payload, mode=name):
                if mode == "timeout":
                    await asyncio.sleep(1)
                return {"unselected.py": "escape"}

            await ProposalWorker(store, runner, timeout=0.01).once()
            result = store.get_coding("owner", job["id"])
            assert result["status"] == "failed" and result["error"] == "proposal_unavailable"
            assert result["proposal"] is None and result["receipt"] is None

    asyncio.run(scenario())


def test_owner_cancellation_stops_pending_provider_coroutine(tmp_path):
    async def scenario():
        store = CodingJobs(tmp_path / "state")
        job, created = store.submit_coding("owner", "synthetic_transport_cancel", request())
        assert created
        started, stopped = asyncio.Event(), asyncio.Event()

        async def runner(payload):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        task = asyncio.create_task(ProposalWorker(store, runner, poll_seconds=0.005).once())
        await started.wait()
        store.cancel_coding("owner", job["id"])
        await asyncio.wait_for(task, timeout=1)
        assert stopped.is_set()
        assert store.get_coding("owner", job["id"])["status"] == "cancelled"

    asyncio.run(scenario())
