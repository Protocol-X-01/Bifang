from __future__ import annotations

import asyncio
import inspect
import json
import math
import os
import re
import sqlite3
import struct
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..providers.embeddings import validate_embedding
from .embedder import ProviderEmbedder, create_provider_embedder, create_simple_embedder


@dataclass
class MemoryEntry:
    """A memory entry."""
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    embedding_space: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    importance: float = 1.0
    access_count: int = 0


class MemoryStore:
    """Persistent memory store with vector search."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.db_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        # Create memories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                embedding BLOB,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                importance REAL NOT NULL DEFAULT 1.0,
                access_count INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Create index for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance)")

        columns = {row["name"] for row in cursor.execute("PRAGMA table_info(memories)")}
        if "embedding_space" not in columns:
            cursor.execute("ALTER TABLE memories ADD COLUMN embedding_space TEXT")
        has_index = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'memories_fts'"
        ).fetchone()
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content, content='memories', content_rowid='rowid'
            )
        """)
        cursor.executescript("""
            CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                VALUES ('delete', old.rowid, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE OF content ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                VALUES ('delete', old.rowid, old.content);
                INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
        """)
        if not has_index:
            cursor.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")

        conn.commit()

    async def add(self, entry: MemoryEntry) -> None:
        """Add a memory entry."""
        conn = self._get_connection()
        cursor = conn.cursor()

        embedding_blob = None
        if not entry.content.strip() or not math.isfinite(entry.importance):
            raise ValueError("Memory content must be nonempty and importance must be finite")
        if entry.embedding is not None:
            vector = validate_embedding(entry.embedding)
            norm = math.hypot(*vector)
            if not math.isfinite(norm):
                raise ValueError("Embedding norm is too large")
            existing = cursor.execute(
                "SELECT length(embedding) FROM memories WHERE embedding_space IS ? "
                "AND embedding IS NOT NULL AND id != ? LIMIT 1", (entry.embedding_space, entry.id)
            ).fetchone()
            if existing and existing[0] != len(vector) * 4:
                raise ValueError("Embedding dimension changed; re-index this embedding space")
            embedding_blob = struct.pack(f"{len(vector)}f", *(value / norm for value in vector))

        cursor.execute("""
            INSERT INTO memories (id, content, metadata, embedding, created_at, updated_at,
                                  importance, access_count, embedding_space)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET content=excluded.content, metadata=excluded.metadata,
                embedding=excluded.embedding, updated_at=excluded.updated_at,
                importance=excluded.importance, access_count=excluded.access_count,
                embedding_space=excluded.embedding_space
        """, (
            entry.id,
            entry.content,
            json.dumps(entry.metadata),
            embedding_blob,
            entry.created_at,
            entry.updated_at,
            entry.importance,
            entry.access_count,
            entry.embedding_space,
        ))

        conn.commit()

    async def get(self, id: str) -> MemoryEntry | None:
        """Get a memory entry by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM memories WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            return None

        return self._row_to_entry(row)

    async def search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        min_similarity: float = 0.7,
        embedding_space: str | None = None,
    ) -> list[MemoryEntry]:
        """Search memories by vector similarity."""
        vector = validate_embedding(query_embedding)
        if not math.isfinite(min_similarity) or not -1 <= min_similarity <= 1:
            raise ValueError("min_similarity must be between -1 and 1")
        if limit < 1:
            return []
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE embedding IS NOT NULL AND embedding_space IS ?",
                       (embedding_space,))
        norm = math.hypot(*vector)
        query = [value / norm for value in vector]
        results = []
        for row in cursor:
            entry = self._row_to_entry(row)
            if entry.embedding:
                if len(entry.embedding) != len(query):
                    raise ValueError("Embedding dimension changed; re-index this embedding space")
                stored = validate_embedding(entry.embedding)
                stored_norm = math.hypot(*stored)
                similarity = math.fsum(value * (component / stored_norm)
                                       for value, component in zip(query, stored))
                if similarity >= min_similarity:
                    results.append((similarity, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results[:limit]]

    async def search_text(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Rank literal query terms with SQLite FTS5; no embedding request."""
        terms = list(dict.fromkeys(re.findall(r"[^\W_]+", query.casefold())))[:32]
        if not terms or limit < 1:
            return []
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT memories.* FROM memories_fts
            JOIN memories ON memories.rowid = memories_fts.rowid
            WHERE memories_fts MATCH ?
            ORDER BY bm25(memories_fts), importance DESC, created_at DESC
            LIMIT ?
        """, (" OR ".join(f'"{term}"' for term in terms), limit))

        return [self._row_to_entry(row) for row in cursor.fetchall()]

    async def update(self, entry: MemoryEntry) -> None:
        """Update a memory entry."""
        entry.updated_at = time.time()
        entry.access_count += 1
        await self.add(entry)

    async def delete(self, id: str) -> bool:
        """Delete a memory entry."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM memories WHERE id = ?", (id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted

    async def mark_accessed(self, entries: list[MemoryEntry]) -> None:
        conn = self._get_connection()
        conn.executemany("UPDATE memories SET access_count = access_count + 1 WHERE id = ?",
                         [(entry.id,) for entry in entries])
        conn.commit()
        for entry in entries:
            entry.access_count += 1

    async def get_recent(self, limit: int = 10) -> list[MemoryEntry]:
        """Get recent memories."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,))
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    async def get_important(self, limit: int = 10) -> list[MemoryEntry]:
        """Get important memories."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM memories ORDER BY importance DESC, access_count DESC LIMIT ?", (limit,))
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """Convert a database row to a MemoryEntry."""
        embedding = None
        if row["embedding"]:
            n = len(row["embedding"]) // 4
            embedding = list(struct.unpack(f"{n}f", row["embedding"]))

        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            metadata=json.loads(row["metadata"] or "{}"),
            embedding=embedding,
            embedding_space=row["embedding_space"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            importance=row["importance"],
            access_count=row["access_count"],
        )

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


class MemoryManager:
    """High-level memory management for agents."""

    def __init__(self, store: MemoryStore,
                 embedder: Callable[[str], list[float] | Awaitable[list[float]]] | None = None,
                 embedding_space: str | None = None):
        self.store = store
        self.embedder = embedder
        self.embedding_space = embedding_space or getattr(embedder, "embedding_space", None)
        if embedder and not self.embedding_space:
            raise ValueError("A stable embedding_space is required for custom embedders")

    async def _embed(self, text: str, purpose: str) -> list[float]:
        operation = getattr(self.embedder, f"embed_{purpose}", self.embedder)
        if inspect.iscoroutinefunction(operation):
            result = await operation(text)
        else:
            result = await asyncio.to_thread(operation, text)
            if inspect.isawaitable(result):
                result = await result
        return validate_embedding(result)

    async def remember(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        importance: float = 1.0,
        id: str | None = None,
    ) -> str:
        """Store a memory."""
        import uuid
        memory_id = id or str(uuid.uuid4())

        if not content.strip():
            raise ValueError("Memory content must be nonempty")
        embedding = None
        if self.embedder:
            embedding = await self._embed(content, "document")

        entry = MemoryEntry(
            id=memory_id,
            content=content,
            metadata=metadata or {},
            embedding=embedding,
            embedding_space=self.embedding_space,
            importance=importance,
        )

        await self.store.add(entry)
        return memory_id

    async def recall(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.7,
    ) -> list[MemoryEntry]:
        """Recall relevant memories."""
        if not query.strip() or limit < 1:
            return []
        if self.embedder:
            query_embedding = await self._embed(query, "query")
            entries = await self.store.search(query_embedding, limit, min_similarity,
                                              embedding_space=self.embedding_space)
        else:
            entries = await self.store.search_text(query, limit)
        await self.store.mark_accessed(entries)
        return entries

    async def get_context(self, query: str, max_tokens: int = 2000) -> str:
        """Get relevant context for a query."""
        if max_tokens < 1:
            return ""
        memories = await self.recall(query, limit=10)

        # Build context string
        context_parts = []
        token_count = 0

        for mem in memories:
            mem_text = f"[Memory: {mem.content}]"
            # Rough token estimation
            mem_tokens = max(1, (len(mem_text) + 3) // 4)
            if token_count + mem_tokens > max_tokens:
                continue
            context_parts.append(mem_text)
            token_count += mem_tokens

        return "\n".join(context_parts)

    async def consolidate(self) -> None:
        """Consolidate memories (increase importance of frequently accessed)."""
        memories = await self.store.get_recent(limit=100)
        for mem in memories:
            if mem.access_count > 5:
                mem.importance = min(2.0, mem.importance + 0.1)
                await self.store.update(mem)


__all__ = [
    "MemoryEntry",
    "MemoryManager",
    "MemoryStore",
    "ProviderEmbedder",
    "create_provider_embedder",
    "create_simple_embedder",
]
