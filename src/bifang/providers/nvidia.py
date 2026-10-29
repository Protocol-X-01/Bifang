from __future__ import annotations

import httpx
from typing import AsyncIterator, Any
from .base import (
    Provider,
    ProviderConfig,
    ModelInfo,
    ChatMessage,
    ToolCall,
    CompletionResponse,
    ToolFunction,
)
from .embeddings import request_embedding
from .streaming import decode_chat_stream


class NVIDIAProvider(Provider):
    """NVIDIA Inference API provider (Nemotron models)."""

    @property
    def name(self) -> str:
        return "nvidia"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://integrate.api.nvidia.com/v1"
        self.client = httpx.AsyncClient(timeout=60.0, base_url=self.base_url)

    async def list_models(self) -> list[ModelInfo]:
        """List available NVIDIA models."""
        try:
            response = await self.client.get("/models", headers=self.config.get_headers())
            response.raise_for_status()
            data = response.json()
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                if "nemotron" in model_id.lower() or "nvidia" in model_id.lower():
                    models.append(ModelInfo(
                        id=model_id,
                        name=model_id.split("/")[-1],
                        provider=self.name,
                        context_window=self._get_context_window(model_id),
                        supports_tools=True,
                        supports_streaming=True,
                        metadata=m,
                    ))
            return models
        except Exception:
            return self._get_fallback_models()

    async def verified_model_ids(self) -> set[str]:
        response = await self.client.get("/models", headers=self.config.get_headers())
        response.raise_for_status()
        data = response.json().get("data")
        if not isinstance(data, list) or any(not isinstance(item, dict) or
                                           not isinstance(item.get("id"), str) for item in data):
            raise ValueError("Invalid live model catalog")
        return {item["id"] for item in data}

    async def embed(self, text: str, model: str, purpose: str = "passage") -> list[float]:
        use_input_type = self.config.extra.get("embedding_input_type", self.name == "nvidia")
        return await request_embedding(self.client, self.config, text, model,
                                       purpose if use_input_type else None)

    def _get_fallback_models(self) -> list[ModelInfo]:
        """Fallback model list."""
        return [
            ModelInfo(
                id="nvidia/nemotron-3-ultra-550b-a55b",
                name="Nemotron 3 Ultra",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="nvidia/nemotron-3-super-120b-a12b",
                name="Nemotron 3 Super",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                name="Nemotron 3 Nano Omni",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="nvidia/llama-3.1-nemotron-70b-instruct",
                name="Llama 3.1 Nemotron 70B",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
        ]

    def _get_context_window(self, model_id: str) -> int:
        """Get context window for a model."""
        if "ultra" in model_id.lower():
            return 128000
        if "super" in model_id.lower():
            return 128000
        if "70b" in model_id.lower():
            return 128000
        if "nano" in model_id.lower():
            return 128000
        return 4096

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
        payload = {
            "model": model,
            "messages": [self._to_api_message(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        response = await self.client.post(
            "/chat/completions",
            headers=self.config.get_headers(),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return self._parse_response(data, model)

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
        payload = {
            "model": model,
            "messages": [self._to_api_message(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        async with self.client.stream(
            "POST",
            "/chat/completions",
            headers=self.config.get_headers(),
            json=payload,
        ) as response:
            response.raise_for_status()
            async for chunk in decode_chat_stream(response.aiter_lines(), model):
                yield chunk

    def _to_api_message(self, msg: ChatMessage) -> dict[str, Any]:
        """Convert internal message to API format."""
        api_msg = {"role": msg.role}
        if msg.content:
            api_msg["content"] = msg.content
        if msg.name:
            api_msg["name"] = msg.name
        if msg.tool_call_id:
            api_msg["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            api_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        return api_msg

    def _parse_response(self, data: dict, model: str) -> CompletionResponse:
        """Parse API response."""
        choice = data["choices"][0]
        msg = choice.get("message", {})
        return CompletionResponse(
            content=msg.get("content"),
            tool_calls=self._parse_tool_calls(msg.get("tool_calls")),
            model=model,
            reported_model=data.get("model") if isinstance(data.get("model"), str) else None,
            usage=data.get("usage"),
            finish_reason=choice.get("finish_reason"),
        )

    def _parse_tool_calls(self, tool_calls: list[dict] | None) -> list[ToolCall] | None:
        """Parse tool calls from API response."""
        if not tool_calls:
            return None
        return [
            ToolCall(
                id=tc["id"],
                type=tc["type"],
                function=ToolFunction(
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                ),
            )
            for tc in tool_calls
        ]

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
