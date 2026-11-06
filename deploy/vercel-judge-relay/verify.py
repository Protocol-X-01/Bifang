import asyncio
import importlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime

import httpx

from bifang.judge_relay import create_app
from bifang.model_ids import TOKEN_FACTORY_ROLES

PROVIDER_KEY = "synthetic-provider-credential-only"
JUDGE_TOKEN = "synthetic-judge-credential-more-than-32-characters"
JUDGE_TOKEN_EXPIRES_AT = "2030-01-01T00:00:00Z"


async def main():
    empty = {name: value for name, value in os.environ.items() if name in {"PATH", "LANG", "LC_ALL"}}
    missing = await asyncio.to_thread(subprocess.run, [sys.executable, "-c", "import app"],
                                     env=empty, capture_output=True)
    assert missing.returncode != 0 and b"Configure separate provider credentials" in missing.stderr
    no_expiry = await asyncio.to_thread(
        subprocess.run, [sys.executable, "-c", "import app"],
        env={**empty, "NEBIUS_API_KEY": PROVIDER_KEY, "BIFANG_JUDGE_TOKEN": JUDGE_TOKEN},
        capture_output=True,
    )
    assert no_expiry.returncode != 0 and b"BIFANG_JUDGE_TOKEN_EXPIRES_AT" in no_expiry.stderr
    os.environ["NEBIUS_API_KEY"] = PROVIDER_KEY
    os.environ["BIFANG_JUDGE_TOKEN"] = JUDGE_TOKEN
    os.environ["BIFANG_JUDGE_TOKEN_EXPIRES_AT"] = JUDGE_TOKEN_EXPIRES_AT
    entrypoint = importlib.import_module("app")
    assert not any(name in sys.modules for name in ("bifang.routing", "bifang.agent", "tensorrt", "torch"))
    async with (entrypoint.app.router.lifespan_context(entrypoint.app),
                httpx.AsyncClient(transport=httpx.ASGITransport(app=entrypoint.app), base_url="http://test") as client):
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/v1/models")).status_code == 401

    model = TOKEN_FACTORY_ROLES["reasoning"]
    calls = []
    wire = b'data: {"choices":[]}\n\ndata: [DONE]\n\n'

    def respond(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer " + PROVIDER_KEY
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": model}, {"id": "disabled"}]})
        if json.loads(request.content).get("stream"):
            return httpx.Response(200, content=wire)
        return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": "Synthetic answer"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as upstream:
        app = create_app(PROVIDER_KEY, JUDGE_TOKEN, token_expires_at=JUDGE_TOKEN_EXPIRES_AT,
                         client=upstream)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers={
                "Authorization": "Bearer " + JUDGE_TOKEN}) as client:
            catalog = await client.get("/v1/models")
            assert catalog.json()["data"] == [{"id": model}]
            payload = {"model": model, "messages": [{"role": "user", "content": "Synthetic fixture"}]}
            response = await client.post("/v1/chat/completions", json=payload)
            assert response.json()["model"] == model
            stream = await client.post("/v1/chat/completions", json={**payload, "stream": True})
            assert stream.content == wire
            assert (await client.get("/sessions")).status_code == 404
    assert len(calls) == 3

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as upstream:
        public_app = create_app(PROVIDER_KEY, "", token_expires_at=JUDGE_TOKEN_EXPIRES_AT,
                                client=upstream, public_access=True)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url="http://test") as client:
            page = await client.get("/")
            assert page.status_code == 200 and PROVIDER_KEY not in page.text
            assert (await client.get("/v1/models")).status_code == 200
            assert (await client.post("/v1/chat/completions", json=payload)).status_code == 200
            assert (await client.get("/sessions")).status_code == 404
    assert len(calls) == 5

    expiry = datetime(2030, 1, 1, tzinfo=UTC)
    current = [expiry.replace(year=2029, month=12, day=31, hour=23, minute=59, second=59)]
    boundary_calls = []

    def respond_at_boundary(request):
        boundary_calls.append(request)
        return httpx.Response(200, json={"data": [{"id": model}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond_at_boundary)) as upstream:
        expiring_app = create_app(PROVIDER_KEY, JUDGE_TOKEN, token_expires_at=JUDGE_TOKEN_EXPIRES_AT,
                                  client=upstream, clock=lambda: current[0])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=expiring_app), base_url="http://test",
                                     headers={"Authorization": "Bearer " + JUDGE_TOKEN}) as client:
            assert (await client.get("/v1/models")).status_code == 200
            current[0] = expiry
            assert (await client.get("/v1/models")).status_code == 401
            assert (await client.get("/health")).status_code == 200
    assert len(boundary_calls) == 1
    print(json.dumps({"status": "passed", "python": sys.version.split()[0], "hosted_requests": 0,
                      "missing_credentials_fail_closed": True, "entrypoint_health_and_auth_verified": True,
                      "synthetic_catalog_completion_and_sse_verified": True,
                      "public_demo_without_judge_credentials_verified": True,
                      "missing_expiry_fails_closed": True, "exact_expiry_boundary_verified": True,
                      "desktop_agent_and_gpu_modules_not_imported": True, "deployed": False}))


asyncio.run(main())
