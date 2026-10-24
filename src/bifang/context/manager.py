from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..config import Config
from .kv_cache import create_conversation_cache
from .summarizer import ContextSummary, Summarizer, create_summarizer, estimate_message_tokens

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
        self.current_tokens += self.estimate_message_tokens(message)

    def estimate_message_tokens(self, message: dict) -> int:
        return estimate_message_tokens(message)

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


class ContextManager:
    """Manages context window with automatic summarization and persistent conversation cache."""

    def __init__(
        self,
        config: Config,
        provider: ProviderManager | None = None,
        summarizer: Summarizer | None = None,
        project_path: Path | None = None,
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
        self.conversation_cache = (create_conversation_cache(config, project_path)
                                   if config.enable_conversation_history else None)
        self._current_session_id: str | None = None
        self._pending_messages: list[dict] = []
        self._pending_snapshot: list[dict] = []
        self._track_messages = False

    async def initialize(self):
        """Initialize the context manager and conversation cache."""
        if self.conversation_cache:
            await self.conversation_cache.initialize()

    async def start_session(self, session_id: str | None = None, metadata: dict | None = None) -> str:
        """Start a new conversation session."""
        if not self.conversation_cache:
            raise ValueError("Conversation history is disabled")
        previous = self._current_session_id
        self.finish_pending("interrupted")
        identity = await self.conversation_cache.start_session(session_id, metadata)
        self._current_session_id = identity
        self._track_messages = True
        session = self.conversation_cache.get_current_session()
        if session.turns:
            self._restore_history(session.turns)
        elif previous and previous != identity:
            self._reset_messages([message for message in self.window.messages
                                  if message.get("role") == "system"])
        return identity

    def get_current_session_id(self) -> str | None:
        """Get the current session ID."""
        return self._current_session_id

    def add_message(self, message: dict) -> None:
        """Add a message to context and conversation cache."""
        if self._track_messages and message.get("role") == "user":
            if self._pending_messages:
                raise RuntimeError("A conversation turn is already pending")
            self._pending_snapshot = list(self.window.messages)
        self.window.add_message(message)
        if self._track_messages and (self._pending_messages or message.get("role") == "user"):
            self._pending_messages.append(copy.deepcopy(message))
            if message.get("role") == "assistant" and not message.get("tool_calls"):
                self.finish_pending("completed")

    def begin_request(self):
        self._track_messages = True

    def finish_pending(self, status: str):
        if not self._pending_messages:
            return
        messages = self._pending_messages
        if self.conversation_cache and self._current_session_id:
            response = (messages[-1].get("content") or "") if status == "completed" else ""
            self.conversation_cache.add_turn(
                messages[0].get("content") or "", response,
                metadata={"status": status, "messages": messages},
            )
        self._pending_messages = []
        self._pending_snapshot = []

    def abort_pending(self, status: str):
        snapshot = self._pending_snapshot
        was_pending = bool(self._pending_messages)
        try:
            self.finish_pending(status)
        finally:
            if was_pending:
                self._reset_messages(snapshot)
            self._pending_messages = []
            self._pending_snapshot = []

    def _reset_messages(self, messages: list[dict]):
        self.window.messages[:] = messages
        self.window.current_tokens = sum(estimate_message_tokens(message) for message in messages)

    def _restore_history(self, turns):
        messages = [message for message in self.window.messages if message.get("role") == "system"]
        for turn in turns:
            if turn.metadata.get("status", "completed") != "completed":
                continue
            saved = turn.metadata.get("messages") or [
                {"role": "user", "content": turn.user_message},
                {"role": "assistant", "content": turn.assistant_response},
            ]
            pending = set()
            for message in saved:
                role = message.get("role")
                if role == "assistant":
                    if pending:
                        raise ValueError("Stored conversation has unresolved tool calls")
                    pending = {call["id"] for call in message.get("tool_calls") or []}
                elif role == "tool":
                    identity = message.get("tool_call_id")
                    if identity not in pending:
                        raise ValueError("Stored conversation has an orphan tool result")
                    pending.remove(identity)
                elif role != "user" or pending:
                    raise ValueError("Stored conversation contains an invalid message sequence")
            if pending:
                raise ValueError("Stored conversation has unresolved tool calls")
            messages.extend(copy.deepcopy(saved))
        self._reset_messages(messages)

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
            max(1, int(self.window.max_tokens * self.summarization_threshold)),
            keep_recent=10,
        )

        compacted_tokens = sum(self.window.estimate_message_tokens(message)
                               for message in summarized_messages)
        if compacted_tokens >= self.window.current_tokens:
            return False

        self.window.messages[:] = summarized_messages
        self.window.current_tokens = compacted_tokens
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
        self.abort_pending("interrupted")
        self._reset_messages([message for message in self.window.messages
                              if message.get("role") == "system"])
        self.window.summaries.clear()
        self.total_summarized = 0

    def set_max_tokens(self, max_tokens: int) -> None:
        """Update max tokens."""
        self.window.max_tokens = max_tokens

    # Conversation cache methods
    async def start_conversation(self, session_id: str | None = None, metadata: dict | None = None) -> str:
        """Start a new conversation session."""
        return await self.start_session(session_id, metadata)

    async def end_conversation(self, session_id: str | None = None) -> str | None:
        """End current conversation session."""
        session_id = session_id or self._current_session_id
        if session_id and self.conversation_cache:
            if session_id == self._current_session_id:
                self.finish_pending("interrupted")
            await self.conversation_cache.end_session(session_id)
            if session_id == self._current_session_id:
                self._current_session_id = None
                self._track_messages = False
                self._reset_messages([message for message in self.window.messages
                                      if message.get("role") == "system"])
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
        if not session_id or not self.conversation_cache:
            raise ValueError("No active conversation session")
        
        return self.conversation_cache.add_turn(
            user_message=user_message,
            assistant_response=assistant_response,
            session_id=session_id,
            metadata=metadata,
        )

    def get_session_summary(self, session_id: str | None = None) -> str:
        """Get session summary."""
        session_id = session_id or self._current_session_id
        if not session_id or not self.conversation_cache:
            return ""
        return self.conversation_cache.get_session_summary(session_id)

    def get_conversation_stats(self) -> dict:
        """Get conversation cache statistics."""
        session = self.conversation_cache.get_current_session() if self.conversation_cache else None
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

    async def close(self):
        try:
            await self.end_conversation()
        finally:
            if self.conversation_cache:
                self.conversation_cache.close()
