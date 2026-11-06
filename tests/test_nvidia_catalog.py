import asyncio

import httpx

from bifang.providers.base import ChatMessage
from bifang.providers.nvidia import NVIDIAProvider
from bifang.providers.types import ProviderConfig


def _provider_with_catalog(base_url: str, payload: dict | None = None, status_code: int = 200):
    provider = NVIDIAProvider(ProviderConfig(name="nvidia", base_url=base_url))
    original_client = provider.client

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload or {"data": []})

    provider.client = httpx.AsyncClient(
        base_url=base_url,
        transport=httpx.MockTransport(respond),
    )
    return provider, original_client


def test_custom_nim_catalog_lists_arbitrary_model_ids():
    async def exercise():
        provider, original_client = _provider_with_catalog(
            "http://127.0.0.1:8000/v1",
            {"data": [
                {"id": "custom-coder-7b"},
                {"id": "acme/vision-model"},
                {"id": "nvidia/nemotron-3-nano"},
                {"id": ""},
                {"id": None},
            ]},
        )
        try:
            return await provider.list_models()
        finally:
            await provider.client.aclose()
            await original_client.aclose()

    models = asyncio.run(exercise())
    assert [model.id for model in models] == [
        "custom-coder-7b", "acme/vision-model", "nvidia/nemotron-3-nano",
    ]


def test_nvidia_hosted_catalog_keeps_nvidia_model_filter():
    async def exercise():
        provider, original_client = _provider_with_catalog(
            "https://integrate.api.nvidia.com/v1",
            {"data": [
                {"id": "nvidia/nemotron-3-nano"},
                {"id": "meta/llama-3.1"},
            ]},
        )
        try:
            return await provider.list_models()
        finally:
            await provider.client.aclose()
            await original_client.aclose()

    models = asyncio.run(exercise())
    assert [model.id for model in models] == ["nvidia/nemotron-3-nano"]


def test_custom_nim_catalog_does_not_advertise_hosted_fallback_models():
    async def exercise():
        provider, original_client = _provider_with_catalog(
            "http://127.0.0.1:8000/v1", status_code=503,
        )
        try:
            return await provider.list_models()
        finally:
            await provider.client.aclose()
            await original_client.aclose()

    assert asyncio.run(exercise()) == []


def test_keyless_custom_nim_completion_uses_openai_compatible_request():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "model": "custom-coder-7b",
            "choices": [{
                "message": {"role": "assistant", "content": "local NIM mock ok"},
                "finish_reason": "stop",
            }],
        })

    async def exercise():
        base_url = "http://127.0.0.1:8000/v1"
        provider = NVIDIAProvider(ProviderConfig(
            name="nvidia",
            base_url=base_url,
            default_model="custom-coder-7b",
        ))
        original_client = provider.client
        provider.client = httpx.AsyncClient(
            base_url=base_url,
            transport=httpx.MockTransport(respond),
        )
        try:
            return await provider.complete(
                [ChatMessage(role="user", content="ping")],
                model="custom-coder-7b",
                max_tokens=8,
            )
        finally:
            await provider.client.aclose()
            await original_client.aclose()

    result = asyncio.run(exercise())

    assert result.content == "local NIM mock ok"
    assert result.reported_model == "custom-coder-7b"
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/chat/completions")
    assert "authorization" not in requests[0].headers
