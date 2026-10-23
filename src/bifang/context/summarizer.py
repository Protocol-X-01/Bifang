from __future__ import annotations

import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..provider import ProviderManager
from ..config import Config


@dataclass
class ContextSummary:
    """A summary of context."""
    content: str
    tokens_estimate: int
    original_tokens: int
    compression_ratio: float
    timestamp: float = time.time()
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Summarizer(ABC):
    """Abstract base for summarizers."""

    @abstractmethod
    async def summarize(self, text: str, max_tokens: int, **kwargs) -> ContextSummary:
        """Summarize text to fit within max_tokens."""
        pass

    @abstractmethod
    async def summarize_messages(
        self,
        messages: list[dict],
        max_tokens: int,
        **kwargs
    ) -> tuple[list[dict], ContextSummary]:
        """Summarize a list of messages, returning condensed messages + summary."""
        pass


class LLMSummarizer(Summarizer):
    """Summarizer using an LLM provider."""

    def __init__(self, provider: ProviderManager, model: str, provider_name: str = None):
        self.provider = provider
        self.model = model
        self.provider_name = provider_name

    async def summarize(self, text: str, max_tokens: int, **kwargs) -> ContextSummary:
        """Summarize text using LLM."""
        prompt = f"""Summarize the following text concisely while preserving key information, decisions, code changes, and technical details. Target: ~{max_tokens} tokens.

Text to summarize:
{text}

Summary:"""

        response = await self.provider.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            provider=self.provider_name,
            max_tokens=max_tokens,
            temperature=0.1,
        )

        summary_text = response.get("content", "")
        original_tokens = self._estimate_tokens(text)
        summary_tokens = self._estimate_tokens(summary_text)

        return ContextSummary(
            content=summary_text,
            tokens_estimate=summary_tokens,
            original_tokens=original_tokens,
            compression_ratio=summary_tokens / max(original_tokens, 1),
        )

    async def summarize_messages(
        self,
        messages: list[dict],
        max_tokens: int,
        **kwargs
    ) -> tuple[list[dict], ContextSummary]:
        """Summarize messages, keeping system prompt and recent messages intact."""
        if not messages:
            return messages, ContextSummary(content="", tokens_estimate=0, original_tokens=0, compression_ratio=1.0)

        # Keep system message
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        # If already under limit, return as-is
        total_tokens = sum(self._estimate_tokens(m.get("content", "") or "") for m in messages)
        if total_tokens <= max_tokens:
            return messages, ContextSummary(
                content="",
                tokens_estimate=total_tokens,
                original_tokens=total_tokens,
                compression_ratio=1.0,
            )

        # Summarize older messages, keep last N
        keep_recent = kwargs.get("keep_recent", 10)
        to_summarize = other_msgs[:-keep_recent] if len(other_msgs) > keep_recent else []
        to_keep = other_msgs[-keep_recent:] if len(other_msgs) > keep_recent else other_msgs

        if not to_summarize:
            return messages, ContextSummary(
                content="",
                tokens_estimate=total_tokens,
                original_tokens=total_tokens,
                compression_ratio=1.0,
            )

        # Convert to text for summarization
        text_parts = []
        for m in to_summarize:
            role = m.get("role", "unknown")
            content = m.get("content", "") or ""
            if m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    content += f"\n[Tool: {tc['function']['name']}]"
            text_parts.append(f"{role}: {content}")

        summary = await self.summarize("\n\n".join(text_parts), max_tokens // 2)

        # Create summary message
        summary_msg = {
            "role": "system",
            "content": f"[Previous context summary]: {summary.content}"
        }

        new_messages = system_msgs + [summary_msg] + to_keep
        new_tokens = sum(self._estimate_tokens(m.get("content", "") or "") for m in new_messages)

        return new_messages, ContextSummary(
            content=summary.content,
            tokens_estimate=new_tokens,
            original_tokens=total_tokens,
            compression_ratio=new_tokens / max(total_tokens, 1),
        )

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation."""
        return max(1, len(text) // 4)


class HeuristicSummarizer(Summarizer):
    """Fast heuristic-based summarizer (no LLM call)."""

    def __init__(self):
        pass

    async def summarize(self, text: str, max_tokens: int, **kwargs) -> ContextSummary:
        """Extract key lines using heuristics."""
        lines = text.split("\n")
        target_lines = max(1, max_tokens // 20)

        # Score lines by importance
        scored = []
        for i, line in enumerate(lines):
            score = 0
            lower = line.lower()
            # Boost important keywords
            for kw in ["error", "exception", "failed", "success", "fix", "patch", "diff",
                       "function", "class", "def ", "import", "return", "TODO", "FIXME"]:
                if kw in lower:
                    score += 5
            # Boost lines with code-like patterns
            if any(c in line for c in "{}[]()"):
                score += 2
            # Boost non-empty lines
            if line.strip():
                score += 1
            scored.append((score, i, line))

        # Sort by score and take top lines
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = sorted(scored[:target_lines], key=lambda x: x[1])
        summary_text = "\n".join(line for _, _, line in selected)

        original_tokens = self._estimate_tokens(text)
        summary_tokens = self._estimate_tokens(summary_text)

        return ContextSummary(
            content=summary_text,
            tokens_estimate=summary_tokens,
            original_tokens=original_tokens,
            compression_ratio=summary_tokens / max(original_tokens, 1),
        )

    async def summarize_messages(
        self,
        messages: list[dict],
        max_tokens: int,
        **kwargs
    ) -> tuple[list[dict], ContextSummary]:
        """Summarize messages heuristically."""
        if not messages:
            return messages, ContextSummary(content="", tokens_estimate=0, original_tokens=0, compression_ratio=1.0)

        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        total_tokens = sum(self._estimate_tokens(m.get("content", "") or "") for m in messages)
        if total_tokens <= max_tokens:
            return messages, ContextSummary(
                content="", tokens_estimate=total_tokens, original_tokens=total_tokens, compression_ratio=1.0
            )

        keep_recent = kwargs.get("keep_recent", 10)
        to_summarize = other_msgs[:-keep_recent] if len(other_msgs) > keep_recent else []
        to_keep = other_msgs[-keep_recent:] if len(other_msgs) > keep_recent else other_msgs

        if not to_summarize:
            return messages, ContextSummary(
                content="", tokens_estimate=total_tokens, original_tokens=total_tokens, compression_ratio=1.0
            )

        # Extract key info from summarized messages
        key_points = []
        for m in to_summarize:
            content = m.get("content", "") or ""
            role = m.get("role", "unknown")
            if m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    key_points.append(f"{role}: Called {tc['function']['name']}")
            elif content.strip():
                # Take first 200 chars
                key_points.append(f"{role}: {content[:200]}")

        summary_text = " | ".join(key_points[:50])
        summary_msg = {"role": "system", "content": f"[Summary]: {summary_text}"}

        new_messages = system_msgs + [summary_msg] + to_keep
        new_tokens = sum(self._estimate_tokens(m.get("content", "") or "") for m in new_messages)

        return new_messages, ContextSummary(
            content=summary_text,
            tokens_estimate=new_tokens,
            original_tokens=total_tokens,
            compression_ratio=new_tokens / max(total_tokens, 1),
        )

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


class HybridSummarizer(Summarizer):
    """Uses heuristic for fast, LLM for quality when needed."""

    def __init__(self, provider: ProviderManager, model: str, provider_name: str = None):
        self.llm = LLMSummarizer(provider, model, provider_name)
        self.heuristic = HeuristicSummarizer()
        self.llm_threshold = 10000  # Use LLM for >10k tokens

    async def summarize(self, text: str, max_tokens: int, **kwargs) -> ContextSummary:
        tokens = self.heuristic._estimate_tokens(text)
        if tokens > self.llm_threshold:
            return await self.llm.summarize(text, max_tokens, **kwargs)
        return await self.heuristic.summarize(text, max_tokens, **kwargs)

    async def summarize_messages(
        self,
        messages: list[dict],
        max_tokens: int,
        **kwargs
    ) -> tuple[list[dict], ContextSummary]:
        total_tokens = sum(self.heuristic._estimate_tokens(m.get("content", "") or "") for m in messages)
        if total_tokens > self.llm_threshold:
            return await self.llm.summarize_messages(messages, max_tokens, **kwargs)
        return await self.heuristic.summarize_messages(messages, max_tokens, **kwargs)


def create_summarizer(
    provider: ProviderManager | None,
    model: str | None = None,
    provider_name: str | None = None,
    prefer_llm: bool = True,
) -> Summarizer:
    """Create appropriate summarizer based on availability."""
    if provider and model and prefer_llm:
        return HybridSummarizer(provider, model, provider_name)
    return HeuristicSummarizer()