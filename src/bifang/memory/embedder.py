from __future__ import annotations

import hashlib
from collections.abc import Callable


def create_simple_embedder(dimension: int = 1536) -> Callable[[str], list[float]]:
    """Create deterministic, non-semantic vectors for tests only."""
    if dimension < 1:
        raise ValueError("Embedding dimension must be positive")

    def embed(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [(digest[index % len(digest)] / 255.0) * 2 - 1 for index in range(dimension)]

    embed.embedding_space = f"test-only-sha256:{dimension}"
    return embed


class ProviderEmbedder:
    """Embed documents and queries through an explicitly selected provider."""

    def __init__(self, provider_manager, model: str, provider: str | None = None):
        if not model.strip():
            raise ValueError("An embedding model is required")
        self.manager = provider_manager
        self.model = model
        config = getattr(provider_manager, "cfg", None) or getattr(provider_manager, "config", None)
        self.provider = provider or (config.default_provider if config else None)
        deployment = config.get_provider_config(self.provider) if config else None
        base_url = deployment.base_url if deployment else ""
        identity = f"{self.provider}\0{base_url}\0{model}"
        self.embedding_space = hashlib.sha256(identity.encode()).hexdigest()

    async def __call__(self, text: str) -> list[float]:
        return await self.embed_document(text)

    async def embed_document(self, text: str) -> list[float]:
        return await self.manager.embed(text, self.model, provider=self.provider, purpose="passage")

    async def embed_query(self, text: str) -> list[float]:
        return await self.manager.embed(text, self.model, provider=self.provider, purpose="query")


async def create_provider_embedder(provider_manager, model: str,
                                   provider: str | None = None) -> ProviderEmbedder:
    return ProviderEmbedder(provider_manager, model, provider)
