from __future__ import annotations

import asyncio
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .remote_coding import CodingJobs, CodingRequest
from .remote_jobs import JobConflict, JobQuota


class CodingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["writes", "check", "review", "stage", "apply"]
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved: bool


async def bounded_body(request, schema, limit):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, "Request exceeds the bounded coding contract")
    try:
        return schema.model_validate_json(body)
    except ValueError:
        raise HTTPException(422, "Invalid coding request; source and validation details withheld") from None


def coding_router(jobs: CodingJobs):
    router = APIRouter()

    async def ready(request):
        tasks = getattr(request.app.state, "coding_tasks", [])
        if len(tasks) != 2 or any(task.done() for task in tasks):
            raise HTTPException(503, "Coding workers are unavailable")
        probe = getattr(request.app.state, "coding_probe", None)
        if probe is not None:
            try:
                await probe()
            except (OSError, RuntimeError, ValueError, TimeoutError):
                raise HTTPException(503, "Independent executor is unavailable") from None

    async def invoke(function, *arguments):
        try:
            result = await asyncio.to_thread(function, *arguments)
        except JobConflict:
            raise HTTPException(409, "Coding state or project revision changed; refresh before deciding") from None
        except JobQuota:
            raise HTTPException(429, "Coding job quota reached") from None
        if result is None:
            raise HTTPException(404, "Coding resource not found")
        return result

    @router.get("/v1/coding/schema")
    async def schema():
        return {"submission": CodingRequest.model_json_schema(), "decision": CodingDecision.model_json_schema()}

    @router.post("/v1/coding/jobs")
    async def submit(request: Request):
        await ready(request)
        key = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            raise HTTPException(400, "Provide an Idempotency-Key of 16–128 safe characters")
        payload = await bounded_body(request, CodingRequest, 400000)
        if payload.sharing_confirmed is not True:
            raise HTTPException(400, "Confirm source sharing before requesting model work")
        job, created = await invoke(jobs.submit_coding, request.state.subject, key, payload)
        return JSONResponse(job, status_code=202 if created else 200)

    @router.get("/v1/coding/jobs")
    async def list_jobs(request: Request):
        return {"jobs": await invoke(jobs.list_coding, request.state.subject)}

    @router.get("/v1/coding/jobs/{identity}")
    async def get_job(identity: str, request: Request):
        return await invoke(jobs.get_coding, request.state.subject, identity)

    @router.get("/v1/coding/jobs/{identity}/patch")
    async def patch(identity: str, request: Request):
        return await invoke(jobs.patch_coding, request.state.subject, identity)

    @router.post("/v1/coding/jobs/{identity}/decisions")
    async def decide(identity: str, request: Request):
        decision = await bounded_body(request, CodingDecision, 2048)
        if decision.action == "check" and decision.approved:
            await ready(request)
        return await invoke(jobs.decide, request.state.subject, identity, decision.action,
                            decision.candidate_sha256, decision.approved)

    @router.post("/v1/coding/jobs/{identity}/cancel")
    async def cancel(identity: str, request: Request):
        return await invoke(jobs.cancel_coding, request.state.subject, identity)

    @router.delete("/v1/coding/jobs/{identity}")
    async def forget_job(identity: str, request: Request):
        return await invoke(jobs.forget_coding, request.state.subject, identity)

    @router.get("/v1/coding/projects/{identity}")
    async def project(identity: str, request: Request):
        return await invoke(jobs.project, request.state.subject, identity)

    @router.delete("/v1/coding/projects/{identity}")
    async def forget_project(identity: str, request: Request):
        return await invoke(jobs.forget_project, request.state.subject, identity)

    return router
