from __future__ import annotations

from typing import Any
from .base import Provider, ProviderConfig, ModelInfo


class ProviderRegistry:
    """Registry for managing multiple LLM providers."""

    def __init__(self):
        self._providers: dict[str, Provider] = {}
        self._configs: dict[str, ProviderConfig] = {}
        self._model_cache: dict[str, list[ModelInfo]] = {}

    def register(self, provider: Provider, config: ProviderConfig | None = None) -> None:
        """Register a provider."""
        self._providers[provider.name] = provider
        if config:
            self._configs[provider.name] = config

    def unregister(self, name: str) -> None:
        """Unregister a provider."""
        self._providers.pop(name, None)
        self._configs.pop(name, None)
        self._model_cache.pop(name, None)

    def get(self, name: str) -> Provider | None:
        """Get a provider by name."""
        return self._providers.get(name)

    def get_all(self) -> list[Provider]:
        """Get all registered providers."""
        return list(self._providers.values())

    def get_for_model(self, model_id: str) -> Provider | None:
        """Find the provider that supports a model."""
        for provider in self._providers.values():
            if provider.supports_model(model_id):
                return provider
        return None

    async def list_all_models(self, force_refresh: bool = False) -> list[ModelInfo]:
        """List models from all providers."""
        all_models = []
        for name, provider in self._providers.items():
            if force_refresh or name not in self._model_cache:
                try:
                    models = await provider.list_models()
                    self._model_cache[name] = models
                except Exception:
                    models = self._model_cache.get(name, [])
            else:
                models = self._model_cache[name]
            all_models.extend(models)
        return all_models

    def get_config(self, name: str) -> ProviderConfig | None:
        """Get provider configuration."""
        return self._configs.get(name)

    def set_config(self, name: str, config: ProviderConfig) -> None:
        """Set provider configuration."""
        self._configs[name] = config
        if name in self._providers:
            self._providers[name].config = config


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Get the global provider registry."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def set_registry(registry: ProviderRegistry) -> None:
    """Set the global provider registry."""
    global _registry
    _registry = registry