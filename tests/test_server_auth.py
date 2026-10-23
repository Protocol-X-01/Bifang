import asyncio

import httpx

from bifang.server import app


def test_non_loopback_server_requires_api_key(monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("BIFANG_SERVER_API_KEY", "test-server-key")

    async def run_test():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                assert (await client.get("/health")).status_code == 200
                assert (await client.get("/sessions")).status_code == 401
                response = await client.get(
                    "/sessions",
                    headers={"X-API-Key": "test-server-key"},
                )
                assert response.status_code != 401

    asyncio.run(run_test())
