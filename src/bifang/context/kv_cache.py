from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Config, state_home


@dataclass
class ConversationTurn:
    turn_id: str
    session_id: str
    user_message: str
    assistant_response: str
    timestamp: float
    metadata: dict = field(default_factory=dict)


@dataclass
class ConversationSession:
    session_id: str
    created_at: float
    updated_at: float
    turns: list[ConversationTurn] = field(default_factory=list)
    summary: str = ""
    metadata: dict = field(default_factory=dict)


class ConversationKVCache:
    """Durable conversation records, not inference-engine KV tensors."""

    def __init__(self, storage_path: Path, max_entries: int = 10000,
                 max_session_age_days: int = 30):
        self.storage_path = Path(storage_path).expanduser()
        self.max_entries = max_entries
        self.max_session_age = max_session_age_days * 86400
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self.storage_path.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = self.storage_path / "conversations.db"
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
            connection = sqlite3.connect(path, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY, created_at REAL NOT NULL,
                    updated_at REAL NOT NULL, metadata TEXT NOT NULL, summary TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    turn_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    user_message TEXT NOT NULL, assistant_response TEXT NOT NULL,
                    timestamp REAL NOT NULL, metadata TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS conversation_turn_order
                    ON conversation_turns(session_id, timestamp, turn_id);
            """)
            connection.commit()
            self._connection = connection
        return self._connection

    async def load(self):
        self._connect()

    async def save(self):
        self._connect().commit()

    def get_session(self, session_id: str) -> ConversationSession | None:
        connection = self._connect()
        row = connection.execute(
            "SELECT * FROM conversation_sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        turns = [ConversationTurn(
            turn_id=turn["turn_id"], session_id=turn["session_id"],
            user_message=turn["user_message"], assistant_response=turn["assistant_response"],
            timestamp=turn["timestamp"], metadata=json.loads(turn["metadata"]),
        ) for turn in connection.execute(
            "SELECT * FROM conversation_turns WHERE session_id=? ORDER BY timestamp, turn_id",
            (session_id,),
        )]
        return ConversationSession(
            session_id=row["session_id"], created_at=row["created_at"], updated_at=row["updated_at"],
            turns=turns, summary=row["summary"], metadata=json.loads(row["metadata"]),
        )

    def list_sessions(self) -> list[ConversationSession]:
        identifiers = self._connect().execute(
            "SELECT session_id FROM conversation_sessions ORDER BY updated_at DESC LIMIT ?",
            (self.max_entries,),
        ).fetchall()
        return [self.get_session(row[0]) for row in identifiers]

    def list_summaries(self, limit: int = 20, offset: int = 0) -> list[dict]:
        rows = self._connect().execute("""
            SELECT sessions.session_id AS conversation_id, sessions.created_at,
                   sessions.updated_at, count(turns.turn_id) AS turn_count
            FROM conversation_sessions AS sessions
            LEFT JOIN conversation_turns AS turns USING(session_id)
            GROUP BY sessions.session_id
            ORDER BY sessions.updated_at DESC, sessions.session_id
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return [dict(row) for row in rows]

    def create_session(self, session_id: str | None = None,
                       metadata: dict | None = None) -> ConversationSession:
        identity = session_id or uuid.uuid4().hex
        connection = self._connect()
        now = time.time()
        with connection:
            connection.execute(
                "INSERT INTO conversation_sessions VALUES (?, ?, ?, ?, '') "
                "ON CONFLICT(session_id) DO NOTHING",
                (identity, now, now, json.dumps(metadata or {})),
            )
        return self.get_session(identity)

    def add_turn(self, session_id: str, user_message: str, assistant_response: str,
                 metadata: dict | None = None) -> str:
        connection = self._connect()
        if connection.execute("SELECT 1 FROM conversation_sessions WHERE session_id=?",
                              (session_id,)).fetchone() is None:
            raise ValueError("Conversation session does not exist")
        identity = uuid.uuid4().hex
        now = time.time()
        with connection:
            connection.execute("INSERT INTO conversation_turns VALUES (?, ?, ?, ?, ?, ?)",
                               (identity, session_id, user_message, assistant_response, now,
                                json.dumps(metadata or {})))
            connection.execute(
                "UPDATE conversation_sessions SET updated_at=?, summary='' WHERE session_id=?",
                (now, session_id),
            )
        return identity

    def get_recent_turns(self, session_id: str, count: int = 10) -> list[ConversationTurn]:
        session = self.get_session(session_id)
        return session.turns[-count:] if session and count > 0 else []

    def get_turns_by_query(self, session_id: str, query: str,
                           limit: int = 5) -> list[ConversationTurn]:
        session = self.get_session(session_id)
        if not session or limit < 1:
            return []
        terms = set(re.findall(r"[^\W_]+", query.casefold()))
        scored = []
        for turn in session.turns:
            text = f"{turn.user_message} {turn.assistant_response}".casefold()
            words = set(re.findall(r"[^\W_]+", text))
            score = len(terms & words)
            if score:
                scored.append((score, turn.timestamp, turn))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [turn for _, _, turn in scored[:limit]]

    def get_session_summary(self, session_id: str) -> str:
        session = self.get_session(session_id)
        if not session or not session.turns:
            return ""
        words = set(re.findall(r"[^\W_]{5,}", " ".join(
            turn.user_message for turn in session.turns[-5:]
        ).casefold()))
        summary = f"Session with {len(session.turns)} turns. Recent topics: {', '.join(sorted(words)[:10])}"
        connection = self._connect()
        with connection:
            connection.execute("UPDATE conversation_sessions SET summary=? WHERE session_id=?",
                               (summary, session_id))
        return summary

    def prune_old_sessions(self):
        connection = self._connect()
        with connection:
            connection.execute("DELETE FROM conversation_sessions WHERE updated_at < ?",
                               (time.time() - self.max_session_age,))
            connection.execute(
                "DELETE FROM conversation_sessions WHERE session_id IN "
                "(SELECT session_id FROM conversation_sessions ORDER BY updated_at DESC "
                "LIMIT -1 OFFSET ?)", (self.max_entries,),
            )

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class ConversationCacheManager:
    def __init__(self, config: Config, project_path: Path | None = None):
        self.config = config
        identity = (hashlib.sha256(str(project_path.resolve()).encode()).hexdigest()[:24]
                    if project_path else "unscoped")
        cache_path = (Path(config.conversation_cache_path).expanduser()
                      if config.conversation_cache_path else state_home() / "conversations" / identity)
        self.cache = ConversationKVCache(cache_path)
        self.current_session_id: str | None = None
        self._initialized = False

    async def initialize(self):
        if not self._initialized:
            await self.cache.load()
            self._initialized = True

    async def start_session(self, session_id: str | None = None,
                            metadata: dict | None = None) -> str:
        await self.initialize()
        session = self.cache.create_session(session_id, metadata)
        self.current_session_id = session.session_id
        return session.session_id

    def get_current_session_id(self) -> str | None:
        return self.current_session_id

    def get_current_session(self) -> ConversationSession | None:
        return self.cache.get_session(self.current_session_id) if self.current_session_id else None

    def add_turn(self, user_message: str, assistant_response: str,
                 session_id: str | None = None, metadata: dict | None = None) -> str:
        identity = session_id or self.current_session_id
        if identity is None:
            raise ValueError("No active conversation session")
        return self.cache.add_turn(identity, user_message, assistant_response, metadata)

    def get_context_for_prompt(self, query: str, session_id: str | None = None,
                               max_turns: int = 5, max_tokens: int = 4000) -> str:
        identity = session_id or self.current_session_id
        if not identity or max_turns < 1 or max_tokens < 1:
            return ""
        ranked = self.cache.get_turns_by_query(identity, query, max_turns)
        recent = self.cache.get_recent_turns(identity, max_turns)
        selected = {turn.turn_id: turn for turn in ranked}
        for turn in reversed(recent):
            if len(selected) >= max_turns:
                break
            selected.setdefault(turn.turn_id, turn)
        parts = []
        remaining = max_tokens
        for turn in sorted(selected.values(), key=lambda item: item.timestamp):
            text = f"User: {turn.user_message}\nAssistant: {turn.assistant_response}"
            cost = (len(text) + 3) // 4 + (2 if parts else 0)
            if cost <= remaining:
                parts.append(text)
                remaining -= cost
        return "\n\n---\n\n".join(parts)

    def get_session_summary(self, session_id: str | None = None) -> str:
        identity = session_id or self.current_session_id
        return self.cache.get_session_summary(identity) if identity else ""

    async def end_session(self, session_id: str | None = None) -> str:
        identity = session_id or self.current_session_id
        await self.cache.save()
        if identity == self.current_session_id:
            self.current_session_id = None
        return identity or ""

    async def cleanup(self):
        await self.initialize()
        self.cache.prune_old_sessions()

    def close(self):
        self.cache.close()
        self._initialized = False
        self.current_session_id = None


def create_conversation_cache(config: Config,
                              project_path: Path | None = None) -> ConversationCacheManager:
    return ConversationCacheManager(config, project_path)
