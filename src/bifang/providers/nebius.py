from __future__ import annotations

from .nvidia import NVIDIAProvider
from .base import ProviderConfig, ModelInfo


class NebiusProvider(NVIDIAProvider):
    """Nebius Token Factory provider (Nemotron models via Nebius)."""

    @property
    def name(self) -> str:
        return "nebius"

    def __init__(self, config: ProviderConfig):
        # Override base URL for Nebius
        config = ProviderConfig(
            name=config.name,
            api_key=config.api_key,
            base_url=config.base_url or "https://api.tokenfactory.nebius.com/v1",
            default_model=config.default_model or "nvidia/Nemotron-3-Ultra-550b-a55b",
            extra=config.extra,
        )
        super().__init__(config)

    def _get_fallback_models(self) -> list[ModelInfo]:
        """Fallback model list for Nebius."""
        return [
            ModelInfo(
                id="nvidia/nemotron-3-super-120b-a12b",
                name="Nemotron 3 Super (Nebius)",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="nvidia/nemotron-3-ultra-550b-a55b",
                name="Nemotron 3 Ultra (Nebius)",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                name="Nemotron 3 Nano Omni (Nebius)",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
        ]
