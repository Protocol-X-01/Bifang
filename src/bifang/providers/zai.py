from __future__ import annotations

from .openai import OpenAIProvider
from .base import ProviderConfig, ModelInfo


class ZAIProvider(OpenAIProvider):
    """Z.ai GLM provider (OpenAI-compatible chat completions)."""

    @property
    def name(self) -> str:
        return "zai"

    def __init__(self, config: ProviderConfig):
        config = ProviderConfig(
            name=config.name,
            api_key=config.api_key,
            base_url=config.base_url or "https://api.z.ai/api/paas/v4",
            default_model=config.default_model or "glm-5.3",
            extra=config.extra,
        )
        super().__init__(config)

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self.client.get("/models", headers=self.config.get_headers())
            response.raise_for_status()
            return self._list_model_ids(response.json())
        except Exception:
            return self._get_fallback_models()
    def _list_model_ids(self, data: dict) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if not isinstance(model_id, str) or not model_id.startswith("glm-"):
                continue
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                provider=self.name,
                context_window=1_000_000 if "5.3" in model_id else 128_000,
                supports_tools=True,
                supports_streaming=True,
                supports_vision="flash" in model_id,
                metadata=m,
            ))
        return models if models else self._get_fallback_models()

    def _get_fallback_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="glm-5.3",
                name="GLM-5.3 (Z.ai flagship, always reasoning, 1M context)",
                provider=self.name,
                context_window=1_000_000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="glm-5.3-flash",
                name="GLM-5.3-Flash (multimodal, visual programming, 1M context)",
                provider=self.name,
                context_window=1_000_000,
                supports_tools=True,
                supports_streaming=True,
                supports_vision=True,
            ),
            ModelInfo(
                id="glm-5.3-flashx",
                name="GLM-5.3-FlashX (multimodal)",
                provider=self.name,
                context_window=1_000_000,
                supports_tools=True,
                supports_streaming=True,
                supports_vision=True,
            ),
        ]
