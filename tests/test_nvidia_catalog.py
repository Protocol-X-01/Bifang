import asyncio

import httpx

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
