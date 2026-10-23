from __future__ import annotations

import asyncio
import hashlib
from typing import Callable, Optional


def create_simple_embedder(dimension: int = 1536) -> Callable[[str], list[float]]:
    """Create a simple deterministic embedder for testing (not for production use)."""
    def embed(text: str) -> list[float]:
        # Use a simple hash-based embedding (deterministic but not semantic)
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()
        # Expand to desired dimension
        result = []
        for i in range(dimension):
            byte_idx = i % len(hash_bytes)
            result.append((hash_bytes[byte_idx] / 255.0) * 2 - 1)
        return result
    return embed


async def create_provider_embedder(
    provider_manager,
    model: str,
    provider: str | None = None,
) -> Callable[[str], list[float]]:
    """Create an embedder using an LLM provider's embedding model."""
    async def embed(text: str) -> list[float]:
        # This would call the provider's embedding endpoint
        # For now, return a placeholder
        return [0.0] * 1536
    return embed