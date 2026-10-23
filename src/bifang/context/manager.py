from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import time
from typing import TYPE_CHECKING

from .summarizer import Summarizer, ContextSummary, create_summarizer
from .kv_cache import ConversationCacheManager, ConversationSession, ConversationTurn, create_conversation_cache
from ..config import Config

if TYPE_CHECKING:
    from ..provider import ProviderManager


@dataclass
class ContextWindow:
    """Represents the current context window."""
    messages: list[dict] = field(default_factory=list)
    max_tokens: int = 100000
    current_tokens: int = 0
    summaries: list[ContextSummary] = field(default_factory=list)

    def add_message(self, message: dict) -> None:
        self.messages.append(message)
        self.current_tokens += self._estimate_tokens(message.get("content", "") or "")
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                self.current_tokens += self._estimate_tokens(str(tc))

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


class ContextManager:
    """Manages context window with automatic summarization and persistent conversation cache."""

    def __init__(
        self,
        config: Config,
        provider: Optional["ProviderManager"] = None,
        summarizer: Optional[Summarizer] = None,
    ):
        self.config = config
        self.provider = provider
        self.window = ContextWindow(max_tokens=config.max_context_tokens)
        self.summarizer = summarizer or create_summarizer(
            provider,
            model=config.get_default_model(),
            provider_name=config.default_provider,
            prefer_llm=config.enable_summarization,
        )
        self.summarization_threshold = config.summarization_threshold
        self.total_summarized = 0

        # Conversation cache for persistent history
        self.conversation_cache = create_conversation_cache(config)
        self._current_session_id: str | None = None

    async def initialize(self):
        """Initialize the context manager and conversation cache."""
        await self.conversation_cache.initialize()

    async def start_session(self, session_id: str | None = None, metadata: dict | None = None) -> str:
        """Start a new conversation session."""
        session_id = await self.conversation_cache.start_session(session_id, metadata)
        return session_id

    def get_current_session_id(self) -> str | None:
        """Get the current session ID."""
        return self._current_session_id

    def add_message(self, message: dict) -> None:
        """Add a message to context and conversation cache."""
        self.window.add_message(message)
        
        # Also store in conversation cache if we have a session
        if self._current_session_id and message.get("role") in ("user", "assistant"):
            # We'll pair user/assistant messages in the tool calling logic
            pass

    def get_messages(self) -> list[dict]:
        """Get current messages."""
        return self.window.messages

    def should_summarize(self) -> bool:
        """Check if context should be summarized."""
        return (
            self.config.enable_summarization and
            self.window.current_tokens > self.window.max_tokens * self.summarization_threshold
        )

    async def maybe_summarize(self) -> bool:
        """Summarize if needed. Returns True if summarized."""
        if not self.should_summarize():
            return False

        summarized_messages, summary = await self.summarizer.summarize_messages(
            self.window.messages,
            self.window.max_tokens,
            keep_recent=10,
        )

        self.window.messages = summarized_messages
        self.window.current_tokens = sum(
            self.window._estimate_tokens(m.get("content", "") or "")
            for m in summarized_messages
        )
        self.window.summaries.append(summary)
        self.total_summarized += 1

        return True

    def get_stats(self) -> dict[str, Any]:
        """Get context statistics."""
        return {
            "current_tokens": self.window.current_tokens,
            "max_tokens": self.window.max_tokens,
            "utilization": self.window.current_tokens / self.window.max_tokens,
            "message_count": len(self.window.messages),
            "summaries_count": len(self.window.summaries),
            "total_summarized": self.total_summarized,
            "total_compressed_tokens": sum(s.original_tokens - s.tokens_estimate for s in self.window.summaries),
        }

    def clear(self) -> None:
        """Clear context window."""
        self.window = ContextWindow(max_tokens=self.window.max_tokens)

    def set_max_tokens(self, max_tokens: int) -> None:
        """Update max tokens."""
        self.window.max_tokens = max_tokens

    # Conversation cache methods
    async def start_conversation(self, session_id: str | None = None, metadata: dict | None = None) -> str:
        """Start a new conversation session."""
        return await self.conversation_cache.start_session(session_id, metadata)

    def end_conversation(self, session_id: str | None = None) -> str | None:
        """End current conversation session."""
        session_id = session_id or self._current_session_id
        if session_id:
            import asyncio
            asyncio.create_task(self.conversation_cache.end_session(session_id))
            return session_id
        return None

    def get_conversation_context(
        self,
        query: str,
        session_id: str | None = None,
        max_turns: int = 5,
        max_tokens: int = 4000,
    ) -> str:
        """Get relevant conversation context for a query."""
        session_id = session_id or self._current_session_id
        if not session_id:
            return ""
        
        return self.conversation_cache.get_context_for_prompt(
            query=query,
            session_id=session_id,
            max_turns=max_turns,
            max_tokens=max_tokens,
        )

    def add_conversation_turn(
        self,
        user_message: str,
        assistant_response: str,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Add a conversation turn to the cache."""
        session_id = session_id or self._current_session_id
        if not session_id:
            raise ValueError("No active conversation session")
        
        return self.conversation_cache.add_conversation_turn(
            user_message=user_message,
            assistant_response=assistant_response,
            session_id=session_id,
            metadata=metadata,
        )

    def get_session_summary(self, session_id: str | None = None) -> str:
        """Get session summary."""
        session_id = session_id or self._current_session_id
        if not session_id:
            return ""
        return self.conversation_cache.get_session_summary(session_id)

    def get_conversation_stats(self) -> dict:
        """Get conversation cache statistics."""
        session = self.conversation_cache.get_current_session()
        if not session:
            return {"active": False}
        
        return {
            "active": True,
            "session_id": session.session_id,
            "turn_count": len(session.turns),
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "summary": session.summary,
        }