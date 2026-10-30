import asyncio
from types import SimpleNamespace

import bifang.server as server_module


def _stub_config(default_provider="nebius", providers=("nebius", "zai")):
    return SimpleNamespace(
        providers={name: object() for name in providers},
        default_provider=default_provider,
        routing_models={"fast": "nvidia/Nemotron-3-Nano-30B-A3B"},
        routing_mode="pinned",
        get_default_model=lambda name: "nvidia/Nemotron-3-Ultra-550b-a55b",
    )


class FakeManager:
    """Offline stand-in mirroring the ProviderManager surface the endpoint uses."""

    def __init__(self, catalogs=None, fallbacks=None):
        self._catalogs = catalogs or {}
        self._fallbacks = fallbacks or {}

    async def verified_model_ids(self, provider):
        ids = self._catalogs.get(provider)
        if ids is None:
            raise ValueError(f"No verified catalog for {provider}")
        return ids

    @property
    def registry(self):
        class Registry:
            def get(self, name):
                fallback = self._fallbacks.get(name, [])

                class StubProvider:
                    async def list_models(_self):
                        if not fallback:
                            raise RuntimeError("offline")
                        return [SimpleNamespace(id=model_id) for model_id in sorted(fallback)]

                return SimpleNamespace(name=name, list_models=StubProvider().list_models)

        registry = Registry()
        registry._fallbacks = self._fallbacks
        return registry

    async def close(self):
        pass


def _run_selectable(monkeypatch, cfg, manager, roles_by_provider):
    async def scenario():
        monkeypatch.setattr(server_module, "Config", SimpleNamespace(load=lambda: cfg))
        monkeypatch.setattr(server_module, "ProviderManager", lambda _cfg: manager)
        saved_roles = dict(server_module.PROVIDER_ROLES)
        server_module.PROVIDER_ROLES = roles_by_provider
        try:
            return await server_module.selectable_models()
        finally:
            server_module.PROVIDER_ROLES = saved_roles

    return asyncio.run(scenario())


def test_selectable_models_merges_providers_and_tags_composites(monkeypatch):
    cfg = _stub_config()
    manager = FakeManager(catalogs={
        "nebius": {"nvidia/Nemotron-3-Ultra-550b-a55b", "nvidia/Nemotron-3-Mini", "MiniMaxAI/MiniMax-M3"},
        "zai": {"glm-5.3", "glm-5.3-flash"},
    })
    roles_by_provider = {
        "nebius": {"fast": "nvidia/Nemotron-3-Nano-30B-A3B"},
        "zai": {"balanced": "glm-5.3", "reasoning": "glm-5.3"},
    }

    result = _run_selectable(monkeypatch, cfg, manager, roles_by_provider)

    assert result["provider"] == "nebius"
    assert result["configured_model"] == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert set(result["models"]) == {
        "nvidia/Nemotron-3-Ultra-550b-a55b",
        "nvidia/Nemotron-3-Mini",
        "MiniMaxAI/MiniMax-M3",
        "zai::glm-5.3",
        "zai::glm-5.3-flash",
    }
    assert result["providers"]["nebius"]["live"] is True
    assert result["providers"]["zai"]["live"] is True
    assert result["roles"] == roles_by_provider["nebius"]
    assert result["providers"]["zai"]["roles"]["reasoning"] == "glm-5.3"
    assert result["auto_available"] is False  # fast role id not in the live set


def test_selectable_models_falls_back_when_live_catalog_fails(monkeypatch):
    cfg = _stub_config()
    manager = FakeManager(fallbacks={"nebius": ["Nemotron-3-Nano"], "zai": ["glm-5.3"]})

    result = _run_selectable(monkeypatch, cfg, manager, {"nebius": {}})

    assert result["providers"]["nebius"]["live"] is False
    assert result["providers"]["nebius"]["models"] == ["Nemotron-3-Nano"]
    assert result["providers"]["zai"]["live"] is False
    assert "zai::glm-5.3" in result["models"]


def test_selectable_models_without_any_provider(monkeypatch):
    cfg = _stub_config(default_provider="", providers=())

    result = _run_selectable(monkeypatch, cfg, FakeManager(), {})

    assert result == {
        "provider": "",
        "models": [],
        "auto_available": False,
        "configured_model": None,
        "configured_mode": "pinned",
        "roles": {},
        "providers": {},
    }
