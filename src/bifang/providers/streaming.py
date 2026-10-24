from __future__ import annotations

import json
from collections.abc import AsyncIterator

from .base import CompletionResponse, ToolCall, ToolFunction


class StreamProtocolError(ValueError):
    pass


async def sse_data(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    pending = []
    length = 0
    async for line in lines:
        if not line:
            if pending:
                yield "\n".join(pending)
                pending, length = [], 0
        elif line.startswith("data:"):
            value = line[5:].removeprefix(" ")
            length += len(value)
            if length > 1_000_000:
                raise StreamProtocolError("Provider stream event exceeded the size limit")
            pending.append(value)
    if pending:
        yield "\n".join(pending)


def completed_calls(pending: dict[int, dict]) -> list[ToolCall]:
    calls = []
    identities = set()
    for _, item in sorted(pending.items()):
        if not item["id"] or not item["name"] or item["id"] in identities:
            raise StreamProtocolError("Provider returned incomplete or duplicate tool identities")
        try:
            arguments = json.loads(item["arguments"])
        except json.JSONDecodeError:
            raise StreamProtocolError("Provider returned incomplete tool arguments") from None
        if not isinstance(arguments, dict):
            raise StreamProtocolError("Tool arguments must be a JSON object")
        identities.add(item["id"])
        calls.append(ToolCall(id=item["id"], function=ToolFunction(
            name=item["name"], arguments=item["arguments"])))
    return calls


async def decode_chat_stream(lines: AsyncIterator[str], model: str) -> AsyncIterator[CompletionResponse]:
    pending = {}
    reported_model = None
    finished = False
    argument_length = 0
    text_length = 0
    async for payload in sse_data(lines):
        if payload == "[DONE]":
            if pending:
                yield CompletionResponse(model=model, reported_model=reported_model,
                                         tool_calls=completed_calls(pending), finish_reason="tool_calls")
            return
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            raise StreamProtocolError("Provider returned malformed stream JSON") from None
        if not isinstance(data, dict) or "error" in data:
            raise StreamProtocolError("Provider returned an invalid or error stream event")
        if isinstance(data.get("model"), str):
            reported_model = data["model"]
        usage = data.get("usage")
        if usage is not None:
            if not isinstance(usage, dict):
                raise StreamProtocolError("Provider returned invalid stream usage")
            usage = {key: value for key, value in usage.items()
                     if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                     and type(value) is int and value >= 0}
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise StreamProtocolError("Provider returned invalid stream choices")
        if not choices:
            if usage is not None:
                yield CompletionResponse(model=model, reported_model=reported_model, usage=usage)
            continue
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("index", 0) != 0:
            raise StreamProtocolError("Provider returned an unsupported stream choice")
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            raise StreamProtocolError("Provider returned an invalid stream delta")
        content = delta.get("content")
        fragments = delta.get("tool_calls") or []
        if finished and (content or fragments):
            raise StreamProtocolError("Provider sent content after finishing the response")
        if content is not None and not isinstance(content, str):
            raise StreamProtocolError("Provider returned invalid streamed content")
        if not isinstance(fragments, list):
            raise StreamProtocolError("Provider returned invalid tool fragments")
        for fragment in fragments:
            if not isinstance(fragment, dict):
                raise StreamProtocolError("Provider returned an invalid tool fragment")
            index = fragment.get("index")
            if type(index) is not int or not 0 <= index < 64:
                raise StreamProtocolError("Provider returned an invalid tool index")
            item = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
            function = fragment.get("function") or {}
            if not isinstance(function, dict) or fragment.get("type", "function") != "function":
                raise StreamProtocolError("Provider returned an unsupported tool fragment")
            for field, value in (("id", fragment.get("id")), ("name", function.get("name"))):
                if value is not None:
                    if not isinstance(value, str):
                        raise StreamProtocolError("Provider returned an invalid tool identity")
                    if value and item[field] and item[field] != value:
                        raise StreamProtocolError("Provider changed a streamed tool identity")
                    if value:
                        item[field] = value
            arguments = function.get("arguments")
            if arguments is not None:
                if not isinstance(arguments, str):
                    raise StreamProtocolError("Provider returned invalid tool arguments")
                argument_length += len(arguments)
                if argument_length > 1_000_000:
                    raise StreamProtocolError("Streamed tool arguments exceeded the size limit")
                item["arguments"] += arguments
        calls = None
        finish_reason = choice.get("finish_reason")
        if finish_reason is not None:
            if finish_reason not in {"stop", "tool_calls"}:
                raise StreamProtocolError("Provider response ended without a complete answer")
            if finish_reason == "tool_calls" and not pending:
                raise StreamProtocolError("Provider finished tool calls without any complete calls")
            calls = completed_calls(pending) if pending else None
            pending = {}
            finished = True
        if content:
            text_length += len(content)
            if text_length > 1_000_000:
                raise StreamProtocolError("Streamed content exceeded the size limit")
        if content is not None or calls or finish_reason or usage is not None:
            yield CompletionResponse(model=model, reported_model=reported_model, content=content,
                                     tool_calls=calls, finish_reason=finish_reason, usage=usage)
    if not finished:
        raise StreamProtocolError("Provider stream ended before completion")
