import asyncio
import hashlib
import json
import subprocess

import httpx
import pytest

from bifang.remote_coding import CodingJobs, snapshot_digest
from bifang.remote_jobs import ReviewJobs
from bifang.remote_server import RemoteTokens, create_remote_app

OWNER = {"Authorization": "Bearer " + "a" * 48}
OTHER = {"Authorization": "Bearer " + "b" * 48}


def payload():
    return {"provider": "nebius", "model": "synthetic-model", "question": "Fix the boundary",
            "files": [{"path": "bounds.py", "content": "def valid(index, items):\n    return index <= len(items)\n"}],
            "writable": ["bounds.py"], "check_command": ["python", "-B", "-m", "unittest"],
            "sharing_confirmed": True}


def application(directory, *, proposal=None, check=None, probe=None):
    jobs = ReviewJobs(directory)
    coding = CodingJobs(directory)
    tokens = RemoteTokens(json.dumps([{"subject": subject, "token_sha256": hashlib.sha256(token.encode()).hexdigest()}
                                     for subject, token in (("alice", "a" * 48), ("bob", "b" * 48))]))

    async def propose(request):
        return {"bounds.py": "def valid(index, items):\n    return 0 <= index < len(items)\n"}

    async def checked(files, command, timeout):
        return {"candidate_sha256": snapshot_digest(files), "command": command, "exit_code": 0,
                "timed_out": False, "output_sha256": hashlib.sha256(b"synthetic check fixture").hexdigest()}

    app = create_remote_app(jobs, tokens, coding=coding, proposal_runner=proposal or propose, check_runner=check or checked,
                            coding_probe=probe)
    return app, coding


async def wait_for(client, identity, status):
    for attempt in range(100):
        response = await client.get("/v1/coding/jobs/" + identity, headers=OWNER)
        assert response.status_code == 200
        job = response.json()
        if job["status"] == status:
            return job
        await asyncio.sleep(0.02)
    pytest.fail("Coding job did not reach " + status + "; observed " + job["status"])


async def submit(client, key="synthetic_http_coding_key"):
    response = await client.post("/v1/coding/jobs", headers={**OWNER, "Idempotency-Key": key}, json=payload())
    assert response.status_code == 202
    return response.json()


async def decide(client, job, action, approved=True):
    return await client.post("/v1/coding/jobs/" + job["id"] + "/decisions", headers=OWNER,
                             json={"action": action, "approved": approved, "candidate_sha256": job["candidate_sha256"]})


def test_authenticated_http_workflow_has_separate_check_review_stage_apply_and_patch(tmp_path):
    async def scenario():
        app, coding = application(tmp_path / "state")
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.invalid") as client:
            assert (await client.get("/health")).json()["coding_enabled"] is True
            initial = await submit(client)
            project_url = "/v1/coding/projects/" + initial["project_id"]
            original = (await client.get(project_url, headers=OWNER)).json()
            job = await wait_for(client, initial["id"], "awaiting_write_approval")
            assert (await decide(client, job, "apply")).status_code == 409
            assert (await decide(client, job, "check")).status_code == 409
            patch = await client.get("/v1/coding/jobs/" + job["id"] + "/patch", headers=OWNER)
            assert patch.json()["candidate_sha256"] == job["candidate_sha256"]
            checkout = tmp_path / "checkout"
            checkout.mkdir()
            (checkout / "bounds.py").write_text(original["files"]["bounds.py"])
            await asyncio.to_thread(subprocess.run, ["git", "init", "-q", str(checkout)], check=True, capture_output=True)
            await asyncio.to_thread(subprocess.run, ["git", "-C", str(checkout), "apply", "--check", "-"], input=patch.json()["patch"],
                                    text=True, check=True, capture_output=True)
            assert (await decide(client, job, "writes")).json()["status"] == "awaiting_check_approval"
            assert (await decide(client, job, "writes")).json()["status"] == "awaiting_check_approval"
            assert (await decide(client, job, "check")).status_code == 200
            job = await wait_for(client, job["id"], "verified")
            assert job["receipt"]["command"] == payload()["check_command"]
            assert (await decide(client, job, "stage")).status_code == 409
            assert (await decide(client, job, "review")).json()["status"] == "reviewed"
            assert (await decide(client, job, "stage")).json()["status"] == "staged"
            assert (await client.get(project_url, headers=OWNER)).json() == original
            assert (await decide(client, job, "apply")).json()["status"] == "applied"
            changed = (await client.get(project_url, headers=OWNER)).json()
            assert changed["revision"] == job["candidate_sha256"]
            assert coding.project("alice", initial["project_id"]) == changed
            assert "0 <= index < len(items)" in changed["files"]["bounds.py"]
            assert "0 <= index < len(items)" not in (checkout / "bounds.py").read_text()
            duplicate = await client.post("/v1/coding/jobs", headers={**OWNER, "Idempotency-Key": "synthetic_http_coding_key"}, json=payload())
            assert duplicate.status_code == 200 and duplicate.json()["id"] == job["id"]
            assert duplicate.headers["Cache-Control"] == "no-store"

    asyncio.run(scenario())


def test_every_resource_route_is_owner_scoped_and_missing_auth_rejected(tmp_path):
    async def scenario():
        app, coding = application(tmp_path / "state")
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.invalid") as client:
            assert (await client.get("/v1/coding/schema")).status_code == 401
            initial = await submit(client)
            job = await wait_for(client, initial["id"], "awaiting_write_approval")
            prefix = "/v1/coding/jobs/" + job["id"]
            decision = {"action": "writes", "candidate_sha256": job["candidate_sha256"], "approved": True}
            for method, path, body in (("GET", prefix, None), ("GET", prefix + "/patch", None),
                                       ("POST", prefix + "/decisions", decision), ("POST", prefix + "/cancel", None),
                                       ("DELETE", prefix, None), ("GET", "/v1/coding/projects/" + job["project_id"], None),
                                       ("DELETE", "/v1/coding/projects/" + job["project_id"], None)):
                response = await client.request(method, path, headers=OTHER, json=body)
                assert response.status_code == 404
            assert (await client.get("/v1/coding/jobs", headers=OTHER)).json() == {"jobs": []}
            assert (await client.get("/v1/coding/schema", headers=OTHER)).status_code == 200
            assert (await client.get("/api/workspace", headers=OWNER)).status_code == 404
            assert coding.get_coding("alice", job["id"])["status"] == "awaiting_write_approval"

    asyncio.run(scenario())


def test_strict_bodies_withhold_source_and_cannot_override_subject_receipt_or_command(tmp_path):
    async def scenario():
        app, coding = application(tmp_path / "state")
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.invalid") as client:
            headers = {**OWNER, "Idempotency-Key": "synthetic_validation_key"}
            for changes in ({"subject": "bob"}, {"passed": True}, {"sharing_confirmed": "true"},
                            {"files": [{"path": ".env", "content": "private-marker-do-not-echo"}]}):
                response = await client.post("/v1/coding/jobs", headers=headers, json={**payload(), **changes})
                assert response.status_code == 422 and "private-marker" not in response.text
            assert (await client.post("/v1/coding/jobs", headers=headers, content=b"x" * 400001)).status_code == 413
            assert (await client.post("/v1/coding/jobs", headers=OWNER, json=payload())).status_code == 400
            initial = await submit(client)
            job = await wait_for(client, initial["id"], "awaiting_write_approval")
            decision = {"action": "writes", "candidate_sha256": job["candidate_sha256"], "approved": True}
            for extra in ({"approved": "yes"}, {"check_command": ["true"]}, {"passed": True}):
                response = await client.post("/v1/coding/jobs/" + job["id"] + "/decisions", headers=OWNER, json={**decision, **extra})
                assert response.status_code == 422
            assert (await client.post("/v1/coding/jobs/" + job["id"] + "/decisions", headers=OWNER, content=b"x" * 2049)).status_code == 413
            assert (await decide(client, job, "writes", False)).json()["status"] == "rejected"
            assert (await decide(client, job, "writes", True)).status_code == 409
            assert len(coding.list_coding("alice")) == 1

    asyncio.run(scenario())


def test_delete_removes_project_source_and_job_payload_but_preserves_idempotency(tmp_path):
    async def scenario():
        app, coding = application(tmp_path / "state")
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.invalid") as client:
            initial = await submit(client)
            prefix = "/v1/coding/jobs/" + initial["id"]
            project = "/v1/coding/projects/" + initial["project_id"]
            assert (await client.delete(prefix, headers=OWNER)).status_code == 409
            assert (await client.delete(project, headers=OWNER)).status_code == 409
            assert (await client.post(prefix + "/cancel", headers=OWNER)).json()["status"] == "cancelled"
            assert (await client.delete(project, headers=OWNER)).json()["logical_source_removal"] is True
            assert (await client.get(project, headers=OWNER)).status_code == 404
            row = (await client.get(prefix, headers=OWNER)).json()
            assert row["status"] == "deleted" and row["proposal"] is None and row["receipt"] is None
            duplicate = await client.post("/v1/coding/jobs", headers={**OWNER, "Idempotency-Key": "synthetic_http_coding_key"}, json=payload())
            assert duplicate.status_code == 200 and duplicate.json()["status"] == "deleted"
            assert (await client.get(prefix + "/patch", headers=OWNER)).status_code == 409
            assert (await client.delete(prefix, headers=OWNER)).json()["status"] == "deleted"
            assert coding.project("alice", initial["project_id"]) is None

    asyncio.run(scenario())


@pytest.mark.parametrize("mode,expected", [("exit", "check_failed"), ("timeout", "check_failed"),
                                          ("command", "failed"), ("hash", "failed"), ("claim", "failed"),
                                          ("mutation", "failed"), ("output", "failed"), ("missing", "failed")])
def test_unavailable_failed_or_mismatched_check_cannot_be_promoted(tmp_path, mode, expected):
    async def scenario():
        async def check(files, command, timeout):
            receipt = {"candidate_sha256": snapshot_digest(files), "command": command,
                       "exit_code": 0, "timed_out": False, "output_sha256": "0" * 64}
            if mode == "exit":
                receipt["exit_code"] = 1
            elif mode == "timeout":
                receipt["timed_out"] = True
            elif mode == "command":
                receipt["command"] = ["true"]
            elif mode == "hash":
                receipt["candidate_sha256"] = "f" * 64
            elif mode == "claim":
                receipt["passed"] = True
            elif mode == "mutation":
                files["bounds.py"] = "changed after approval"
            elif mode == "output":
                receipt["output_sha256"] = "invalid"
            elif mode == "missing":
                raise ValueError("private-provider-marker-do-not-echo")
            return receipt

        app, coding = application(tmp_path / "state", check=check)
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.invalid") as client:
            initial = await submit(client)
            job = await wait_for(client, initial["id"], "awaiting_write_approval")
            original = coding.project("alice", initial["project_id"])
            assert (await decide(client, job, "writes")).status_code == 200
            assert (await decide(client, job, "check")).status_code == 200
            job = await wait_for(client, job["id"], expected)
            assert "private-provider-marker" not in json.dumps(job)
            assert (await decide(client, job, "review")).status_code == 409
            assert (await decide(client, job, "stage")).status_code == 409
            assert (await decide(client, job, "apply")).status_code == 409
            assert coding.project("alice", initial["project_id"]) == original

    asyncio.run(scenario())


def test_cancelling_running_check_cancels_executor_and_rejects_late_receipts(tmp_path):
    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()

        async def check(files, command, timeout):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        app, coding = application(tmp_path / "state", check=check)
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.invalid") as client:
            initial = await submit(client)
            job = await wait_for(client, initial["id"], "awaiting_write_approval")
            assert (await decide(client, job, "writes")).status_code == 200
            assert (await decide(client, job, "check")).status_code == 200
            await asyncio.wait_for(started.wait(), timeout=2)
            response = await client.post("/v1/coding/jobs/" + job["id"] + "/cancel", headers=OWNER)
            assert response.json()["status"] == "cancelled"
            await asyncio.wait_for(stopped.wait(), timeout=2)
            assert coding.get_coding("alice", job["id"])["receipt"] is None
            assert (await decide(client, job, "apply")).status_code == 409

    asyncio.run(scenario())


def test_missing_check_worker_fails_health_submissions_and_check_approval_closed(tmp_path):
    async def scenario():
        app, coding = application(tmp_path / "state")
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.invalid") as client:
            initial = await submit(client)
            job = await wait_for(client, initial["id"], "awaiting_write_approval")
            assert (await decide(client, job, "writes")).status_code == 200
            app.state.coding_tasks[1].cancel()
            await asyncio.gather(app.state.coding_tasks[1], return_exceptions=True)
            assert (await client.get("/health")).status_code == 503
            assert (await decide(client, job, "check")).status_code == 503
            response = await client.post("/v1/coding/jobs", headers={**OWNER, "Idempotency-Key": "another_worker_failure_key"}, json=payload())
            assert response.status_code == 503
            assert coding.get_coding("alice", job["id"])["status"] == "awaiting_check_approval"

    asyncio.run(scenario())


def test_executor_readiness_failure_prevents_new_model_work_and_check_approval(tmp_path):
    async def scenario():
        unavailable = [False]
        calls = []

        async def probe():
            if unavailable[0]:
                raise RuntimeError("private-backend-detail-not-for-clients")

        async def proposal(request):
            calls.append(request["model"])
            return {"bounds.py": "candidate"}

        app, coding = application(tmp_path / "state", proposal=proposal, probe=probe)
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.invalid") as client:
            initial = await submit(client)
            job = await wait_for(client, initial["id"], "awaiting_write_approval")
            assert (await decide(client, job, "writes")).status_code == 200
            unavailable[0] = True
            assert (await client.get("/health")).status_code == 503
            response = await decide(client, job, "check")
            assert response.status_code == 503 and "private-backend" not in response.text
            response = await client.post("/v1/coding/jobs", headers={**OWNER, "Idempotency-Key": "another_backend_failure_key"}, json=payload())
            assert response.status_code == 503 and len(calls) == 1
            assert coding.get_coding("alice", job["id"])["status"] == "awaiting_check_approval"

    asyncio.run(scenario())


def test_coding_is_disabled_without_both_worker_capabilities(tmp_path):
    jobs = ReviewJobs(tmp_path / "state")
    coding = CodingJobs(tmp_path / "state")
    tokens = RemoteTokens(json.dumps([{"subject": "alice", "token_sha256": hashlib.sha256(("a" * 48).encode()).hexdigest()}]))
    with pytest.raises(ValueError):
        create_remote_app(jobs, tokens, coding=coding)
    with pytest.raises(ValueError):
        create_remote_app(jobs, tokens, check_runner=lambda: None)

    async def scenario():
        app = create_remote_app(jobs, tokens)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.invalid") as client:
            assert (await client.get("/v1/coding/schema", headers=OWNER)).status_code == 404

    asyncio.run(scenario())
