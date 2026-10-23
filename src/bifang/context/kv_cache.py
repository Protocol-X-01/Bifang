from __future__ import annotations

import asyncio
import json
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from collections import OrderedDict

from .kv_store import KVStore, KVEntry
from ..config import Config


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    turn_id: str
    session_id: str
    user_message: str
    assistant_response: str
    timestamp: float
    metadata: dict = field(default_factory=dict)


@dataclass
class ConversationSession:
    """A conversation session with full history."""
    session_id: str
    created_at: float
    updated_at: float
    turns: list[ConversationTurn] = field(default_factory=list)
    summary: str = ""
    metadata: dict = field(default_factory=dict)


class ConversationKVCache:
    """Conversation-level KV cache with persistence across turns and sessions."""
    
    def __init__(
        self,
        storage_path: Path,
        max_entries: int = 10000,
        max_session_age_days: int = 30,
    ):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.max_session_age = max_session_age_days * 24 * 3600
        
        # In-memory cache with LRU eviction
        self._sessions: OrderedDict[str, ConversationSession] = OrderedDict()
        self._turn_index: dict[str, list[str]] = {}  # session_id -> turn_ids
        self._loaded = False
    
    async def load(self):
        """Load cache from disk."""
        if self._loaded:
            return
        
        sessions_file = self.storage_path / "sessions.json"
        if sessions_file.exists():
            try:
                with open(sessions_file) as f:
                    data = json.load(f)
                
                for session_data in data.get("sessions", []):
                    session = ConversationSession(
                        session_id=session_data["session_id"],
                        created_at=session_data["created_at"],
                        updated_at=session_data["updated_at"],
                        summary=session_data.get("summary", ""),
                        metadata=session_data.get("metadata", {}),
                    )
                    for turn_data in session_data.get("turns", []):
                        turn = ConversationTurn(
                            turn_id=turn_data["turn_id"],
                            session_id=turn_data["session_id"],
                            user_message=turn_data["user_message"],
                            assistant_response=turn_data["assistant_response"],
                            timestamp=turn_data["timestamp"],
                            metadata=turn_data.get("metadata", {}),
                        )
                        session.turns.append(turn)
                    
                    self._sessions[session.session_id] = session
                    self._turn_index[session.session_id] = [t.turn_id for t in session.turns]
                
                self._loaded = True
            except Exception as e:
                print(f"Failed to load conversation cache: {e}")
    
    async def save(self):
        """Save cache to disk."""
        sessions_file = self.storage_path / "sessions.json"
        sessions_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "saved_at": time.time(),
            "sessions": [],
        }
        
        for session in self._sessions.values():
            session_data = {
                "session_id": session.session_id,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "summary": session.summary,
                "metadata": session.metadata,
                "turns": [
                    {
                        "turn_id": turn.turn_id,
                        "session_id": turn.session_id,
                        "user_message": turn.user_message,
                        "assistant_response": turn.assistant_response,
                        "timestamp": turn.timestamp,
                        "metadata": turn.metadata,
                    }
                    for turn in session.turns
                ],
            }
            data["sessions"].append(session_data)
        
        # Atomic write
        tmp_file = sessions_file.with_suffix(".tmp")
        with open(tmp_file, "w") as f:
            json.dump(data, f)
        tmp_file.replace(sessions_file)
    
    def get_session(self, session_id: str) -> ConversationSession | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def create_session(self, session_id: str | None = None, metadata: dict | None = None) -> ConversationSession:
        """Create a new conversation session."""
        if session_id is None:
            session_id = f"session-{int(time.time() * 1000)}"
        
        session = ConversationSession(
            session_id=session_id,
            created_at=time.time(),
            updated_at=time.time(),
            metadata=metadata or {},
        )
        self._sessions[session_id] = session
        self._turn_index[session_id] = []
        
        # LRU eviction
        if len(self._sessions) > self.max_entries:
            oldest = next(iter(self._sessions))
            del self._sessions[oldest]
            self._turn_index.pop(oldest, None)
        
        return session
    
    def add_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        metadata: dict | None = None,
    ) -> str:
        """Add a turn to a session."""
        session = self._sessions.get(session_id)
        if not session:
            session = self.create_session(session_id)
        
        turn_id = f"turn-{int(time.time() * 1000000)}"
        turn = ConversationTurn(
            turn_id=turn_id,
            session_id=session_id,
            user_message=user_message,
            assistant_response=assistant_response,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        
        session.turns.append(turn)
        session.updated_at = time.time()
        self._turn_index[session_id].append(turn_id)
        
        # Keep only last 1000 turns per session
        if len(session.turns) > 1000:
            session.turns = session.turns[-1000:]
            self._turn_index[session_id] = self._turn_index[session_id][-1000:]
        
        return turn_id
    
    def get_recent_turns(self, session_id: str, count: int = 10) -> list[ConversationTurn]:
        """Get recent turns from a session."""
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session.turns[-count:]
    
    def get_turns_by_query(
        self,
        session_id: str,
        query: str,
        limit: int = 5,
    ) -> list[ConversationTurn]:
        """Get turns relevant to a query using simple text matching."""
        session = self._sessions.get(session_id)
        if not session:
            return []
        
        query_lower = query.lower()
        scored = []
        
        for turn in session.turns:
            score = 0
            # Score user message
            if query_lower in turn.user_message.lower():
                score += 3
            # Score assistant response
            if query_lower in turn.assistant_response.lower():
                score += 2
            # Check metadata
            for key, value in turn.metadata.items():
                if isinstance(value, str) and query_lower in value.lower():
                    score += 1
            
            if score > 0:
                scored.append((score, turn))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [turn for _, turn in scored[:limit]]
    
    def get_session_summary(self, session_id: str) -> str:
        """Get or generate a summary of the session."""
        session = self._sessions.get(session_id)
        if not session:
            return ""
        
        if session.summary:
            return session.summary
        
        # Generate simple summary from recent turns
        recent = session.turns[-5:]
        if not recent:
            return ""
        
        topics = set()
        for turn in recent:
            # Extract key terms from user message
            words = turn.user_message.lower().split()
            topics.update(w for w in words if len(w) > 4)
        
        summary = f"Session with {len(session.turns)} turns. Recent topics: {', '.join(sorted(topics)[:10])}"
        session.summary = summary
        return summary
    
    def prune_old_sessions(self):
        """Remove sessions older than max age."""
        now = time.time()
        cutoff = now - self.max_session_age
        
        to_remove = [
            sid for sid, session in self._sessions.items()
            if session.updated_at < cutoff
        ]
        
        for sid in to_remove:
            del self._sessions[sid]
            self._turn_index.pop(sid, None)


class ConversationCacheManager:
    """High-level manager for conversation caching with persistence."""
    
    def __init__(self, config: Config):
        self.config = config
        from ..config import state_home
        cache_path = state_home() / "conversation_cache"
        self.cache = ConversationKVCache(cache_path)
        self.current_session_id: str | None = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the cache."""
        if self._initialized:
            return
        await self.cache.load()
        self._initialized = True
    
    async def start_session(self, session_id: str | None = None, metadata: dict | None = None) -> str:
        """Start a new conversation session."""
        await self.initialize()
        session = self.cache.create_session(session_id, metadata)
        self.current_session_id = session.session_id
        return session.session_id
    
    def get_current_session_id(self) -> str | None:
        return self.current_session_id
    
    def get_current_session(self) -> "ConversationSession | None":
        if not self.current_session_id:
            return None
        return self.cache.get_session(self.current_session_id)
    
    def add_turn(
        self,
        user_message: str,
        assistant_response: str,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Add a turn to the current session."""
        session_id = session_id or self.current_session_id
        if not session_id:
            raise ValueError("No active session")
        
        return self.cache.add_turn(
            session_id=session_id,
            user_message=user_message,
            assistant_response=assistant_response,
            metadata=metadata,
        )
    
    def get_context_for_prompt(
        self,
        query: str,
        session_id: str | None = None,
        max_turns: int = 5,
        max_tokens: int = 4000,
    ) -> str:
        """Get relevant context from conversation history for a prompt."""
        session_id = session_id or self.current_session_id
        if not session_id:
            return ""
        
        # Get relevant turns
        relevant_turns = self.cache.get_turns_by_query(session_id, query, limit=max_turns)
        
        # Also get recent turns
        recent_turns = self.cache.get_recent_turns(session_id, count=max_turns)
        
        # Combine and deduplicate
        seen = set()
        combined = []
        for turn in relevant_turns + recent_turns:
            if turn.turn_id not in seen:
                seen.add(turn.turn_id)
                combined.append(turn)
        
        # Build context string
        context_parts = []
        token_count = 0
        
        for turn in reversed(combined[-max_turns:]):
            turn_text = f"User: {turn.user_message}\nAssistant: {turn.assistant_response}"
            turn_tokens = len(turn_text) // 4
            
            if token_count + turn_tokens > max_tokens:
                break
            
            context_parts.append(turn_text)
            token_count += turn_tokens
        
        return "\n\n---\n\n".join(reversed(context_parts))
    
    def get_session_summary(self, session_id: str | None = None) -> str:
        """Get session summary."""
        session_id = session_id or self.current_session_id
        if not session_id:
            return ""
        return self.cache.get_session_summary(session_id)
    
    async def end_session(self, session_id: str | None = None) -> str:
        """End current session and save."""
        session_id = session_id or self.current_session_id
        if session_id:
            session = self.cache.get_session(session_id)
            if session:
                session.updated_at = time.time()
        await self.cache.save()
        self.current_session_id = None
        return session_id or ""
    
    async def cleanup(self):
        """Cleanup old sessions and save."""
        await self.initialize()
        self.cache.prune_old_sessions()
        await self.cache.save()


def create_conversation_cache(config: Config) -> ConversationCacheManager:
    """Create a conversation cache manager."""
    return ConversationCacheManager(config)