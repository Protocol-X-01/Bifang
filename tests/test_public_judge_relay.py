import asyncio
import base64
import hashlib
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from bifang.judge_access import check_access
from bifang.judge_quota import PublicQuotaExceeded, PublicQuotaUnavailable
from bifang.judge_relay import create_app, public_access_enabled
from bifang.model_ids import TOKEN_FACTORY_ROLES
from bifang.providers.base import ChatMessage
from bifang.providers.nebius import NebiusProvider
from bifang.providers.types import ProviderConfig

PROVIDER_KEY = "synthetic-provider-key-for-public-tests"
EXPIRY = datetime(2099, 1, 1, tzinfo=UTC)
MODEL = TOKEN_FACTORY_ROLES["fast"]
PAYLOAD = {"model": MODEL, "messages": [{"role": "user", "content": "Synthetic coding request"}]}


class GrantedQuota:
    async def reserve(self, **reservation):
        pass

    async def aclose(self):
        pass


@pytest.mark.parametrize(("value", "expected"), [(None, False), ("", False), ("0", False), ("1", True)])
def test_public_access_requires_explicit_opt_in(value, expected):
    assert public_access_enabled(value) is expected


@pytest.mark.parametrize("value", ["true", "yes", "False", " 1", "1 "])
def test_mistyped_public_access_setting_fails_closed(value):
    with pytest.raises(ValueError, match="must be 0 or 1"):
        public_access_enabled(value)


def test_public_demo_and_existing_provider_client_need_no_secret():
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer " + PROVIDER_KEY
        assert "bifang-public-demo" not in str(request.headers)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": value} for value in TOKEN_FACTORY_ROLES.values()]})
        return httpx.Response(200, json={"model": MODEL, "choices": [{"message": {"content": "Synthetic answer"}}]})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as upstream:
            app = create_app(PROVIDER_KEY, "", public_access=True, public_quota=GrantedQuota(),
                             token_expires_at=EXPIRY, client=upstream)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://relay") as browser:
                page = await browser.get("/")
                assert page.status_code == 200
                assert 'id="prompt-form"' in page.text
                assert PROVIDER_KEY not in page.text
                assert "unsafe-inline" not in page.headers["content-security-policy"]
                for tag in ("script", "style"):
                    contents = re.search(f"<{tag}>(.*?)</{tag}>", page.text, re.DOTALL).group(1)
                    digest = base64.b64encode(hashlib.sha256(contents.encode()).digest()).decode()
                    assert "sha256-" + digest in page.headers["content-security-policy"]
                catalog = await browser.get("/v1/models")
                assert {row["id"] for row in catalog.json()["data"]} == set(TOKEN_FACTORY_ROLES.values())
                completion = await browser.post("/v1/chat/completions", json=PAYLOAD,
                                                headers={"Authorization": "Bearer bifang-public-demo"})
                assert completion.status_code == 200
                assert completion.json()["choices"][0]["message"]["content"] == "Synthetic answer"
                provider = NebiusProvider(ProviderConfig("nebius", "bifang-public-demo", "https://relay/v1", MODEL))
                await provider.client.aclose()
                provider.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://relay/v1")
                try:
                    result = await provider.complete([ChatMessage(role="user", content="Synthetic fixture")], MODEL)
                    assert result.content == "Synthetic answer"
                    assert result.reported_model == MODEL
                finally:
                    await provider.close()
                for path in ("/sessions", "/v1/files", "/bifang/judge_relay.py", "/.env.local", "/docs"):
                    assert (await browser.get(path)).status_code == 404
                assert len(calls) == 3
                assert (await browser.post("/v1/chat/completions", json=PAYLOAD,
                                          headers={"Origin": "https://unrelated.invalid"})).status_code == 403
                assert (await browser.post("/v1/chat/completions", content="{}",
                                          headers={"Content-Type": "text/plain"})).status_code == 415
                assert len(calls) == 3
                report = await check_access("https://relay", client=browser, public_access=True)
                assert report["passed"]
                assert report["metadata_get_requests"] == 7
                assert report["completion_requests_sent"] == 0

    asyncio.run(scenario())


def test_public_access_keeps_expiry_and_server_secret_requirements():
    with pytest.raises(ValueError, match="provider credentials"):
        create_app("", "", public_access=True, token_expires_at=EXPIRY)
    with pytest.raises(TypeError, match="boolean"):
        create_app(PROVIDER_KEY, "", public_access="1", token_expires_at=EXPIRY)
    with pytest.raises(ValueError, match="EXPIRES_AT"):
        create_app(PROVIDER_KEY, "", public_access=True)

    async def scenario():
        current = [EXPIRY - timedelta(seconds=1)]
        calls = []

        def respond(request):
            calls.append(request)
            return httpx.Response(200, json={"data": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as upstream:
            app = create_app(PROVIDER_KEY, "", public_access=True, public_quota=GrantedQuota(), token_expires_at=EXPIRY,
                             clock=lambda: current[0], client=upstream)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://relay") as browser:
                assert (await browser.get("/v1/models")).status_code == 200
                current[0] = EXPIRY
                assert (await browser.get("/")).status_code == 401
                assert (await browser.get("/v1/models")).status_code == 401
                assert (await browser.post("/v1/chat/completions", json=PAYLOAD)).status_code == 401
                assert (await browser.get("/health")).status_code == 200
                assert len(calls) == 1

    asyncio.run(scenario())


def test_public_mode_requires_a_shared_guard():
    with pytest.raises(ValueError, match="shared public-demo usage guard"):
        create_app(PROVIDER_KEY, "", public_access=True, token_expires_at=EXPIRY)


@pytest.mark.parametrize(("failure", "status"), [(PublicQuotaExceeded, 429), (PublicQuotaUnavailable, 503)])
def test_public_guard_failure_never_reaches_provider(failure, status):
    calls, reservations = [], []

    class Guard(GrantedQuota):
        async def reserve(self, **reservation):
            reservations.append(reservation)
            raise failure()

    async def scenario():
        def respond(request):
            calls.append(request)
            return httpx.Response(200, json={})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as upstream:
            app = create_app(PROVIDER_KEY, "", public_access=True, public_quota=Guard(),
                             token_expires_at=EXPIRY, client=upstream)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://relay") as client:
                response = await client.post("/v1/chat/completions", json=PAYLOAD)
                assert response.status_code == status
                if status == 429:
                    assert int(response.headers["retry-after"]) > 0
                assert "synthetic-provider" not in response.text
                assert reservations == [{"output_tokens": 4096, "body_bytes": len(response.request.content)}]
                assert not calls
                assert (await client.get("/health")).status_code == 200
                assert (await client.get("/")).status_code == 200

    asyncio.run(scenario())


def test_public_request_limits_reject_before_reservation_or_provider():
    async def scenario():
        class Guard(GrantedQuota):
            async def reserve(self, **reservation):
                pytest.fail("Invalid requests must not reserve or call the provider")

        app = create_app(PROVIDER_KEY, "", public_access=True, public_quota=Guard(), token_expires_at=EXPIRY)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://relay") as client:
                assert (await client.post("/v1/chat/completions", json={**PAYLOAD, "max_tokens": 8193})).status_code == 400
                large = {**PAYLOAD, "messages": [{"role": "user", "content": "x" * 32768}]}
                assert (await client.post("/v1/chat/completions", json=large)).status_code == 413
        finally:
            async with app.router.lifespan_context(app):
                pass

    asyncio.run(scenario())
