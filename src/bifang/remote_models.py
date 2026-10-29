from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import HTTPException

from .provider import ProviderManager


class RemoteModelCatalog:
    def __init__(self, config, *, manager_factory=ProviderManager, clock=time.monotonic):
        self.config = config
        self.manager_factory = manager_factory
        self.clock = clock
        self.cache = {}
        self.lock = asyncio.Lock()

    async def __call__(self, provider):
        if provider not in {"nebius", "nvidia"} or provider not in self.config.providers:
            raise HTTPException(503, "This provider is not configured on the service")
        async with self.lock:
            cached = self.cache.get(provider)
            if cached is not None and self.clock() < cached[0]:
                return cached[1]
            manager = self.manager_factory(self.config)
            try:
                identifiers = await asyncio.wait_for(manager.verified_model_ids(provider), timeout=12)
                if (not isinstance(identifiers, set) or len(identifiers) > 4096
                        or any(not isinstance(model, str) or not model.strip() or len(model) > 256
                               or any(ord(character) < 32 for character in model) for model in identifiers)):
                    raise ValueError("Invalid live catalog")
            except (httpx.HTTPError, ValueError, OSError, TimeoutError):
                raise HTTPException(503, "Live model list unavailable; retry discovery shortly") from None
            finally:
                await manager.close()
            default = self.config.get_default_model(provider)
            result = {"provider": provider, "models": sorted(identifiers),
                      "default_model": default if default in identifiers else None}
            self.cache[provider] = (self.clock() + 30, result)
            return result
