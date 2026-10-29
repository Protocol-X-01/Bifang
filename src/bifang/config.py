from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

if os.getenv("BIFANG_NO_DOTENV") != "1":
    load_dotenv(dotenv_path=os.getenv("BIFANG_ENV_FILE") or None)

from bifang.approvals import APPROVAL_MODES, ApprovalMode
from bifang.providers.types import ProviderConfig


@dataclass
class Config:
    """Global configuration for Bifang."""
    # Provider settings
    default_provider: str = "nebius"
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    routing_mode: str = "pinned"
    routing_models: dict[str, str] = field(default_factory=dict)
    vision_models: dict[str, list[str]] = field(default_factory=dict)

    # Agent settings
    mode: str = "assist"
    approval_mode: ApprovalMode = "manual"
    max_steps: int = 12
    timeout: int = 180
    use_worktree: bool = True
    use_bwrap: bool = True

    # Context efficiency
    max_context_tokens: int = 100000
    enable_summarization: bool = True
    summarization_threshold: float = 0.8

    # Memory
    enable_memory: bool = True
    memory_db_path: str | None = None
    memory_embedding_model: str | None = None
    memory_embedding_provider: str | None = None
    enable_conversation_history: bool = True
    conversation_cache_path: str | None = None

    # Tracing
    enable_tracing: bool = False
    tracing_endpoint: str | None = None
    tracing_backend: str = "phoenix"

    # MCP
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from environment variables."""
        approval_mode = os.getenv("BIFANG_APPROVAL_MODE", "manual")
        if approval_mode not in APPROVAL_MODES:
            raise ValueError("BIFANG_APPROVAL_MODE must be manual, auto or full")
        providers = {}

        # NVIDIA
        nvidia_key = os.getenv("NVIDIA_API_KEY", "")
        if nvidia_key:
            providers["nvidia"] = ProviderConfig(
                name="nvidia",
                api_key=nvidia_key,
                base_url=os.getenv("BIFANG_NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/"),
                default_model=os.getenv("BIFANG_NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
            )

        # Nebius
        nebius_key = os.getenv("NEBIUS_API_KEY", "")
        if nebius_key:
            providers["nebius"] = ProviderConfig(
                name="nebius",
                api_key=nebius_key,
                base_url=os.getenv("BIFANG_NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1").rstrip("/"),
                default_model=os.getenv("BIFANG_NEBIUS_MODEL", "nvidia/Nemotron-3-Ultra-550b-a55b"),
            )

        # OpenAI
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            providers["openai"] = ProviderConfig(
                name="openai",
                api_key=openai_key,
                base_url=os.getenv("BIFANG_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
                default_model=os.getenv("BIFANG_OPENAI_MODEL", "openai/gpt-4o"),
            )

        # Anthropic
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            providers["anthropic"] = ProviderConfig(
                name="anthropic",
                api_key=anthropic_key,
                base_url=os.getenv("BIFANG_ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/"),
                default_model=os.getenv("BIFANG_ANTHROPIC_MODEL", "anthropic/claude-3-5-sonnet-20241022"),
            )

        # OpenRouter
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        if openrouter_key:
            providers["openrouter"] = ProviderConfig(
                name="openrouter",
                api_key=openrouter_key,
                base_url=os.getenv("BIFANG_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
                default_model=os.getenv("BIFANG_OPENROUTER_MODEL", "openrouter/anthropic/claude-3.5-sonnet"),
            )

        # Determine default provider
        default_provider = os.getenv("BIFANG_DEFAULT_PROVIDER", "nebius")
        if default_provider not in providers and providers:
            default_provider = next(iter(providers))

        return cls(
            default_provider=default_provider,
            providers=providers,
            routing_mode=os.getenv("BIFANG_ROUTING_MODE", "pinned"),
            vision_models=_parse_vision_models(os.getenv("BIFANG_VISION_MODELS", "")),
            routing_models={role: os.environ[name] for role, name in {
                "fast": "BIFANG_FAST_MODEL", "balanced": "BIFANG_BALANCED_MODEL",
                "reasoning": "BIFANG_REASONING_MODEL"}.items() if os.getenv(name)},
            mode=os.getenv("BIFANG_MODE", "assist"),
            approval_mode=approval_mode,
            max_steps=int(os.getenv("BIFANG_MAX_STEPS", "12")),
            timeout=int(os.getenv("BIFANG_TIMEOUT", "180")),
            use_worktree=os.getenv("BIFANG_WORKTREE", "1") != "0",
            use_bwrap=os.getenv("BIFANG_BWRAP", "1") != "0",
            max_context_tokens=int(os.getenv("BIFANG_MAX_CONTEXT_TOKENS", "100000")),
            enable_summarization=os.getenv("BIFANG_ENABLE_SUMMARIZATION", "1") != "0",
            summarization_threshold=float(os.getenv("BIFANG_SUMMARIZATION_THRESHOLD", "0.8")),
            enable_memory=os.getenv("BIFANG_ENABLE_MEMORY", "1") != "0",
            memory_db_path=os.getenv("BIFANG_MEMORY_DB_PATH"),
            memory_embedding_model=os.getenv("BIFANG_MEMORY_EMBEDDING_MODEL") or None,
            memory_embedding_provider=os.getenv("BIFANG_MEMORY_EMBEDDING_PROVIDER") or None,
            enable_conversation_history=os.getenv("BIFANG_ENABLE_CONVERSATION_HISTORY", "1") != "0",
            conversation_cache_path=os.getenv("BIFANG_CONVERSATION_CACHE_PATH") or None,
            enable_tracing=os.getenv("BIFANG_ENABLE_TRACING", "0") != "0",
            tracing_endpoint=os.getenv("BIFANG_TRACING_ENDPOINT"),
            tracing_backend=os.getenv("BIFANG_TRACING_BACKEND", "phoenix"),
            mcp_servers=_parse_mcp_servers(os.getenv("BIFANG_MCP_SERVERS", "")),
        )

    def get_provider_config(self, name: str | None = None) -> ProviderConfig | None:
        """Get provider configuration."""
        name = name or self.default_provider
        return self.providers.get(name)

    def get_default_model(self, provider_name: str | None = None) -> str | None:
        """Get default model for a provider."""
        config = self.get_provider_config(provider_name)
        return config.default_model if config else None

    def require_key(self, provider_name: str | None = None) -> None:
        """Ensure a provider has an API key."""
        config = self.get_provider_config(provider_name)
        if not config or not config.api_key:
            available = ", ".join(self.providers.keys())
            raise RuntimeError(
                f"No API key for provider '{provider_name or self.default_provider}'. "
                f"Available providers: {available}. "
                f"Set one of: NVIDIA_API_KEY, NEBIUS_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY"
            )


def _parse_mcp_servers(value: str) -> list[dict[str, Any]]:
    """Parse MCP servers from environment variable (JSON array)."""
    if not value:
        return []
    try:
        import json
        return json.loads(value)
    except Exception:
        return []


def _parse_vision_models(value: str) -> dict[str, list[str]]:
    import json
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError("BIFANG_VISION_MODELS must be a provider-to-model-list JSON object") from None
    if (not isinstance(parsed, dict) or set(parsed) - {"nebius", "nvidia"}
            or any(not isinstance(models, list) or len(models) > 64
                   or any(not isinstance(model, str) or not model.strip() or len(model) > 256 for model in models)
                   for models in parsed.values())):
        raise ValueError("BIFANG_VISION_MODELS must contain exact Nebius/NVIDIA model identifiers")
    return parsed


def state_home() -> Path:
    return Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local/state")) / "bifang"
