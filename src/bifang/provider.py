from __future__ import annotations

from contextlib import aclosing
from typing import Any, TYPE_CHECKING
from .config import Config
from .providers import ProviderRegistry, ProviderConfig
from .providers.nvidia import NVIDIAProvider
from .providers.nebius import NebiusProvider
from .providers.openai import OpenAIProvider
from .providers.anthropic import AnthropicProvider
from .providers.openrouter import OpenRouterProvider
from .providers.zai import ZAIProvider
from .providers.huggingface import HuggingFaceProvider

if TYPE_CHECKING:
    from .routing import TieredProviderManager, TaskType


class ProviderManager:
    """Manages multiple LLM providers."""

    def __init__(self, cfg: Config, registry: ProviderRegistry | None = None):
        self.cfg = cfg
        self.registry = registry if registry is not None else ProviderRegistry()
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize providers from config."""
        provider_classes = {
            "nvidia": NVIDIAProvider,
            "nebius": NebiusProvider,
            "openai": OpenAIProvider,
            "anthropic": AnthropicProvider,
            "openrouter": OpenRouterProvider,
            "zai": ZAIProvider,
            "huggingface": HuggingFaceProvider,
        }

        for name, config in self.cfg.providers.items():
            if name in provider_classes:
                provider = provider_classes[name](config)
                self.registry.register(provider, config)

    async def list_models(self, provider: str | None = None) -> list[str]:
        """List models from a provider or all providers."""
        if provider:
            p = self.registry.get(provider)
            if p:
                models = await p.list_models()
                return [m.id for m in models]
            return []

        all_models = await self.registry.list_all_models()
        return [m.id for m in all_models]

    async def embed(self, text: str, model: str, provider: str | None = None,
                    purpose: str = "passage") -> list[float]:
        target_provider = provider or self.cfg.default_provider
        selected = self.registry.get(target_provider)
        if purpose not in ("passage", "query"):
            raise ValueError("Embedding purpose must be passage or query")
        if selected is None or not hasattr(selected, "embed"):
            raise ValueError(f"Provider {target_provider} does not support embeddings")
        if not model.strip():
            raise ValueError("An embedding model must be configured explicitly")
        return await selected.embed(text, model, purpose=purpose)

    async def verified_model_ids(self, provider: str) -> set[str]:
        selected = self.registry.get(provider)
        if not selected or not hasattr(selected, "verified_model_ids"):
            raise ValueError("The selected provider has no verified catalog adapter")
        return await selected.verified_model_ids()

    @staticmethod
    def _split_model_spec(provider: str | None, model: str | None, default_provider: str) -> tuple[str, str | None]:
        """Resolve a 'provider::model' composite id into its parts.

        Bare model ids keep the default (or explicitly requested) provider;
        the split only happens when the caller did not choose a provider and
        the id carries an explicit tag.
        """
        if provider or not model or "::" not in model:
            return provider or default_provider, model
        prefix, _, remainder = model.partition("::")
        if prefix and remainder and "/" not in prefix:
            return prefix, remainder
        return default_provider, model

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Complete using the specified or auto-detected provider."""
        target_provider, target_model = self._split_model_spec(provider, model, default_provider=self.cfg.default_provider)
        if not target_model:
            raise ValueError(f"No model specified for provider {target_provider}")
        p = self.registry.get(target_provider)
        if not p:
            raise ValueError(f"Provider {target_provider} not found or doesn't support model {target_model}")

        # Convert messages to ChatMessage format
        from .providers.base import ChatMessage, ToolCall, ToolFunction
        chat_messages = []
        for msg in messages:
            tool_calls = None
            if msg.get("tool_calls"):
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        type=tc["type"],
                        function=ToolFunction(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"],
                        ),
                    )
                    for tc in msg["tool_calls"]
                ]
            chat_messages.append(ChatMessage(
                role=msg["role"],
                content=msg.get("content"),
                name=msg.get("name"),
                tool_call_id=msg.get("tool_call_id"),
                tool_calls=tool_calls,
            ))

        response = await p.complete(
            messages=chat_messages,
            model=target_model,
            tools=tools,
            tool_choice="auto",
            temperature=kwargs.get("temperature", 0.2),
            max_tokens=kwargs.get("max_tokens", 4096),
        )

        return {
            "role": "assistant",
            "provider": target_provider,
            "content": response.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in response.tool_calls or []
            ],
            "model": response.model,
            "reported_model": response.reported_model,
            "usage": response.usage,
            "finish_reason": response.finish_reason,
        }

    async def complete_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        """Stream completion from the specified or auto-detected provider."""
        target_provider, target_model = self._split_model_spec(provider, model, default_provider=self.cfg.default_provider)

        if not target_model:
            raise ValueError(f"No model specified for provider {target_provider}")

        p = self.registry.get(target_provider)
        if not p:
            raise ValueError(f"Provider {target_provider} not found or doesn't support model {target_model}")

        from .providers.base import ChatMessage, ToolCall, ToolFunction
        chat_messages = []
        for msg in messages:
            tool_calls = None
            if msg.get("tool_calls"):
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        type=tc["type"],
                        function=ToolFunction(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"],
                        ),
                    )
                    for tc in msg["tool_calls"]
                ]
            chat_messages.append(ChatMessage(
                role=msg["role"],
                content=msg.get("content"),
                name=msg.get("name"),
                tool_call_id=msg.get("tool_call_id"),
                tool_calls=tool_calls,
            ))

        async with aclosing(p.complete_stream(
            messages=chat_messages,
            model=target_model,
            tools=tools,
            tool_choice="auto",
            temperature=kwargs.get("temperature", 0.2),
            max_tokens=kwargs.get("max_tokens", 4096),
        )) as completion:
            async for chunk in completion:
                yield {
                    "content": chunk.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in chunk.tool_calls or []
                    ],
                    "model": chunk.model,
                    "reported_model": chunk.reported_model,
                    "usage": chunk.usage,
                    "finish_reason": chunk.finish_reason,
                }

    async def close(self):
        """Close all provider connections."""
        for provider in self.registry.get_all():
            if hasattr(provider, "close"):
                await provider.close()


def create_provider(cfg: Config) -> ProviderManager:
    """Factory function to create a provider manager."""
    return ProviderManager(cfg)


def create_tiered_provider(cfg: Config) -> "TieredProviderManager":
    """Factory function to create a tiered provider manager."""
    from .routing import TieredProviderManager
    base = ProviderManager(cfg)
    return TieredProviderManager(base, cfg)


# Re-export for backward compatibility
from .routing import TieredProviderManager, TaskType
__all__ = ["ProviderManager", "TieredProviderManager", "TaskType", "create_provider", "create_tiered_provider"]
