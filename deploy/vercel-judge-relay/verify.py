import asyncio
import importlib
import json
import os
import subprocess
import sys

import httpx

from bifang.judge_relay import create_app
from bifang.model_ids import TOKEN_FACTORY_ROLES

PROVIDER_KEY = "synthetic-provider-credential-only"
JUDGE_TOKEN = "synthetic-judge-credential-more-than-32-characters"


async def main():
    empty = {name: value for name, value in os.environ.items() if name in {"PATH", "LANG", "LC_ALL"}}
    missing = await asyncio.to_thread(subprocess.run, [sys.executable, "-c", "import app"],
                                     env=empty, capture_output=True)
    assert missing.returncode != 0 and b"Configure separate provider credentials" in missing.stderr
    os.environ["NEBIUS_API_KEY"] = PROVIDER_KEY
    os.environ["BIFANG_JUDGE_TOKEN"] = JUDGE_TOKEN
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
        app = create_app(PROVIDER_KEY, JUDGE_TOKEN, client=upstream)
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
    print(json.dumps({"status": "passed", "python": sys.version.split()[0], "hosted_requests": 0,
                      "missing_credentials_fail_closed": True, "entrypoint_health_and_auth_verified": True,
                      "synthetic_catalog_completion_and_sse_verified": True,
                      "desktop_agent_and_gpu_modules_not_imported": True, "deployed": False}))


asyncio.run(main())
