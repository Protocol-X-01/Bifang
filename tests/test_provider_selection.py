import asyncio
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from bifang.config import Config
from bifang.provider import ProviderManager
from bifang.providers.base import CompletionResponse
from bifang.providers.registry import ProviderRegistry
from bifang.providers.types import ProviderConfig
from bifang.routing import TaskClassifier, TaskType, TieredProviderManager


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


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("provider", ["nebius", "nvidia"])
def test_agent_router_preserves_configured_deployment(stream, provider):
    calls = []
    model = "deployment-specific-model"
    cfg = Config(default_provider=provider, providers={
        provider: ProviderConfig(name=provider, api_key="test-key", default_model=model),
    })

    async def complete(**kwargs):
        calls.append((kwargs["provider"], kwargs["model"]))
        return {"content": "ok"}

    async def complete_stream(**kwargs):
        yield await complete(**kwargs)

    manager = TieredProviderManager(SimpleNamespace(complete=complete, complete_stream=complete_stream), cfg)

    async def request():
        for task in TaskType:
            if stream:
                chunks = [chunk async for chunk in manager.complete_stream(messages=[], task_type=task)]
                assert chunks[0]["routing"]["model"] == model
            else:
                await manager.complete(messages=[], task_type=task)
            assert manager.get_routing_info(task)["provider"] == provider

    asyncio.run(request())
    assert calls == [(provider, model)] * len(TaskType)


@pytest.mark.parametrize("file_path", [Path("src/parser.py"), PureWindowsPath("src/parser.py")])
def test_task_classifier_accepts_workspace_paths(file_path):
    expected = TaskClassifier.classify("Fix the parser", {"files": [str(file_path)]})
    assert TaskClassifier.classify("Fix the parser", {"files": [file_path]}) == expected
