from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from collections import OrderedDict


@dataclass
class KVEntry:
    """A key-value entry with metadata."""
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    ttl: float | None = None  # Time to live in seconds
    tags: list[str] = field(default_factory=list)


class KVStore:
    """Persistent key-value store with LRU eviction and TTL support."""
    
    def __init__(
        self,
        storage_path: Path,
        max_entries: int = 10000,
        default_ttl: float | None = None,
    ):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        
        # In-memory LRU cache
        self._cache: OrderedDict[str, KVEntry] = OrderedDict()
        self._loaded = False
    
    async def load(self):
        """Load store from disk."""
        if self._loaded:
            return
        
        store_file = self.storage_path / "kv_store.json"
        if store_file.exists():
            try:
                with open(store_file) as f:
                    data = json.load(f)
                
                for key, entry_data in data.items():
                    entry = KVEntry(
                        key=entry_data["key"],
                        value=entry_data["value"],
                        created_at=entry_data["created_at"],
                        updated_at=entry_data["updated_at"],
                        access_count=entry_data.get("access_count", 0),
                        ttl=entry_data.get("ttl"),
                        tags=entry_data.get("tags", []),
                    )
                    self._cache[key] = entry
                
                self._loaded = True
            except Exception as e:
                print(f"Failed to load KV store: {e}")
    
    async def save(self):
        """Save store to disk."""
        store_file = self.storage_path / "kv_store.json"
        store_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {}
        for key, entry in self._cache.items():
            data[key] = {
                "key": entry.key,
                "value": entry.value,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
                "access_count": entry.access_count,
                "ttl": entry.ttl,
                "tags": entry.tags,
            }
        
        # Atomic write
        tmp_file = store_file.with_suffix(".tmp")
        with open(tmp_file, "w") as f:
            json.dump(data, f)
        tmp_file.replace(store_file)
    
    def _is_expired(self, entry: KVEntry) -> bool:
        if entry.ttl is None:
            return False
        return time.time() - entry.created_at > entry.ttl
    
    def _evict_expired(self):
        """Remove expired entries."""
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.ttl is not None and (now - entry.created_at) > entry.ttl
        ]
        for key in expired_keys:
            del self._cache[key]
    
    def _evict_lru(self):
        """Evict least recently used entries if over capacity."""
        while len(self._cache) >= self.max_entries:
            self._cache.popitem(last=False)
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key."""
        await self.load()
        self._evict_expired()
        
        if key not in self._cache:
            return default
        
        entry = self._cache[key]
        if self._is_expired(entry):
            del self._cache[key]
            return default
        
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        entry.access_count += 1
        entry.updated_at = time.time()
        return entry.value
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Set a key-value pair."""
        await self.load()
        
        if key in self._cache:
            entry = self._cache[key]
            entry.value = value
            entry.updated_at = time.time()
            if ttl is not None:
                entry.ttl = ttl
            if tags is not None:
                entry.tags = tags
            self._cache.move_to_end(key)
        else:
            self._evict_lru()
            self._cache[key] = KVEntry(
                key=key,
                value=value,
                ttl=ttl or self.default_ttl,
                tags=tags or [],
            )
    
    async def delete(self, key: str) -> bool:
        """Delete a key."""
        await self.load()
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        await self.load()
        self._evict_expired()
        return key in self._cache
    
    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple keys."""
        result = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    async def set_many(self, items: dict[str, Any], ttl: float | None = None) -> None:
        """Set multiple key-value pairs."""
        for key, value in items.items():
            await self.set(key, value, ttl)
    
    def get_keys_by_tag(self, tag: str) -> list[str]:
        """Get all keys with a specific tag."""
        return [
            key for key, entry in self._cache.items()
            if tag in entry.tags
        ]
    
    async def delete_by_tag(self, tag: str) -> int:
        """Delete all entries with a tag."""
        await self.load()
        keys = self.get_keys_by_tag(tag)
        for key in keys:
            del self._cache[key]
        return len(keys)
    
    def get_stats(self) -> dict:
        """Get store statistics."""
        return {
            "entries": len(self._cache),
            "max_entries": self.max_entries,
            "utilization": len(self._cache) / self.max_entries,
        }
    
    async def clear(self):
        """Clear all entries."""
        self._cache.clear()
    
    async def close(self):
        """Close and save."""
        await self.save()