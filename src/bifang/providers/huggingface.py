from __future__ import annotations

from .openai import OpenAIProvider
from .base import ProviderConfig, ModelInfo


class HuggingFaceProvider(OpenAIProvider):
    """HuggingFace Inference Providers router (OpenAI-compatible)."""

    @property
    def name(self) -> str:
        return "huggingface"

    def __init__(self, config: ProviderConfig):
        config = ProviderConfig(
            name=config.name,
            api_key=config.api_key,
            base_url=config.base_url or "https://router.huggingface.co/v1",
            default_model=config.default_model or "meta-llama/Llama-3.3-70B-Instruct",
            extra=config.extra,
        )
        super().__init__(config)

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self.client.get("/models", headers=self.config.get_headers())
            response.raise_for_status()
            data = response.json()
        except Exception:
            return self._get_fallback_models()
        models: list[ModelInfo] = []
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if not isinstance(model_id, str) or "/" not in model_id or model_id.count("/") != 1:
                continue
            models.append(ModelInfo(
                id=model_id,
                name=model_id.split("/")[-1],
                provider=self.name,
                supports_tools=True,
                supports_streaming=True,
                context_window=128_000,
                metadata=m,
            ))
        return models if models else self._get_fallback_models()

    def _get_fallback_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="meta-llama/Llama-3.3-70B-Instruct",
                name="Llama 3.3 70B Instruct",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="deepseek-ai/DeepSeek-V3-0324",
                name="DeepSeek V3 (0324)",
                provider=self.name,
                context_window=65536,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="Qwen/Qwen2.5-Coder-32B-Instruct",
                name="Qwen2.5 Coder 32B Instruct",
                provider=self.name,
                context_window=32768,
                supports_tools=True,
                supports_streaming=True,
            ),
        ]
