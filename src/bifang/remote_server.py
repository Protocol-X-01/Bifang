from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .remote_jobs import JobConflict, JobQuota, RemoteReviewRequest, ReviewJobs
from .remote_worker import ReviewWorker, review_source


class RemoteTokens:
    def __init__(self, encoded: str):
        records = json.loads(encoded)
        if not isinstance(records, list) or not 1 <= len(records) <= 32:
            raise ValueError("Configure client token hashes before starting")
        self.records = []
        seen = set()
        for entry in records:
            if (not isinstance(entry, dict) or set(entry) != {"subject", "token_sha256"}
                    or not isinstance(entry["subject"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", entry["subject"])
                    or not isinstance(entry["token_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["token_sha256"])
                    or entry["token_sha256"] in seen):
                raise ValueError("Invalid client token registry")
            seen.add(entry["token_sha256"])
            self.records.append((entry["subject"], entry["token_sha256"]))

    def subject(self, header: str):
        scheme, separator, token = header.partition(" ")
        if not separator or scheme.lower() != "bearer" or not re.fullmatch(r"[!-~]{32,256}", token):
            return None
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        matches = [subject for subject, expected in self.records if hmac.compare_digest(fingerprint, expected)]
        return matches[0] if len(matches) == 1 else None


def create_remote_app(jobs: ReviewJobs, tokens: RemoteTokens, *, runner=None,
                      coding=None, proposal_runner=None, check_runner=None, coding_probe=None):
    configuration = (coding is not None, proposal_runner is not None, check_runner is not None)
    if any(configuration) and not all(configuration):
        raise ValueError("Coding requires a store, proposal worker and independent check runner")
    if coding is not None and coding.path != jobs.path:
        raise ValueError("Coding and review jobs must share the private backup store")
    if coding_probe is not None and coding is None:
        raise ValueError("A coding probe requires an explicitly configured coding service")

    @asynccontextmanager
    async def lifespan(application):
        if coding_probe is not None:
            await coding_probe()
        task = asyncio.create_task(ReviewWorker(jobs, runner).run()) if runner else None
        application.state.worker_task = task
        coding_tasks = []
        if coding is not None:
            from .remote_check_worker import CodingCheckWorker
            from .remote_proposal import ProposalWorker

            coding_tasks = [asyncio.create_task(ProposalWorker(coding, proposal_runner).run()),
                            asyncio.create_task(CodingCheckWorker(coding, check_runner).run())]
        application.state.coding_tasks = coding_tasks
        try:
            yield
        finally:
            workers = ([task] if task is not None else []) + coding_tasks
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    application = FastAPI(title="Bifang Remote Reviews", version="0.1.0", lifespan=lifespan,
                          docs_url=None, redoc_url=None, openapi_url=None)
    application.state.coding_probe = coding_probe

    @application.middleware("http")
    async def authenticate(request: Request, call_next):
        if request.url.path != "/health":
            subject = tokens.subject(request.headers.get("Authorization", ""))
            if subject is None:
                return JSONResponse({"detail": "Authentication required"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"})
            request.state.subject = subject
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.get("/health")
    async def health():
        task = getattr(application.state, "worker_task", None)
        if task is not None and task.done():
            return JSONResponse({"status": "unavailable", "service": "bifang-remote-reviews"}, status_code=503)
        coding_tasks = getattr(application.state, "coding_tasks", [])
        if coding is not None and (len(coding_tasks) != 2 or any(worker.done() for worker in coding_tasks)):
            return JSONResponse({"status": "unavailable", "service": "bifang-remote-reviews"}, status_code=503)
        if coding_probe is not None:
            try:
                await coding_probe()
            except (OSError, RuntimeError, ValueError, TimeoutError):
                return JSONResponse({"status": "unavailable", "service": "bifang-remote-reviews"}, status_code=503)
        value = {"status": "ok", "service": "bifang-remote-reviews", "worker_enabled": task is not None}
        if coding is not None:
            value["coding_enabled"] = True
        return value

    @application.get("/v1/schema")
    async def schema():
        return RemoteReviewRequest.model_json_schema()

    @application.post("/v1/reviews")
    async def submit(request: Request):
        key = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            raise HTTPException(400, "Provide an Idempotency-Key of 16–128 safe characters")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 400000:
                raise HTTPException(413, "Review request is too large")
        try:
            payload = RemoteReviewRequest.model_validate_json(body)
        except (ValueError, ValidationError):
            raise HTTPException(422, "Invalid review request; source and validation details withheld") from None
        if payload.sharing_confirmed is not True:
            raise HTTPException(400, "Confirm sharing the selected source with this service and provider")
        try:
            job, created = await asyncio.to_thread(jobs.submit, request.state.subject, key, payload)
        except JobConflict:
            raise HTTPException(409, "Idempotency key already belongs to another request") from None
        except JobQuota:
            raise HTTPException(429, "Review job quota reached") from None
        return JSONResponse(job, status_code=202 if created else 200)

    @application.get("/v1/reviews")
    async def list_jobs(request: Request):
        return {"jobs": await asyncio.to_thread(jobs.list, request.state.subject)}

    @application.get("/v1/reviews/{identity}")
    async def get_job(identity: str, request: Request):
        job = await asyncio.to_thread(jobs.get, request.state.subject, identity)
        if job is None:
            raise HTTPException(404, "Review not found")
        return job

    @application.post("/v1/reviews/{identity}/cancel")
    async def cancel_job(identity: str, request: Request):
        job = await asyncio.to_thread(jobs.cancel, request.state.subject, identity)
        if job is None:
            raise HTTPException(404, "Review not found")
        return job

    @application.delete("/v1/reviews/{identity}")
    async def forget_job(identity: str, request: Request):
        try:
            job = await asyncio.to_thread(jobs.forget, request.state.subject, identity)
        except JobConflict:
            raise HTTPException(409, "Cancel active work before removing its result") from None
        if job is None:
            raise HTTPException(404, "Review not found")
        return job

    if coding is not None:
        from .remote_coding_api import coding_router

        application.include_router(coding_router(coding))
    return application


def main():
    import uvicorn

    from .config import Config

    config = Config.load()
    tokens = RemoteTokens(os.environ.get("BIFANG_REMOTE_CLIENTS", "[]"))
    directory = Path(os.environ.get("BIFANG_REMOTE_STATE", "~/.local/state/bifang/remote")).expanduser()
    jobs = ReviewJobs(directory)

    async def runner(payload):
        return await review_source(config, payload)

    options = {}
    socket_path = os.environ.get("BIFANG_REMOTE_CODING_SOCKET")
    if socket_path:
        from .remote_coding import CodingJobs
        from .remote_executor import BrokerClient
        from .remote_proposal import generate_proposal

        if socket_path != "/run/bifang-executor/check.sock":
            raise ValueError("Use the operator-controlled executor socket")
        broker = BrokerClient(socket_path)

        async def probe():
            await asyncio.wait_for(broker.verify_peer(), timeout=2)

        async def proposal(payload):
            await probe()
            return await generate_proposal(config, payload)

        options = {"coding": CodingJobs(directory), "proposal_runner": proposal,
                   "check_runner": broker, "coding_probe": probe}
    uvicorn.run(create_remote_app(jobs, tokens, runner=runner, **options),
                host=os.environ.get("BIFANG_REMOTE_HOST", "127.0.0.1"), port=8125)


if __name__ == "__main__":
    main()
