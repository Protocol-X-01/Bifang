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
from .embeddings import request_embedding


class OpenAIProvider(Provider):
    """OpenAI provider (GPT models)."""

    @property
    def name(self) -> str:
        return "openai"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://api.openai.com/v1"
        self.client = httpx.AsyncClient(timeout=60.0, base_url=self.base_url)

    async def embed(self, text: str, model: str, purpose: str = "passage") -> list[float]:
        return await request_embedding(self.client, self.config, text, model.removeprefix("openai/"))

    async def list_models(self) -> list[ModelInfo]:
        """List available OpenAI models."""
        try:
            response = await self.client.get("/models", headers=self.config.get_headers())
            response.raise_for_status()
            data = response.json()
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                if any(x in model_id for x in ["gpt-4", "gpt-3.5", "o1", "o3"]):
                    models.append(ModelInfo(
                        id=f"openai/{model_id}",
                        name=model_id,
                        provider=self.name,
                        context_window=self._get_context_window(model_id),
                        supports_tools="gpt-4" in model_id or "o1" in model_id or "o3" in model_id,
                        supports_streaming=True,
                        supports_vision="gpt-4o" in model_id or "gpt-4-vision" in model_id,
                        metadata=m,
                    ))
            return models
        except Exception:
            return self._get_fallback_models()

    def _get_fallback_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="openai/gpt-4o",
                name="GPT-4o",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
                supports_vision=True,
            ),
            ModelInfo(
                id="openai/gpt-4o-mini",
                name="GPT-4o Mini",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
                supports_vision=True,
            ),
            ModelInfo(
                id="openai/o1-preview",
                name="o1 Preview",
                provider=self.name,
                context_window=128000,
                supports_tools=True,
                supports_streaming=True,
            ),
            ModelInfo(
                id="openai/gpt-3.5-turbo",
                name="GPT-3.5 Turbo",
                provider=self.name,
                context_window=16384,
                supports_tools=True,
                supports_streaming=True,
            ),
        ]

    def _get_context_window(self, model_id: str) -> int:
        if "gpt-4o" in model_id or "o1" in model_id or "o3" in model_id:
            return 128000
        if "gpt-4" in model_id:
            return 8192
        return 16384

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
            "model": model.replace("openai/", ""),
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
            "model": model.replace("openai/", ""),
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
