from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, AsyncIterator
from pydantic import BaseModel, Field

from .types import ProviderConfig


@dataclass
class ModelInfo:
    """Information about a model."""
    id: str
    name: str
    provider: str
    context_window: int = 4096
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    pricing_per_1k_input: float | None = None
    pricing_per_1k_output: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ChatMessage(BaseModel):
    """A chat message."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


class ToolCall(BaseModel):
    """A tool call from the model."""
    id: str
    type: Literal["function"] = "function"
    function: ToolFunction


class ToolFunction(BaseModel):
    """Function details for a tool call."""
    name: str
    arguments: str


class CompletionResponse(BaseModel):
    """Response from a completion request."""
    reported_model: str | None = None
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    model: str
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None


class Provider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List available models."""
        pass

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = "auto",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> CompletionResponse | AsyncIterator[CompletionResponse]:
        """Complete a chat conversation."""
        pass

    @abstractmethod
    async def complete_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = "auto",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[CompletionResponse]:
        """Stream a chat completion."""
        pass

    def get_default_model(self) -> str | None:
        """Get the default model for this provider."""
        return self.config.default_model

    def supports_model(self, model_id: str) -> bool:
        """Check if this provider supports a model."""
        return model_id.startswith(f"{self.name}/") or model_id == self.config.default_model


from typing import AsyncIterator
