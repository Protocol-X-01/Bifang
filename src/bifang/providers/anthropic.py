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


class AnthropicProvider(Provider):
    """Anthropic provider (Claude models)."""

    @property
    def name(self) -> str:
        return "anthropic"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://api.anthropic.com/v1"
        self.client = httpx.AsyncClient(timeout=60.0, base_url=self.base_url)

    def get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key or "",
            "anthropic-version": "2023-06-01",
        }

    async def list_models(self) -> list[ModelInfo]:
        """Anthropic doesn't have a models endpoint, return known models."""
        return self._get_fallback_models()

    def _get_fallback_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="anthropic/claude-3-5-sonnet-20241022",
                name="Claude 3.5 Sonnet",
                provider=self.name,
                context_window=200000,
                supports_tools=True,
                supports_streaming=True,
                supports_vision=True,
            ),
            ModelInfo(
                id="anthropic/claude-3-5-haiku-20241022",
                name="Claude 3.5 Haiku",
                provider=self.name,
                context_window=200000,
                supports_tools=True,
                supports_streaming=True,
                supports_vision=True,
            ),
            ModelInfo(
                id="anthropic/claude-3-opus-20240229",
                name="Claude 3 Opus",
                provider=self.name,
                context_window=200000,
                supports_tools=True,
                supports_streaming=True,
                supports_vision=True,
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
            "model": model.replace("anthropic/", ""),
            "messages": [self._to_api_message(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = {"type": "auto"} if tool_choice == "auto" else tool_choice

        response = await self.client.post(
            "/messages",
            headers=self.get_headers(),
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
            "model": model.replace("anthropic/", ""),
            "messages": [self._to_api_message(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = {"type": "auto"} if tool_choice == "auto" else tool_choice

        async with self.client.stream(
            "POST",
            "/messages",
            headers=self.get_headers(),
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
                        if data.get("type") == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield CompletionResponse(
                                    content=delta.get("text"),
                                    model=model,
                                )
                    except Exception:
                        continue

    def _to_api_message(self, msg: ChatMessage) -> dict[str, Any]:
        """Convert to Anthropic format (no system role in messages)."""
        if msg.role == "system":
            return {"role": "user", "content": f"[System]: {msg.content}"}
        if msg.role == "tool":
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                ],
            }
        return {"role": msg.role, "content": msg.content or ""}

    def _parse_response(self, data: dict, model: str) -> CompletionResponse:
        content_blocks = data.get("content", [])
        text_parts = []
        tool_calls = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.get("id"),
                    type="function",
                    function=ToolFunction(
                        name=block.get("name"),
                        arguments=json.dumps(block.get("input", {})),
                    ),
                ))
        return CompletionResponse(
            content="".join(text_parts) if text_parts else None,
            tool_calls=tool_calls if tool_calls else None,
            model=model,
            usage=data.get("usage"),
            finish_reason=data.get("stop_reason"),
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