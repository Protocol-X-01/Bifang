from __future__ import annotations

import hmac
import json
import os
from contextlib import asynccontextmanager

import httpx
from anyio import CancelScope
from fastapi import FastAPI, HTTPException, Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from .model_ids import TOKEN_FACTORY_ROLES

UPSTREAM = "https://api.tokenfactory.nebius.com/v1"
MAX_BODY_BYTES = 2_000_000
REQUEST_FIELDS = {"model", "messages", "tools", "tool_choice", "temperature",
                  "max_tokens", "stream", "stream_options"}


def reject_nonfinite(value):
    raise ValueError("Nonfinite numbers are not JSON")


def create_app(provider_key: str, judge_token: str, *, client: httpx.AsyncClient | None = None):
    if len(provider_key) < 16 or len(judge_token) < 32 or provider_key == judge_token:
        raise ValueError("Configure separate provider credentials and a strong judge-only token")
    upstream = client or httpx.AsyncClient(timeout=120, trust_env=False, follow_redirects=False)
    owns_client = client is None
    allowed_models = frozenset(TOKEN_FACTORY_ROLES.values())

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if owns_client:
                await upstream.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if request.url.path != "/health":
            supplied = request.headers.get("authorization", "").encode()
            expected = ("Bearer " + judge_token).encode()
            if not hmac.compare_digest(supplied, expected):
                return JSONResponse({"detail": "Judge authorization required"}, status_code=401)
        return await call_next(request)

    @app.get("/health")
    async def health():
        return {"status": "ok", "scope": "inference-only"}

    async def send(method, path, payload=None, *, stream=False):
        request = upstream.build_request(method, UPSTREAM + path, json=payload,
                                         headers={"Authorization": "Bearer " + provider_key})
        try:
            response = await upstream.send(request, stream=stream, follow_redirects=False)
        except httpx.HTTPError as error:
            raise HTTPException(503, "Inference service temporarily unavailable") from error
        if response.status_code != 200:
            await response.aclose()
            raise HTTPException(429 if response.status_code == 429 else 502,
                                "Inference provider did not accept the request")
        return response

    @app.get("/v1/models")
    async def models():
        response = await send("GET", "/models")
        try:
            data = response.json()
            rows = data["data"]
            if not isinstance(rows, list):
                raise TypeError("Invalid catalog")
            return {"object": "list", "data": [row for row in rows
                    if isinstance(row, dict) and row.get("id") in allowed_models]}
        except (ValueError, KeyError, TypeError) as error:
            raise HTTPException(502, "Inference catalog unavailable") from error
        finally:
            await response.aclose()

    @app.post("/v1/chat/completions")
    async def complete(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                raise HTTPException(413, "Inference request exceeds relay body limit")
            body.extend(chunk)
        try:
            payload = json.loads(body, parse_constant=reject_nonfinite)
        except (ValueError, UnicodeError) as error:
            raise HTTPException(400, "Expected a JSON inference request") from error
        if not isinstance(payload, dict) or set(payload) - REQUEST_FIELDS:
            raise HTTPException(400, "Unsupported inference request fields")
        if not isinstance(payload.get("model"), str) or payload["model"] not in allowed_models:
            raise HTTPException(400, "Model is not enabled for judge access")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages or any(not isinstance(row, dict) for row in messages):
            raise HTTPException(400, "Expected nonempty message objects")
        maximum = payload.get("max_tokens", 4096)
        if type(maximum) is not int or not 1 <= maximum <= 32768:
            raise HTTPException(400, "max_tokens must be between 1 and 32768")
        payload["max_tokens"] = maximum
        streaming = payload.get("stream", False)
        if type(streaming) is not bool:
            raise HTTPException(400, "stream must be a boolean")
        response = await send("POST", "/chat/completions", payload, stream=streaming)
        if streaming:
            async def chunks():
                try:
                    async for chunk in response.aiter_bytes():
                        yield chunk
                finally:
                    with CancelScope(shield=True):
                        await response.aclose()

            return StreamingResponse(chunks(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
        try:
            return Response(response.content, media_type="application/json",
                            headers={"Cache-Control": "no-store"})
        finally:
            await response.aclose()

    return app


def main():
    import uvicorn

    app = create_app(os.environ.get("NEBIUS_API_KEY", ""), os.environ.get("BIFANG_JUDGE_TOKEN", ""))
    uvicorn.run(app, host=os.environ.get("BIFANG_JUDGE_HOST", "127.0.0.1"),
                port=int(os.environ.get("BIFANG_JUDGE_PORT", os.environ.get("PORT", "8010"))),
                access_log=False)


if __name__ == "__main__":
    main()
