import asyncio
from types import SimpleNamespace

import httpx
import pytest

from bifang import server
from bifang.agent import Agent
from bifang.config import Config
from bifang.provider import ProviderManager
from bifang.providers.nvidia import NVIDIAProvider
from bifang.providers.types import ProviderConfig
from bifang.routing import (
    TOKEN_FACTORY_ROLES,
    CatalogUnavailable,
    ModelSelectionError,
    TaskType,
    TieredProviderManager,
)


@pytest.mark.parametrize("stream", [False, True])
def test_auto_routes_three_roles_without_switching_providers_or_changing_pinned_default(stream):
    calls, catalogs = [], []
    cfg = Config(default_provider="nebius", providers={
        "nebius": ProviderConfig("nebius", "test-key", default_model="custom-pinned")})

    async def verified(provider):
        catalogs.append(provider)
        return set(TOKEN_FACTORY_ROLES.values())

    async def complete(**kwargs):
        calls.append((kwargs["provider"], kwargs["model"]))
        return {"content": "ok", "reported_model": "server-canonical-id",
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "nested": {"cached": 0}}}

    async def complete_stream(**kwargs):
        yield await complete(**kwargs)

    manager = TieredProviderManager(SimpleNamespace(complete=complete, complete_stream=complete_stream,
                                                    verified_model_ids=verified), cfg)

    async def scenario():
        for task, role in [(TaskType.SYNTAX_CHECK, "fast"), (TaskType.CODE_REVIEW, "balanced"),
                           (TaskType.ARCHITECTURE, "reasoning"), (TaskType.CHAT, "balanced")]:
            if stream:
                await anext(manager.complete_stream([], task_type=task, routing_mode="auto"))
            else:
                await manager.complete([], task_type=task, routing_mode="auto")
            receipt = manager.requests[-1]
            assert receipt["requested_model"] == TOKEN_FACTORY_ROLES[role]
            assert receipt["reported_model"] == "server-canonical-id"
            assert receipt["role"] == role
            assert calls[-1] == ("nebius", TOKEN_FACTORY_ROLES[role])
            if not stream:
                assert receipt["usage"] == {"prompt_tokens": 12, "completion_tokens": 3}
        await manager.complete([], task_type=TaskType.SYNTAX_CHECK)
        assert calls[-1] == ("nebius", "custom-pinned")
        assert cfg.routing_mode == "pinned"
        assert catalogs == ["nebius"]

    asyncio.run(scenario())


@pytest.mark.parametrize("catalog_error", [True, False])
def test_missing_catalog_or_model_never_falls_back_or_calls_inference(catalog_error):
    async def verified(provider):
        if catalog_error:
            raise httpx.ConnectError("synthetic private backend detail")
        return set()

    async def complete(**kwargs):
        pytest.fail("Inference must not run")

    manager = TieredProviderManager(SimpleNamespace(complete=complete, verified_model_ids=verified), Config())
    with pytest.raises(CatalogUnavailable if catalog_error else ModelSelectionError):
        asyncio.run(manager.complete([], task_type=TaskType.CHAT, routing_mode="auto"))
    assert manager.requests == []


def test_custom_nim_remains_pinned_and_auto_is_rejected():
    async def complete(**kwargs):
        assert kwargs["model"] == "private-nim-profile"
        assert kwargs["provider"] == "nvidia"
        return {"content": "ok"}

    config = Config(default_provider="nvidia", providers={
        "nvidia": ProviderConfig("nvidia", "test-key", default_model="private-nim-profile")})
    manager = TieredProviderManager(SimpleNamespace(complete=complete), config)
    asyncio.run(manager.complete([], task_type=TaskType.SYNTAX_CHECK))
    with pytest.raises(ModelSelectionError):
        asyncio.run(manager.complete([], task_type=TaskType.SYNTAX_CHECK, routing_mode="auto"))


def test_strict_catalog_does_not_use_provider_fallbacks():
    async def scenario():
        provider = NVIDIAProvider(ProviderConfig("nvidia", "test-key"))
        await provider.client.aclose()
        provider.client = httpx.AsyncClient(base_url="https://example.invalid/v1",
                                           transport=httpx.MockTransport(lambda request: httpx.Response(503)))
        try:
            assert await provider.list_models()
            with pytest.raises(httpx.HTTPStatusError):
                await provider.verified_model_ids()
        finally:
            await provider.close()

    asyncio.run(scenario())


def test_reported_model_is_not_fabricated_when_server_omits_it():
    provider = NVIDIAProvider(ProviderConfig("nvidia", "test-key"))
    payload = {"choices": [{"message": {"content": "ok"}}]}
    assert provider._parse_response(payload, "requested").reported_model is None
    payload["model"] = "actual-reported-id"
    assert provider._parse_response(payload, "requested").reported_model == "actual-reported-id"
    asyncio.run(provider.close())


def test_api_selection_receipts_and_durable_history(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BIFANG_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(server, "sessions", {})
    config = Config(enable_memory=False, use_worktree=False, providers={
        "nebius": ProviderConfig("nebius", "test-key", default_model="original-pinned")})
    monkeypatch.setattr(server.Config, "load", lambda: config)
    calls = []

    async def verified(self, provider):
        return set(TOKEN_FACTORY_ROLES.values())

    async def complete(self, **kwargs):
        calls.append(kwargs["model"])
        return {"role": "assistant", "content": "synthetic answer", "reported_model": "server-id",
                "model": kwargs["model"], "usage": {"prompt_tokens": 10, "completion_tokens": 2}}

    async def no_services(self):
        return

    monkeypatch.setattr(ProviderManager, "verified_model_ids", verified)
    monkeypatch.setattr(ProviderManager, "complete", complete)
    monkeypatch.setattr(Agent, "_ensure_services_started", no_services)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            catalog = (await client.get("/models")).json()
            assert catalog["auto_available"] is True
            assert set(catalog["models"]) == set(TOKEN_FACTORY_ROLES.values())
            session = (await client.post("/sessions", json={"workspace": "."})).json()["session_id"]
            try:
                for selection in ({"routing_mode": "auto"},
                                  {"routing_mode": "pinned", "model": TOKEN_FACTORY_ROLES["fast"]}, None):
                    response = await client.post(f"/sessions/{session}/chat", json={"prompt": "hello", "selection": selection})
                    assert response.status_code == 200
                    receipt = response.json()["routing"][0]
                    assert receipt["provider"] == "nebius"
                    assert receipt["reported_model"] == "server-id"
                assert calls == [TOKEN_FACTORY_ROLES["balanced"], TOKEN_FACTORY_ROLES["fast"], "original-pinned"]
                history = (await client.get(f"/sessions/{session}/history")).json()
                assert len(history) == 3
                assert history[0]["routing"][0]["requested_model"] == TOKEN_FACTORY_ROLES["balanced"]
                for selection in ({"routing_mode": "auto", "model": "conflict"},
                                  {"routing_mode": "pinned", "provider": "nvidia"}):
                    assert (await client.post(f"/sessions/{session}/chat", json={"prompt": "hello", "selection": selection})).status_code == 422
                assert (await client.post(f"/sessions/{session}/chat", json={"prompt": "hello", "selection": {
                    "routing_mode": "pinned", "model": "not-in-catalog"}})).status_code == 400
                assert len(calls) == 3
            finally:
                await client.delete(f"/sessions/{session}")

    asyncio.run(scenario())
