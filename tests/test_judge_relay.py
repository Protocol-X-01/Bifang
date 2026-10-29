import asyncio

import httpx
import pytest

from bifang.judge_relay import MAX_BODY_BYTES, UPSTREAM, create_app
from bifang.providers.base import ChatMessage
from bifang.providers.nebius import NebiusProvider
from bifang.providers.types import ProviderConfig
from bifang.routing import TOKEN_FACTORY_ROLES

PROVIDER_KEY = "synthetic-provider-key-not-live"
JUDGE_TOKEN = "synthetic-judge-token-with-more-than-32-characters"
MODEL = TOKEN_FACTORY_ROLES["reasoning"]
PAYLOAD = {"model": MODEL, "messages": [{"role": "user", "content": "Synthetic fixture"}]}
AUTH = {"Authorization": "Bearer " + JUDGE_TOKEN}


def test_relay_auth_fixed_upstream_and_native_provider_compatibility():
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer " + PROVIDER_KEY
        assert JUDGE_TOKEN.encode() not in request.content
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": MODEL}, {"id": "not-enabled"}]})
        assert str(request.url) == UPSTREAM + "/chat/completions"
        return httpx.Response(200, json={"model": MODEL, "choices": [{"message": {
            "role": "assistant", "content": "Synthetic relay answer"}}]})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as upstream:
            app = create_app(PROVIDER_KEY, JUDGE_TOKEN, client=upstream)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://relay") as browser:
                assert (await browser.get("/health")).status_code == 200
                assert (await browser.get("/v1/models")).status_code == 401
                assert (await browser.post("/v1/chat/completions", json=PAYLOAD,
                                          headers={"Authorization": "Bearer wrong"})).status_code == 401
                assert not calls
                catalog = await browser.get("/v1/models", headers=AUTH)
                assert catalog.json()["data"] == [{"id": MODEL}]
                for path in ("/sessions", "/v1/files", "/docs", "/openapi.json"):
                    assert (await browser.get(path, headers=AUTH)).status_code == 404
            provider = NebiusProvider(ProviderConfig("nebius", JUDGE_TOKEN, "http://relay/v1", MODEL))
            await provider.client.aclose()
            provider.client = httpx.AsyncClient(transport=transport, base_url="http://relay/v1")
            try:
                result = await provider.complete([ChatMessage(role="user", content="Synthetic fixture")], MODEL)
                assert result.content == "Synthetic relay answer"
                assert result.reported_model == MODEL
            finally:
                await provider.close()
            assert len(calls) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("change", [{"model": "disabled"}, {"model": {}}, {"url": "https://other.invalid"},
                                    {"max_tokens": True}, {"max_tokens": 32769}, {"stream": "yes"},
                                    {"messages": []}, {"messages": ["not an object"]}])
def test_relay_rejects_invalid_requests_without_upstream_calls(change):
    def forbidden(request):
        pytest.fail("Rejected request reached provider")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as upstream:
            app = create_app(PROVIDER_KEY, JUDGE_TOKEN, client=upstream)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://relay") as client:
                response = await client.post("/v1/chat/completions", json={**PAYLOAD, **change}, headers=AUTH)
                assert response.status_code == 400
                assert PROVIDER_KEY not in response.text

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_relay_does_not_follow_redirects_or_expose_provider_errors(status):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, text="Synthetic private upstream detail " + PROVIDER_KEY,
                              headers={"Location": "https://other.invalid/steal"})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as upstream:
            app = create_app(PROVIDER_KEY, JUDGE_TOKEN, client=upstream)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://relay") as client:
                response = await client.post("/v1/chat/completions", json=PAYLOAD, headers=AUTH)
                assert response.status_code == (429 if status == 429 else 502)
                assert "Synthetic private upstream" not in response.text
                assert PROVIDER_KEY not in response.text
                assert len(calls) == 1

    asyncio.run(scenario())


def test_relay_preserves_stream_bytes_and_closes_upstream():
    wire = b'data: {"choices":[]}\n\ndata: [DONE]\n\n'
    closed = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield wire[:12]
            yield wire[12:]

        async def aclose(self):
            closed.append(True)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=Stream()))) as upstream:
            app = create_app(PROVIDER_KEY, JUDGE_TOKEN, client=upstream)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://relay") as client:
                response = await client.post("/v1/chat/completions", json={**PAYLOAD, "stream": True}, headers=AUTH)
                assert response.content == wire
                assert response.headers["cache-control"] == "no-store"
                assert closed

    asyncio.run(scenario())


def test_relay_caps_actual_body_and_rejects_missing_or_shared_credentials():
    for provider, token in [("", JUDGE_TOKEN), (PROVIDER_KEY, "short"), (JUDGE_TOKEN, JUDGE_TOKEN)]:
        with pytest.raises(ValueError):
            create_app(provider, token)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("Oversized request forwarded"))) as upstream:
            app = create_app(PROVIDER_KEY, JUDGE_TOKEN, client=upstream)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://relay") as client:
                response = await client.post("/v1/chat/completions", content=b" " * (MAX_BODY_BYTES + 1), headers=AUTH)
                assert response.status_code == 413
                for body in (b"{", b'{"nested":{"nonfinite":NaN}}'):
                    malformed = await client.post("/v1/chat/completions", content=body, headers=AUTH)
                    assert malformed.status_code == 400

    asyncio.run(scenario())


def test_relay_disconnect_finishes_async_upstream_close():
    async def scenario():
        disconnected = asyncio.Event()
        closed = asyncio.Event()

        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"data: synthetic-first-chunk\n\n"
                await asyncio.sleep(30)

            async def aclose(self):
                await asyncio.sleep(0.01)
                closed.set()

        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=Stream()))) as upstream:
            app = create_app(PROVIDER_KEY, JUDGE_TOKEN, client=upstream)
            body = ('{"model":"' + MODEL + '","messages":[{"role":"user",'
                    '"content":"Synthetic fixture"}],"stream":true}').encode()
            received = False

            async def receive():
                nonlocal received
                if not received:
                    received = True
                    return {"type": "http.request", "body": body, "more_body": False}
                await disconnected.wait()
                return {"type": "http.disconnect"}

            async def send(message):
                if message["type"] == "http.response.body" and message.get("body"):
                    disconnected.set()

            scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
                     "http_version": "1.1", "method": "POST", "scheme": "http", "root_path": "",
                     "path": "/v1/chat/completions", "raw_path": b"/v1/chat/completions",
                     "query_string": b"", "server": ("test", 80), "client": ("127.0.0.1", 12345),
                     "headers": [(b"authorization", ("Bearer " + JUDGE_TOKEN).encode()),
                                 (b"content-type", b"application/json")]}
            await asyncio.wait_for(app(scope, receive, send), timeout=2)
            assert disconnected.is_set()
            assert closed.is_set(), "Disconnect interrupted upstream cleanup"

    asyncio.run(scenario())
