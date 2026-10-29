import asyncio
import builtins
import json
import os
import sqlite3
from types import SimpleNamespace

import httpx
import pytest

from bifang.agent import Agent
from bifang.config import Config
from bifang.memory import MemoryEntry, MemoryManager, MemoryStore, ProviderEmbedder
from bifang.memory.embedder import create_provider_embedder
from bifang.provider import ProviderManager
from bifang.providers.embeddings import validate_embedding
from bifang.providers.registry import ProviderRegistry
from bifang.providers.types import ProviderConfig
from bifang.routing import TieredProviderManager
from bifang.workspace import Workspace


def test_local_recall_is_ranked_token_search_and_survives_restart(tmp_path):
    path = tmp_path / "memory.db"

    async def scenario():
        store = MemoryStore(path)
        manager = MemoryManager(store)
        await manager.remember("Receipt parser preserves quotation marks and quoted CSV fields", id="parser")
        await manager.remember("GPU model deployment configuration", id="gpu")
        matches = await manager.recall("QUOTATION parser")
        assert [entry.id for entry in matches] == ["parser"]
        assert matches[0].access_count == 1
        assert matches[0].embedding is None
        store.close()
        store = MemoryStore(path)
        assert (await store.get("parser")).access_count == 1
        assert [entry.id for entry in await store.search_text("quoted CSV")] == ["parser"]
        store.close()

    asyncio.run(scenario())
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


def test_fts_tracks_updates_and_deletion_and_treats_queries_as_literals(tmp_path):
    async def scenario():
        store = MemoryStore(tmp_path / "memory.db")
        await store.add(MemoryEntry("item", "alpha parser"))
        assert len(await store.search_text("alpha")) == 1
        await store.add(MemoryEntry("item", "beta deployment"))
        assert await store.search_text("alpha") == []
        assert len(await store.search_text("beta")) == 1
        assert await store.search_text('" % * :') == []
        await store.search_text("OR NOT DROP TABLE memories")
        assert await store.delete("item") is True
        assert await store.delete("item") is False
        assert await store.search_text("beta") == []
        store.close()

    asyncio.run(scenario())


def test_legacy_memory_is_migrated_and_indexed_without_claiming_legacy_vectors(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("""
            CREATE TABLE memories (
                id TEXT PRIMARY KEY, content TEXT, metadata TEXT, embedding BLOB,
                created_at REAL, updated_at REAL, importance REAL, access_count INTEGER
            )
        """)
        connection.execute("INSERT INTO memories VALUES (?, ?, '{}', NULL, 1, 1, 1, 0)",
                           ("old", "retained receipt knowledge"))

    async def scenario():
        store = MemoryStore(path)
        assert (await store.get("old")).embedding_space is None
        assert [entry.id for entry in await store.search_text("receipt")] == ["old"]
        store.close()
        store = MemoryStore(path)
        assert len(await store.search_text("receipt")) == 1
        store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("vector", [[], [0, 0], [float("nan"), 1], [float("inf")],
                                   [True, 1], ["1", 0], "not a vector", [1.7e308, 1.7e308]])
def test_invalid_embeddings_are_rejected(vector):
    with pytest.raises(ValueError):
        validate_embedding(vector)


def test_vector_recall_needs_no_numpy_and_does_not_mix_embedding_spaces(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in ("numpy", "sqlite_vec"):
            raise AssertionError("Undeclared vector dependency imported")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    async def scenario():
        store = MemoryStore(tmp_path / "vectors.db")
        await store.add(MemoryEntry("a", "parser fact", embedding=[3, 4], embedding_space="model-a"))
        await store.add(MemoryEntry("b", "different model", embedding=[3, 4], embedding_space="model-b"))
        await store.add(MemoryEntry("old", "legacy vector", embedding=[3, 4]))
        results = await store.search([3, 4], embedding_space="model-a")
        assert [entry.id for entry in results] == ["a"]
        with pytest.raises(ValueError, match="dimension changed"):
            await store.search([1, 0, 0], embedding_space="model-a")
        with pytest.raises(ValueError, match="dimension changed"):
            await store.add(MemoryEntry("wrong", "wrong dimension", embedding=[1, 0, 0],
                                        embedding_space="model-a"))
        assert await store.get("wrong") is None
        store.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("provider_name,model", [
    ("nebius", "Qwen/test-embedding"),
    ("nvidia", "nvidia/test-embedding"),
    ("openai", "openai/test-embedding"),
])
def test_provider_embedding_http_and_document_query_modes(tmp_path, monkeypatch, provider_name, model):
    registry = ProviderRegistry()
    config = Config(default_provider=provider_name, providers={
        provider_name: ProviderConfig(provider_name, "test-key", "https://example.invalid/v1"),
    })
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.url.path == "/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-key"
        assert payload["model"] == model.removeprefix("openai/")
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.8, 0.6]}]})

    async def scenario():
        providers = ProviderManager(config, registry=registry)
        selected = registry.get(provider_name)
        await selected.client.aclose()
        selected.client = httpx.AsyncClient(transport=httpx.MockTransport(respond),
                                            base_url="https://example.invalid/v1")
        store = MemoryStore(tmp_path / "memory.db")
        try:
            embedder = await create_provider_embedder(providers, model, provider_name)
            manager = MemoryManager(store, embedder)
            await manager.remember("Quoted CSV parsing knowledge", id="fact")
            results = await manager.recall("How are fields quoted?")
            assert [entry.id for entry in results] == ["fact"]
            assert len(requests) == 2
            assert [request["input"] for request in requests] == [
                ["Quoted CSV parsing knowledge"], ["How are fields quoted?"],
            ]
            if provider_name == "nvidia":
                assert [request["input_type"] for request in requests] == ["passage", "query"]
            else:
                assert all("input_type" not in request for request in requests)
            assert (await store.get("fact")).embedding_space == embedder.embedding_space
        finally:
            store.close()
            await providers.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("status,payload,error", [
    (401, {"error": "denied"}, httpx.HTTPStatusError),
    (429, {"error": "limited"}, httpx.HTTPStatusError),
    (200, {"data": []}, ValueError),
    (200, {"data": [{"embedding": [0, 0]}]}, ValueError),
    (200, {"data": [{"embedding": [True]}]}, ValueError),
])
def test_embedding_failure_does_not_save_fake_memory(tmp_path, monkeypatch, status, payload, error):
    registry = ProviderRegistry()

    async def scenario():
        config = Config(providers={"nebius": ProviderConfig("nebius", "test-key")})
        provider = ProviderManager(config, registry=registry)
        selected = registry.get("nebius")
        await selected.client.aclose()
        selected.client = httpx.AsyncClient(base_url="https://example.invalid/v1",
            transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload)))
        store = MemoryStore(tmp_path / "memory.db")
        try:
            manager = MemoryManager(store, ProviderEmbedder(provider, "embedding-model", "nebius"))
            with pytest.raises(error):
                await manager.remember("synthetic fact")
            assert await store.get_recent() == []
        finally:
            store.close()
            await provider.close()

    asyncio.run(scenario())


def test_sync_and_async_custom_embedders(tmp_path):
    async def async_embed(text):
        await asyncio.sleep(0)
        return [1, 0]

    async def scenario():
        store = MemoryStore(tmp_path / "memory.db")
        with pytest.raises(ValueError, match="embedding_space"):
            MemoryManager(store, async_embed)
        for name, embedder in (("sync", lambda text: [1, 0]), ("async", async_embed)):
            manager = MemoryManager(store, embedder, embedding_space=name)
            await manager.remember("synthetic fact", id=name)
            assert [entry.id for entry in await manager.recall("query")] == [name]
        store.close()

    asyncio.run(scenario())


def test_default_agent_memory_is_project_scoped_and_uses_configured_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    async def scenario():
        source = tmp_path / "project"
        source.mkdir()
        agents = [
            Agent(Config(), Workspace(source, tmp_path / "worktree-one")),
            Agent(Config(), Workspace(source, tmp_path / "worktree-two")),
            Agent(Config(), Workspace(tmp_path / "other-project", tmp_path / "other-worktree")),
            Agent(Config(memory_db_path=str(tmp_path / "chosen.db")), Workspace(source, source)),
        ]
        try:
            first, same_project, other_project, custom = agents
            assert first.memory.embedder is None
            assert first.memory.store.db_path == same_project.memory.store.db_path
            assert first.memory.store.db_path != other_project.memory.store.db_path
            assert custom.memory.store.db_path == tmp_path / "chosen.db"
            await first.memory.remember("receipt parser fact")
            assert len(await same_project.memory.recall("receipt")) == 1
            assert await other_project.memory.recall("receipt") == []
        finally:
            for agent in agents:
                await agent.close()

    asyncio.run(scenario())


def test_embedding_identity_tracks_provider_model_and_endpoint():
    config = Config(providers={"nebius": ProviderConfig("nebius", base_url="https://one.invalid/v1")})
    manager = SimpleNamespace(cfg=config)
    original = ProviderEmbedder(manager, "model-a").embedding_space
    assert ProviderEmbedder(manager, "model-b").embedding_space != original
    config.providers["nebius"].base_url = "https://two.invalid/v1"
    assert ProviderEmbedder(manager, "model-a").embedding_space != original


def test_embedding_routing_does_not_infer_provider_from_model_prefix(monkeypatch):
    registry = ProviderRegistry()
    calls = []

    async def embed(text, model, purpose):
        calls.append((text, model, purpose))
        return [1, 0]

    registry.register(SimpleNamespace(name="nebius", embed=embed))
    registry.register(SimpleNamespace(name="unsupported"))
    base = ProviderManager(Config(default_provider="nvidia"), registry=registry)
    provider = TieredProviderManager(base, Config(default_provider="nvidia"))

    async def scenario():
        assert await provider.embed("query", "nvidia/embedding", provider="nebius",
                                    purpose="query") == [1, 0]
        with pytest.raises(ValueError, match="does not support embeddings"):
            await provider.embed("query", "model", provider="unsupported")
        with pytest.raises(ValueError, match="purpose"):
            await provider.embed("query", "model", provider="nebius", purpose="wrong")

    asyncio.run(scenario())
    assert calls == [("query", "nvidia/embedding", "query")]


def test_memory_context_skips_oversized_results_and_respects_empty_budget(tmp_path, monkeypatch):
    store = MemoryStore(tmp_path / "memory.db")
    manager = MemoryManager(store)
    calls = []

    async def recall(query, limit):
        calls.append(query)
        return [MemoryEntry("large", "x" * 10000), MemoryEntry("small", "use csv.reader")]

    monkeypatch.setattr(manager, "recall", recall)

    async def scenario():
        assert await manager.get_context("query", max_tokens=0) == ""
        assert calls == []
        context = await manager.get_context("query", max_tokens=20)
        assert context == "[Memory: use csv.reader]"
        assert (len(context) + 3) // 4 <= 20

    try:
        asyncio.run(scenario())
    finally:
        store.close()


def test_config_loads_explicit_embedding_settings(tmp_path, monkeypatch):
    env_file = tmp_path / "config.env"
    env_file.write_text("")
    monkeypatch.setenv("BIFANG_ENV_FILE", str(env_file))
    monkeypatch.setenv("BIFANG_MEMORY_EMBEDDING_PROVIDER", "nebius")
    monkeypatch.setenv("BIFANG_MEMORY_EMBEDDING_MODEL", "Qwen/embedding")
    monkeypatch.setenv("BIFANG_MEMORY_DB_PATH", str(tmp_path / "chosen.db"))
    config = Config.load()
    assert config.memory_embedding_provider == "nebius"
    assert config.memory_embedding_model == "Qwen/embedding"
    assert config.memory_db_path == str(tmp_path / "chosen.db")
