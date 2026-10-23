from __future__ import annotations

import httpx
import json
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


class OpenRouterProvider(Provider):
    """OpenRouter provider (access to many models via single API)."""

    @property
    def name(self) -> str:
        return "openrouter"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://openrouter.ai/api/v1"
        self.client = httpx.AsyncClient(timeout=60.0, base_url=self.base_url)

    async def list_models(self) -> list[ModelInfo]:
        """List available OpenRouter models."""
        try:
            response = await self.client.get("/models", headers=self.config.get_headers())
            response.raise_for_status()
            data = response.json()
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                models.append(ModelInfo(
                    id=f"openrouter/{model_id}",
                    name=m.get("name", model_id),
                    provider=self.name,
                    context_window=m.get("context_length", 4096),
                    supports_tools=True,
                    supports_streaming=True,
                    supports_vision=m.get("architecture", {}).get("modality", "") == "image+text",
                    pricing_per_1k_input=m.get("pricing", {}).get("prompt"),
                    pricing_per_1k_output=m.get("pricing", {}).get("completion"),
                    metadata=m,
                ))
            return models
        except Exception:
            return self._get_fallback_models()

    def _get_fallback_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="openrouter/anthropic/claude-3.5-sonnet",
                name="Claude 3.5 Sonnet (OpenRouter)",
                provider=self.name,
                context_window=200000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="openrouter/openai/gpt-4o",
                name="GPT-4o (OpenRouter)",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="openrouter/meta-llama/llama-3.1-405b-instruct",
                name="Llama 3.1 405B (OpenRouter)",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="openrouter/nvidia/nemotron-3-ultra",
                name="Nemotron 3 Ultra (OpenRouter)",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
        ]

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
        payload = {
            "model": model.replace("openrouter/", ""),
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
        payload = {
            "model": model.replace("openrouter/", ""),
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
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        if "content" in delta or "tool_calls" in delta:
                            yield CompletionResponse(
                                content=delta.get("content"),
                                tool_calls=self._parse_tool_calls(delta.get("tool_calls")),
                                model=model,
                                finish_reason=data["choices"][0].get("finish_reason"),
                            )
                    except Exception:
                        continue

    def _to_api_message(self, msg: ChatMessage) -> dict[str, Any]:
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
        choice = data["choices"][0]
        msg = choice.get("message", {})
        return CompletionResponse(
            content=msg.get("content"),
            tool_calls=self._parse_tool_calls(msg.get("tool_calls")),
            model=model,
            usage=data.get("usage"),
            finish_reason=choice.get("finish_reason"),
        )

    def _parse_tool_calls(self, tool_calls: list[dict] | None) -> list[ToolCall] | None:
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
        await self.client.aclose()