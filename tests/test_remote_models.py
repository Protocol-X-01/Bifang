import asyncio
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from bifang.remote_jobs import ReviewJobs
from bifang.remote_models import RemoteModelCatalog
from bifang.remote_server import RemoteTokens, create_remote_app


def test_live_catalog_cache_expiry_cleanup_and_verified_default():
    async def exercise():
        calls = []
        now = [0]

        class Manager:
            def __init__(self, config):
                pass

            async def verified_model_ids(self, provider):
                calls.append(provider)
                return {"model-b", "model-a"}

            async def close(self):
                calls.append("closed")

        config = SimpleNamespace(providers={"nebius": {}}, get_default_model=lambda provider: "model-b")
        catalog = RemoteModelCatalog(config, manager_factory=Manager, clock=lambda: now[0])
        expected = {"provider": "nebius", "models": ["model-a", "model-b"], "default_model": "model-b"}
        assert await catalog("nebius") == expected
        assert await catalog("nebius") == expected
        assert calls == ["nebius", "closed"]
        now[0] = 31
        config.get_default_model = lambda provider: "not-listed"
        assert (await catalog("nebius"))["default_model"] is None
        assert calls == ["nebius", "closed", "nebius", "closed"]
        with pytest.raises(HTTPException) as failure:
            await catalog("nvidia")
        assert failure.value.status_code == 503

    asyncio.run(exercise())


@pytest.mark.parametrize("reply", [ValueError("private upstream details"), {""}, {"a\nb"}, {"a" * 257}, ["model"]])
def test_catalog_errors_are_bounded_redacted_and_not_cached(reply):
    async def exercise():
        closes = []

        class Manager:
            def __init__(self, config):
                pass

            async def verified_model_ids(self, provider):
                if isinstance(reply, Exception):
                    raise reply
                return reply

            async def close(self):
                closes.append(True)

        catalog = RemoteModelCatalog(SimpleNamespace(providers={"nebius": {}}), manager_factory=Manager)
        with pytest.raises(HTTPException) as failure:
            await catalog("nebius")
        assert failure.value.status_code == 503
        assert "private" not in failure.value.detail
        assert closes == [True]
        assert catalog.cache == {}

    asyncio.run(exercise())


def test_model_route_requires_auth_and_rejects_arbitrary_providers(tmp_path):
    async def exercise():
        token = "synthetic-owner-token-for-catalogue"
        tokens = RemoteTokens(json.dumps([{"subject": "owner", "token_sha256": hashlib.sha256(token.encode()).hexdigest()}]))
        calls = []

        async def catalog(provider):
            calls.append(provider)
            return {"provider": provider, "models": ["synthetic-model"], "default_model": None}

        app = create_remote_app(ReviewJobs(tmp_path / "state"), tokens, model_catalog=catalog)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/v1/models/nebius")).status_code == 401
            assert calls == []
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get("/v1/models/nebius", headers=headers)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.json()["models"] == ["synthetic-model"]
            assert (await client.get("/v1/models/unconfigured", headers=headers)).status_code == 422
            assert calls == ["nebius"]

    asyncio.run(exercise())
