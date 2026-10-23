import asyncio
from types import SimpleNamespace

import pytest

from bifang.config import Config
from bifang.provider import ProviderManager
from bifang.providers.base import CompletionResponse
from bifang.providers.registry import ProviderRegistry


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("selected", [None, "nebius", "nvidia", "missing"])
def test_provider_selection_overrides_shared_model_prefix(monkeypatch, stream, selected):
    calls = []
    registry = ProviderRegistry()
    model = "nvidia/shared-model"

    def fake_provider(name):
        async def complete(**kwargs):
            calls.append(name)
            return CompletionResponse(content="ok", model=kwargs["model"])

        async def complete_stream(**kwargs):
            yield await complete(**kwargs)

        return SimpleNamespace(name=name, complete=complete, complete_stream=complete_stream,
                               supports_model=lambda model_id: model_id.startswith("nvidia/"))

    registry.register(fake_provider("nvidia"))
    registry.register(fake_provider("nebius"))
    monkeypatch.setattr("bifang.provider.get_registry", lambda: registry)
    manager = ProviderManager(Config(default_provider="nebius"))

    async def request():
        kwargs = {"messages": [{"role": "user", "content": "Hello"}], "model": model, "provider": selected}
        if stream:
            return [chunk async for chunk in manager.complete_stream(**kwargs)]
        return await manager.complete(**kwargs)

    if selected == "missing":
        with pytest.raises(ValueError, match="Provider missing"):
            asyncio.run(request())
        assert calls == []
    else:
        asyncio.run(request())
        assert calls == [selected or "nebius"]
