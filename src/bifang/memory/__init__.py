from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import sqlite_vec
    HAS_SQLITE_VEC = True
except ImportError:
    HAS_SQLITE_VEC = False

# Import embedder functions
from .embedder import create_simple_embedder, create_provider_embedder


@dataclass
class MemoryEntry:
    """A memory entry."""
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    importance: float = 1.0
    access_count: int = 0


class MemoryStore:
    """Persistent memory store with vector search."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            if HAS_SQLITE_VEC:
                self._conn.enable_load_extension(True)
                sqlite_vec.load(self._conn)
                self._conn.enable_load_extension(False)
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

        if HAS_SQLITE_VEC:
            # Create virtual table for vector search
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(
                    embedding FLOAT[1536]
                )
            """)

        conn.commit()

    async def add(self, entry: MemoryEntry) -> None:
        """Add a memory entry."""
        conn = self._get_connection()
        cursor = conn.cursor()

        import struct
        embedding_blob = None
        if entry.embedding:
            embedding_blob = struct.pack(f"{len(entry.embedding)}f", *entry.embedding)

        cursor.execute("""
            INSERT OR REPLACE INTO memories (id, content, metadata, embedding, created_at, updated_at, importance, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.id,
            entry.content,
            json.dumps(entry.metadata),
            embedding_blob,
            entry.created_at,
            entry.updated_at,
            entry.importance,
            entry.access_count,
        ))

        if HAS_SQLITE_VEC and entry.embedding:
            cursor.execute("INSERT INTO memories_vec (rowid, embedding) VALUES (?, ?)",
                         (entry.id, embedding_blob))

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
    ) -> list[MemoryEntry]:
        """Search memories by vector similarity."""
        if not HAS_SQLITE_VEC:
            return await self._search_fallback(query_embedding, limit, min_similarity)

        conn = self._get_connection()
        cursor = conn.cursor()

        import struct
        query_blob = struct.pack(f"{len(query_embedding)}f", *query_embedding)

        cursor.execute("""
            SELECT m.*, vec_distance_cosine(m.embedding, ?) as distance
            FROM memories m
            JOIN memories_vec v ON m.id = v.rowid
            WHERE vec_distance_cosine(m.embedding, ?) < ?
            ORDER BY distance ASC
            LIMIT ?
        """, (query_blob, query_blob, 1.0 - min_similarity, limit))

        rows = cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    async def _search_fallback(
        self,
        query_embedding: list[float],
        limit: int,
        min_similarity: float,
    ) -> list[MemoryEntry]:
        """Fallback search without sqlite-vec (load all and compute in Python)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM memories WHERE embedding IS NOT NULL")
        rows = cursor.fetchall()

        import numpy as np
        query_vec = np.array(query_embedding)
        results = []

        for row in rows:
            entry = self._row_to_entry(row)
            if entry.embedding:
                entry_vec = np.array(entry.embedding)
                similarity = np.dot(query_vec, entry_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(entry_vec))
                if similarity >= min_similarity:
                    results.append((similarity, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results[:limit]]

    async def search_text(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Search memories by text (SQLite FTS)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM memories
            WHERE content LIKE ?
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
        """, (f"%{query}%", limit))

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
        if HAS_SQLITE_VEC:
            cursor.execute("DELETE FROM memories_vec WHERE rowid = ?", (id,))

        conn.commit()
        return cursor.rowcount > 0

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
        import struct
        embedding = None
        if row["embedding"]:
            n = len(row["embedding"]) // 4
            embedding = list(struct.unpack(f"{n}f", row["embedding"]))

        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            metadata=json.loads(row["metadata"] or "{}"),
            embedding=embedding,
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

    def __init__(self, store: MemoryStore, embedder: Optional[Callable[[str], list[float]]] = None):
        self.store = store
        self.embedder = embedder

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

        embedding = None
        if self.embedder:
            embedding = await asyncio.to_thread(self.embedder, content)

        entry = MemoryEntry(
            id=memory_id,
            content=content,
            metadata=metadata or {},
            embedding=embedding,
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
        if self.embedder:
            query_embedding = await asyncio.to_thread(self.embedder, query)
            return await self.store.search(query_embedding, limit, min_similarity)
        else:
            return await self.store.search_text(query, limit)

    async def get_context(self, query: str, max_tokens: int = 2000) -> str:
        """Get relevant context for a query."""
        memories = await self.recall(query, limit=10)

        # Build context string
        context_parts = []
        token_count = 0

        for mem in memories:
            mem_text = f"[Memory: {mem.content}]"
            # Rough token estimation
            mem_tokens = len(mem_text) // 4
            if token_count + mem_tokens > max_tokens:
                break
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
    "MemoryStore",
    "MemoryEntry",
    "MemoryManager",
    "create_simple_embedder",
    "create_provider_embedder",
]