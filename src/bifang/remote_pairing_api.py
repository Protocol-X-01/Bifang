from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .remote_pairing import PairingError, PairingStore


class StartPairing(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9 ._-]+$")


class ExchangePairing(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    device_code: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class ApprovePairing(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    user_code: str = Field(pattern=r"^[A-Za-z2-9]{4}-?[A-Za-z2-9]{4}$")
    authenticator_code: str = Field(pattern=r"^(?:[0-9]{6}|[0-9]{8})$")
    approved: bool


async def body(request, schema):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 1024:
            raise HTTPException(413, "Pairing request is too large")
    try:
        return schema.model_validate_json(content)
    except ValueError:
        raise HTTPException(422, "Invalid pairing request; credential details withheld") from None


def pairing_router(store: PairingStore):
    router = APIRouter()

    def operator(request):
        if request.state.auth_kind != "operator":
            raise HTTPException(403, "Pairing management requires an existing operator credential")

    async def invoke(function, *arguments, **options):
        try:
            return await asyncio.to_thread(function, *arguments, **options)
        except PairingError as failure:
            return JSONResponse({"error": failure.code, "interval": failure.interval},
                                status_code=429 if failure.code == "slow_down" else 400)

    @router.post("/v1/auth/device/start")
    async def start(request: Request):
        payload = await body(request, StartPairing)
        host = request.client.host if request.client else "unknown"
        bucket = hashlib.sha256(host.encode()).hexdigest()
        return await invoke(store.start, bucket, payload.label)

    @router.post("/v1/auth/device/token")
    async def exchange(request: Request):
        payload = await body(request, ExchangePairing)
        return await invoke(store.exchange, payload.device_code)

    @router.post("/v1/auth/device/approve")
    async def approve(request: Request):
        operator(request)
        payload = await body(request, ApprovePairing)
        return await invoke(store.approve, request.state.subject, payload.user_code, payload.authenticator_code,
                            approved=payload.approved)

    @router.post("/v1/auth/device/cancel")
    async def cancel(request: Request):
        payload = await body(request, ExchangePairing)
        return await invoke(store.cancel, payload.device_code)

    @router.get("/v1/auth/devices")
    async def sessions(request: Request):
        operator(request)
        return {"devices": await asyncio.to_thread(store.sessions, request.state.subject)}

    @router.delete("/v1/auth/devices/{identity}")
    async def revoke(identity: str, request: Request):
        operator(request)
        if not await asyncio.to_thread(store.revoke, request.state.subject, identity):
            raise HTTPException(404, "Device session not found")
        return {"revoked": True}

    @router.get("/v1/auth/session")
    async def session(request: Request):
        return {"subject": request.state.subject, "authentication": request.state.auth_kind}

    @router.delete("/v1/auth/session")
    async def logout(request: Request):
        if request.state.auth_kind != "device":
            return {"revoked": False}
        return await invoke(store.logout, request.state.subject, request.headers.get("Authorization", ""))

    return router
