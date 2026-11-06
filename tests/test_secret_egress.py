import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bifang.agent import Agent
from bifang.config import Config
from bifang.memory import MemoryManager, MemoryStore
from bifang.policy import Policy
from bifang.providers.types import ProviderConfig
from bifang.secret_patterns import (
    is_sensitive_command_path,
    is_sensitive_workspace_path,
    redact_model_diff,
    redact_secrets,
)
from bifang.tools.builtin import (
    _directory_size_bytes,
    _run_bounded_package_download,
    _validated_package_requirements,
    code_execute,
)
from bifang.tools.commands import SandboxUnavailableError
from bifang.tools.files import list_files, read_file, search
from bifang.workspace import Workspace


@pytest.mark.parametrize("name", [
    "OPENAI_API_KEY", "NVIDIA_API_KEY", "NEBIUS_API_KEY", "AWS_SECRET_ACCESS_KEY",
    "HF_TOKEN", "client_secret",
])
def test_redacts_common_credential_assignments(name):
    secret = "synthetic-fixture-token-123456"
    redacted = redact_secrets(f'{name}="{secret}"')

    assert secret not in redacted
    assert "[REDACTED]" in redacted


@pytest.mark.parametrize(("value", "expected"), [
    (
        "DATABASE_URL=postgresql://fixture_user:short@db.example.invalid/app",
        "DATABASE_URL=postgresql://[REDACTED]@db.example.invalid/app",
    ),
    (
        "DATABASE_URL=mysql://app:p%40ss%3Aword@db.example.invalid/app",
        "DATABASE_URL=mysql://[REDACTED]@db.example.invalid/app",
    ),
    (
        "DATABASE_URL=postgresql://fixture_user:part@secret@db.example.invalid/app",
        "DATABASE_URL=postgresql://[REDACTED]@db.example.invalid/app",
    ),
    (
        r'DATABASE_URL="postgresql:\/\/fixture_user:pw@db.example.invalid/app"',
        r'DATABASE_URL="postgresql:\/\/[REDACTED]@db.example.invalid/app"',
    ),
    (
        "DATABASE_URL=postgresql://fixture_user%3Aencoded-pass@db.example.invalid/app",
        "DATABASE_URL=postgresql://[REDACTED]@db.example.invalid/app",
    ),
    (
        r'DATABASE_URL="postgresql://fixture_user\u003Aencoded-pass\u0040db.example.invalid/app"',
        'DATABASE_URL="postgresql://[REDACTED]@db.example.invalid/app"',
    ),
    (
        "CACHE_URL=redis://:x@cache.example.invalid:6379/0",
        "CACHE_URL=redis://[REDACTED]@cache.example.invalid:6379/0",
    ),
    (
        "JDBC_URL=jdbc:postgresql://fixture_user:pw@[2001:db8::1]:5432/app",
        "JDBC_URL=jdbc:postgresql://[REDACTED]@[2001:db8::1]:5432/app",
    ),
    (
        "DATABASE_URL=//fixture_user:pw@db.example.invalid/app",
        "DATABASE_URL=//[REDACTED]@db.example.invalid/app",
    ),
])
def test_redacts_uri_userinfo_credentials(value, expected):
    assert redact_secrets(value) == expected


@pytest.mark.parametrize("value", [
    "https://example.com:8443/api",
    "https://alice@example.com/path",
    "mailto:alice@example.com",
    "alice@example.com",
    "https://example.com/path?contact=alice:team@example.com#section",
    "https://example.com/path//alice:team@example.com",
])
def test_preserves_urls_without_uri_passwords(value):
    assert redact_secrets(value) == value


@pytest.mark.parametrize("secret", [
    "nvapi-" + "a" * 30,
    "tvly-" + "b" * 30,
    "glpat-" + "c" * 24,
    "xoxb-" + "d" * 20,
])
def test_redacts_common_bare_token_prefixes(secret):
    assert secret not in redact_secrets(f"credential: {secret}")


def test_sensitive_path_rules_allow_documented_env_examples():
    assert is_sensitive_workspace_path(".env")
    assert is_sensitive_workspace_path("config/.env.local")
    assert is_sensitive_workspace_path("secrets.env")
    assert is_sensitive_workspace_path("prod.env")
    assert is_sensitive_workspace_path("secrets.env/backup.txt")
    assert is_sensitive_workspace_path("secrets/backup.txt")
    assert is_sensitive_workspace_path(".aws/credentials")
    assert is_sensitive_workspace_path(".config/gcloud/credentials.db")
    assert is_sensitive_workspace_path("config/credentials.db")
    assert is_sensitive_workspace_path("deploy/private.pem")
    for example_name in (".env.example", ".env.sample", ".env.template", ".env.dist"):
        assert not is_sensitive_workspace_path(example_name)
        assert is_sensitive_workspace_path(f"{example_name}/private.txt")
    assert not is_sensitive_workspace_path("src/config.py")


def test_sandbox_command_path_rules_hide_private_state_and_keep_git_usable():
    assert is_sensitive_command_path(".bifang/sessions/chat.jsonl")
    assert is_sensitive_command_path(".env")
    assert is_sensitive_command_path(".git/.env")
    assert is_sensitive_command_path(".git-credentials")
    assert is_sensitive_command_path(".config/gcloud/credentials.db")
    assert not is_sensitive_command_path(".git/config")
    assert not is_sensitive_command_path(".env.example")


def test_diff_omits_sensitive_file_and_redacts_other_hunks():
    diff = (
        "diff --git a/.env b/.env\nindex 1..2\n--- a/.env\n+++ b/.env\n"
        "+OPENAI_API_KEY=synthetic-fixture-token-123456\n"
        "diff --git a/secrets.env b/secrets.env\nindex 1..2\n"
        "+NVIDIA_API_KEY=synthetic-fixture-token-123456\n"
        "diff --git a/settings.json b/settings.json\nindex 1..2\n"
        "+{\"NVIDIA_API_KEY\":\"synthetic-fixture-token-123456\"}\n"
        "+DATABASE_URL=postgresql://fixture_user:synthetic-uri-diff-password@db.example.invalid/app\n"
    )

    result = redact_model_diff(diff)
    assert "Sensitive file diff omitted" in result
    assert "OPENAI_API_KEY=synthetic-fixture-token-123456" not in result
    assert "NVIDIA_API_KEY=synthetic-fixture-token-123456" not in result
    assert "synthetic-fixture-token-123456" not in result
    assert "synthetic-uri-diff-password" not in result
    assert "postgresql://[REDACTED]@db.example.invalid/app" in result
    assert "[REDACTED]" in result


def test_read_file_blocks_sensitive_paths_and_redacts_values(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=synthetic-fixture-token-123456\n")
    (tmp_path / "secrets.env").write_text("NVIDIA_API_KEY=synthetic-fixture-token-123456\n")
    nested_example = tmp_path / ".env.example"
    nested_example.mkdir()
    (nested_example / "private.txt").write_text("synthetic-unmatched-private-fixture\n")
    (tmp_path / "settings.json").write_text(
        '{"NVIDIA_API_KEY":"synthetic-fixture-token-123456"}\n'
    )

    with pytest.raises(PermissionError):
        read_file(Policy(tmp_path), ".env")
    with pytest.raises(PermissionError):
        read_file(Policy(tmp_path), "secrets.env")
    with pytest.raises(PermissionError):
        read_file(Policy(tmp_path), ".env.example/private.txt")
    result = read_file(Policy(tmp_path), "settings.json")
    assert "synthetic-fixture-token-123456" not in result
    assert "[REDACTED]" in result


def test_read_file_and_search_redact_uri_userinfo_credentials(tmp_path, monkeypatch):
    secret = "synthetic-uri-password-246801"
    value = f'DATABASE_URL="postgresql://fixture_user:{secret}@db.example.invalid/app"'
    (tmp_path / "settings.toml").write_text(value + "\n")

    read_result = read_file(Policy(tmp_path), "settings.toml")
    assert secret not in read_result
    assert "postgresql://[REDACTED]@db.example.invalid/app" in read_result

    rg = shutil.which("rg")
    if rg:
        monkeypatch.setattr("bifang.tools.files.shutil.which", lambda _: rg)
        rg_result = search(tmp_path, "DATABASE_URL")
        assert secret not in rg_result
        assert "postgresql://[REDACTED]@db.example.invalid/app" in rg_result

    monkeypatch.setattr("bifang.tools.files.shutil.which", lambda _: None)
    fallback_result = search(tmp_path, "DATABASE_URL")
    assert secret not in fallback_result
    assert "postgresql://[REDACTED]@db.example.invalid/app" in fallback_result


def test_search_uses_explicit_workspace_and_filters_secret_paths(tmp_path, monkeypatch):
    (tmp_path / "settings.json").write_text("NVIDIA_API_KEY=synthetic-fixture-token-123456\n")
    (tmp_path / ".env").write_text("NVIDIA_API_KEY=synthetic-fixture-token-123456\n")
    (tmp_path / "secrets.env").write_text("NVIDIA_API_KEY=synthetic-fixture-token-123456\n")
    (tmp_path / "outside.txt").write_text("SYNTHETIC_SEARCH_MARKER\n")

    monkeypatch.setattr("bifang.tools.files.shutil.which", lambda _: None)
    result = search(tmp_path, "SYNTHETIC")

    assert "outside.txt:1:SYNTHETIC_SEARCH_MARKER" in result
    assert ".env" not in result
    assert "secrets.env" not in result
    assert "synthetic-fixture-token-123456" not in result


def test_file_list_and_search_redact_credentials_in_paths(tmp_path, monkeypatch):
    synthetic_credential = "sk-proj-" + "A" * 32
    path = tmp_path / f"{synthetic_credential}.txt"
    path.write_text("SYNTHETIC_PATH_MARKER\n")

    listed = list_files(tmp_path)
    assert synthetic_credential not in listed
    assert "[REDACTED].txt" in listed

    rg_binary = shutil.which("rg")
    monkeypatch.setattr("bifang.tools.files.shutil.which", lambda _: None)
    fallback_result = search(tmp_path, "SYNTHETIC_PATH_MARKER")
    assert synthetic_credential not in fallback_result
    assert "[REDACTED].txt:1:SYNTHETIC_PATH_MARKER" in fallback_result

    if rg_binary:
        monkeypatch.setattr("bifang.tools.files.shutil.which", lambda _: rg_binary)
        rg_result = search(tmp_path, "SYNTHETIC_PATH_MARKER")
        assert synthetic_credential not in rg_result
        assert "[REDACTED].txt:1:SYNTHETIC_PATH_MARKER" in rg_result


def test_search_rejects_empty_query(tmp_path):
    assert "Search query must" in search(tmp_path, "  ")


def test_agent_requires_one_chat_scoped_content_approval_and_redacts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "source.py").write_text("NVIDIA_API_KEY=synthetic-fixture-token-123456\n")
    prompts = []
    cfg = Config(
        approval_mode="manual",
        enable_memory=False,
        enable_conversation_history=False,
        providers={"nebius": ProviderConfig(
            "nebius", "synthetic-provider-key", base_url="https://api.tokenfactory.nebius.com/v1",
            default_model="fixture",
        )},
    )

    async def scenario():
        agent = Agent(cfg, Workspace(tmp_path, tmp_path), approve=lambda prompt: prompts.append(prompt) or True)
        try:
            listed = await agent.tool("list_files", {})
            first = await agent.tool("read_file", {"path": "source.py"})
            second = await agent.tool("search", {"query": "NVIDIA_API_KEY"})
            assert "source.py" in listed
            assert ".env" not in listed
            assert "synthetic-fixture-token-123456" not in listed + first + second
            assert first.count("[REDACTED]") == 1
            assert second.count("[REDACTED]") == 1
            assert len(prompts) == 1
            assert "api.tokenfactory.nebius.com" in prompts[0]
            assert "OPENAI_API_KEY=" not in prompts[0]
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_memory_results_require_chat_scoped_egress_approval_and_are_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    secret = "synthetic-memory-api-secret-963852"
    prompts = []

    async def recall(query, limit=5):
        return [SimpleNamespace(content=f"NVIDIA_API_KEY={secret}")]

    async def get_context(query, max_tokens=2000):
        return f"[Memory: NEBIUS_API_KEY={secret}]"

    async def scenario():
        agent = Agent(
            Config(approval_mode="manual", enable_memory=False, enable_conversation_history=False,
                   providers={"nebius": ProviderConfig(
                       "nebius", "synthetic-provider-key", base_url="https://api.tokenfactory.nebius.com/v1",
                       default_model="fixture",
                   )}),
            Workspace(tmp_path, tmp_path),
            approve=lambda prompt: prompts.append(prompt) or True,
        )
        agent.memory = SimpleNamespace(recall=recall, get_context=get_context,
                                       store=SimpleNamespace(close=lambda: None))
        try:
            recall_result = await agent.tool("memory_recall", {"query": "fixture"})
            context_result = await agent.tool("memory_context", {"query": "fixture"})
            assert secret not in recall_result + context_result
            assert recall_result.count("[REDACTED]") == 1
            assert context_result.count("[REDACTED]") == 1
            assert len(prompts) == 1
            assert "workspace content and saved memory content" in prompts[0]
            assert "memory results" in prompts[0]
            assert "api.tokenfactory.nebius.com" in prompts[0]
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_memory_egress_is_denied_without_chat_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    prompts = []

    async def unexpected_recall(*args, **kwargs):
        pytest.fail("Memory was accessed before content-sharing consent")

    async def scenario():
        agent = Agent(
            Config(approval_mode="manual", enable_memory=False, enable_conversation_history=False),
            Workspace(tmp_path, tmp_path),
            approve=lambda prompt: prompts.append(prompt) or False,
        )
        agent.memory = SimpleNamespace(recall=unexpected_recall, get_context=unexpected_recall,
                                       store=SimpleNamespace(close=lambda: None))
        try:
            result = await agent.tool("memory_recall", {"query": "fixture"})
            assert result == "DENIED: workspace-content sharing was not approved"
            assert len(prompts) == 1
            assert "saved memory" in prompts[0]
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("approved", [False, True])
def test_remote_memory_store_requires_endpoint_aware_consent(tmp_path, monkeypatch, approved):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    prompts, stored = [], []

    async def remember(content, **kwargs):
        stored.append(content)
        return "memory-fixture"

    async def scenario():
        cfg = Config(
            approval_mode="manual",
            enable_memory=False,
            enable_conversation_history=False,
            memory_embedding_model="fixture-embedding",
            memory_embedding_provider="nebius",
            providers={"nebius": ProviderConfig(
                "nebius", "synthetic-provider-key", base_url="https://embed.tokenfactory.example/v1",
                default_model="fixture",
            )},
        )
        agent = Agent(
            cfg,
            Workspace(tmp_path, tmp_path),
            approve=lambda prompt: prompts.append(prompt) or approved,
        )
        agent.memory = SimpleNamespace(
            embedder=object(),
            remember=remember,
            store=SimpleNamespace(close=lambda: None),
        )
        try:
            result = await agent.tool("memory_store", {"content": "synthetic workspace note"})
            assert len(prompts) == 1
            assert "embedding endpoint" in prompts[0]
            assert "embed.tokenfactory.example" in prompts[0]
            assert "synthetic workspace note" not in prompts[0]
            if approved:
                assert result == "Stored memory: memory-fixture"
                assert stored == ["synthetic workspace note"]
            else:
                assert result == "DENIED by user"
                assert stored == []
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_remote_memory_embedding_approval_does_not_authorize_workspace_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "source.py").write_text("print('synthetic fixture')\n")
    prompts, stored = [], []

    async def remember(content, **kwargs):
        stored.append(content)
        return "memory-fixture"

    async def scenario():
        cfg = Config(
            approval_mode="manual",
            enable_memory=False,
            enable_conversation_history=False,
            memory_embedding_model="fixture-embedding",
            memory_embedding_provider="nebius",
            providers={"nebius": ProviderConfig(
                "nebius", "synthetic-provider-key", base_url="https://embed.tokenfactory.example/v1",
                default_model="fixture",
            )},
        )
        agent = Agent(
            cfg,
            Workspace(tmp_path, tmp_path),
            approve=lambda prompt: prompts.append(prompt) or True,
        )
        agent.memory = SimpleNamespace(
            embedder=object(), remember=remember, store=SimpleNamespace(close=lambda: None),
        )
        try:
            assert (await agent.tool("memory_store", {"content": "synthetic workspace note"})).startswith("Stored")
            assert "synthetic fixture" in await agent.tool("read_file", {"path": "source.py"})
            assert stored == ["synthetic workspace note"]
            assert len(prompts) == 2
            assert "embedding endpoint" in prompts[0]
            assert "workspace content and saved memory content" in prompts[1]
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_memory_retrieval_query_embedding_has_separate_provider_scoped_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "source.py").write_text("print('synthetic fixture')\n")
    prompts, embedded_queries = [], []
    state = {"allow_embedding": False}

    class ProbeEmbedder:
        embedding_space = "synthetic-openai-endpoint-model"

        async def embed_document(self, text):
            return [1.0, 0.0]

        async def embed_query(self, text):
            embedded_queries.append(text)
            return [1.0, 0.0]

    def approve(prompt):
        prompts.append(prompt)
        if prompt.startswith("Allow workspace content"):
            return True
        return state["allow_embedding"]

    async def scenario():
        cfg = Config(
            approval_mode="manual",
            enable_memory=False,
            enable_conversation_history=False,
            default_provider="nebius",
            memory_embedding_model="fixture-embedding",
            memory_embedding_provider="openai",
            providers={
                "nebius": ProviderConfig(
                    "nebius", "synthetic-chat-key", base_url="https://chat.tokenfactory.example/v1",
                    default_model="fixture-chat",
                ),
                "openai": ProviderConfig(
                    "openai", "synthetic-embedding-key", base_url="https://embed.openai.example/v1",
                    default_model="fixture-embedding",
                ),
            },
        )
        agent = Agent(cfg, Workspace(tmp_path, tmp_path), approve=approve)
        agent.memory = MemoryManager(MemoryStore(tmp_path / "memory.db"), ProbeEmbedder())
        try:
            await agent.memory.remember("synthetic saved memory", id="fixture")
            assert "synthetic fixture" in await agent.tool("read_file", {"path": "source.py"})
            assert len(prompts) == 1
            assert "synthetic recall query" not in prompts[0]

            for name, parameter, value in (
                ("memory_recall", "limit", True),
                ("memory_recall", "limit", 1.5),
                ("memory_context", "max_tokens", True),
                ("memory_context", "max_tokens", 1.5),
            ):
                result = await agent.tool(name, {"query": "synthetic malformed query", parameter: value})
                assert result == f"DENIED: {name} {parameter} must be an integer"
                assert embedded_queries == []
                assert len(prompts) == 1

            denied = await agent.tool("memory_recall", {"query": "synthetic recall query"})
            assert denied == "DENIED: memory-query embedding was not approved"
            assert embedded_queries == []
            assert len(prompts) == 2
            assert "embed.openai.example" in prompts[1]
            assert "synthetic recall query" not in prompts[1]
            assert "does not approve sending retrieved memory results" in prompts[1]

            state["allow_embedding"] = True
            synthetic_key = "sk-proj-" + "A" * 40
            recalled = await agent.tool(
                "memory_recall", {"query": f"synthetic recall query {synthetic_key}"}
            )
            assert "synthetic saved memory" in recalled
            assert embedded_queries == ["synthetic recall query [REDACTED]"]
            assert synthetic_key not in embedded_queries[0]
            assert len(prompts) == 3
            assert "embed.openai.example" in prompts[2]

            context = await agent.tool("memory_context", {"query": "synthetic context query"})
            assert "synthetic saved memory" in context
            assert embedded_queries == [
                "synthetic recall query [REDACTED]", "synthetic context query"
            ]
            assert len(prompts) == 3
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("approved", [False, True])
def test_restored_conversation_asks_before_resending_prior_tool_results(
        tmp_path, monkeypatch, streaming, approved):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(Agent, "_ensure_services_started", lambda self: asyncio.sleep(0))
    marker = "synthetic-saved-workspace-result-2468013"
    saved_secret = "synthetic-saved-api-secret-975310"
    prompts, calls = [], []
    cfg = Config(enable_memory=False, enable_conversation_history=False,
                 providers={"nebius": ProviderConfig(
                     "nebius", "synthetic-provider-key", base_url="https://api.tokenfactory.nebius.com/v1",
                     default_model="fixture",
                 )})

    async def scenario():
        agent = Agent(cfg, Workspace(tmp_path, tmp_path),
                      approve=lambda prompt: prompts.append(prompt) or approved,
                      restored_conversation=True)
        agent.context.add_message({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "prior-read", "type": "function", "function": {
                "name": "read_file", "arguments": '{"path":"source.py"}',
            }}],
        })
        agent.context.add_message({
            "role": "tool", "tool_call_id": "prior-read",
            "content": f"{marker}\nNVIDIA_API_KEY={saved_secret}",
        })

        async def complete(messages, **kwargs):
            calls.append(messages)
            return {"role": "assistant", "content": "continued"}

        async def complete_stream(messages, **kwargs):
            calls.append(messages)
            yield {"content": "continued", "finish_reason": "stop"}

        agent.provider.complete = complete
        agent.provider.complete_stream = complete_stream
        try:
            if streaming:
                result = "".join([part async for part in agent.ask_stream("Continue")])
            else:
                result = await agent.ask("Continue")
            if approved:
                assert result == "continued"
                assert len(calls) == 1
                tool_result = next(message for message in calls[0] if message.get("role") == "tool")
                assert marker in tool_result["content"]
                assert saved_secret not in tool_result["content"]
                assert "[REDACTED]" in tool_result["content"]
                assert len(prompts) == 1
                assert "saved conversation history" in prompts[0]
                assert marker not in prompts[0]
                (tmp_path / "source.py").write_text("print('synthetic fixture')\n")
                assert "synthetic fixture" in await agent.tool("read_file", {"path": "source.py"})
                assert len(prompts) == 2
                assert "workspace content and saved memory content" in prompts[1]
            else:
                assert result.startswith("DENIED:")
                assert calls == []
                assert len(prompts) == 1
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("approved", [False, True])
def test_legacy_restored_conversation_requires_consent_and_redacts_all_roles(
        tmp_path, monkeypatch, approved):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(Agent, "_ensure_services_started", lambda self: asyncio.sleep(0))
    secret = "synthetic-legacy-api-secret-753159"
    marker = "legacy-workspace-summary"
    prompts, calls = [], []
    cfg = Config(enable_memory=False, enable_conversation_history=False,
                 providers={"nebius": ProviderConfig(
                     "nebius", "synthetic-provider-key", base_url="https://api.tokenfactory.nebius.com/v1",
                     default_model="fixture",
                 )})

    async def scenario():
        agent = Agent(cfg, Workspace(tmp_path, tmp_path),
                      approve=lambda prompt: prompts.append(prompt) or approved,
                      restored_conversation=True)
        agent.context.add_message({"role": "user", "content": f"Earlier note: {marker}; token={secret}"})
        agent.context.add_message({"role": "assistant", "content": f"Source excerpt: API_KEY={secret}"})

        async def complete(messages, **kwargs):
            calls.append(messages)
            return {"role": "assistant", "content": "continued"}

        agent.provider.complete = complete
        try:
            result = await agent.ask("Continue")
            if approved:
                assert result == "continued"
                assert len(calls) == 1
                restored_messages = calls[0]
                assert marker in str(restored_messages)
                assert secret not in str(restored_messages)
                assert "[REDACTED]" in str(restored_messages)
                assert len(prompts) == 1
                assert "user prompts, assistant replies" in prompts[0]
                assert "api.tokenfactory.nebius.com" in prompts[0]
            else:
                assert result.startswith("DENIED:")
                assert calls == []
                assert len(prompts) == 1
        finally:
            await agent.close()

    asyncio.run(scenario())


def test_restored_file_list_drops_sensitive_names():
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "list-1", "function": {
            "name": "list_files", "arguments": "{}",
        }}]},
        {"role": "tool", "tool_call_id": "list-1",
         "content": ".env\nsecrets.env\n.env.example\nsrc/main.py"},
    ]

    Agent._sanitize_restored_tool_history(messages)

    assert ".env\n" not in messages[1]["content"]
    assert "secrets.env" not in messages[1]["content"]
    assert ".env.example" in messages[1]["content"]
    assert "src/main.py" in messages[1]["content"]


def test_restored_read_and_search_results_drop_sensitive_paths():
    messages = [
        {"role": "assistant", "tool_calls": [
            {"id": "read-1", "function": {
                "name": "read_file", "arguments": '{"path":"secrets.env/backup.txt"}',
            }},
            {"id": "search-1", "function": {
                "name": "search", "arguments": '{"query":"SYNTHETIC"}',
            }},
        ]},
        {"role": "tool", "tool_call_id": "read-1",
         "content": "SYNTHETIC_SAVED_SECRET=synthetic-saved-secret-246801"},
        {"role": "tool", "tool_call_id": "search-1",
         "content": "secrets.env/backup.txt:1:SYNTHETIC_SAVED_SECRET\nsrc/main.py:4:SYNTHETIC_SAFE_MARKER"},
    ]

    Agent._sanitize_restored_tool_history(messages)

    assert "synthetic-saved-secret-246801" not in messages[1]["content"]
    assert "SYNTHETIC_SAVED_SECRET" not in messages[2]["content"]
    assert "src/main.py:4:SYNTHETIC_SAFE_MARKER" in messages[2]["content"]


def test_command_output_redacts_common_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    uri_secret = "synthetic-command-uri-password-135790"
    monkeypatch.setattr(
        "bifang.agent.run_command",
        lambda *args, **kwargs: asyncio.sleep(0, result={
            "returncode": 0,
            "stdout": (
                "NVIDIA_API_KEY=synthetic-fixture-token-123456\n"
                f"DATABASE_URL=postgresql://fixture_user:{uri_secret}@db.example.invalid/app\n"
            ),
            "stderr": "",
        }),
    )

    async def scenario():
        agent = Agent(Config(approval_mode="manual", enable_memory=False,
                            enable_conversation_history=False), Workspace(tmp_path, tmp_path),
                      approve=lambda _: True)
        try:
            result = json.loads(await agent.tool("run_command", {"command": "printf fixture"}))
            assert "synthetic-fixture-token-123456" not in result["stdout"]
            assert uri_secret not in result["stdout"]
            assert "postgresql://[REDACTED]@db.example.invalid/app" in result["stdout"]
            assert "[REDACTED]" in result["stdout"]
        finally:
            await agent.close()

    asyncio.run(scenario())


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="Bubblewrap is required for this isolation check")
def test_generated_python_cannot_read_a_host_file(tmp_path):
    marker = "synthetic-host-file-marker-7654321"
    outside = tmp_path / "outside-marker.txt"
    outside.write_text(marker)
    code = (
        "from pathlib import Path\n"
        f"try:\n    print(Path({str(outside)!r}).read_text())\n"
        "except OSError as error:\n    print(type(error).__name__)\n"
    )

    result = asyncio.run(code_execute(code))

    assert marker not in result
    assert "Error" in result


def test_generated_python_fails_closed_without_bubblewrap(monkeypatch):
    async def missing_sandbox(*args, **kwargs):
        raise SandboxUnavailableError("Synthetic missing Bubblewrap")

    monkeypatch.setattr("bifang.tools.builtin.shutil.which", lambda name: "/synthetic/bwrap")
    monkeypatch.setattr("bifang.tools.builtin.run_command", missing_sandbox)
    result = asyncio.run(code_execute("print('fixture')"))

    assert "No unsandboxed fallback" in result


def test_missing_bubblewrap_stops_before_package_download(monkeypatch):
    monkeypatch.setattr(
        "bifang.tools.builtin.shutil.which",
        lambda name, path=None: "/synthetic/python3" if name == "python3" else None,
    )
    monkeypatch.setattr("bifang.tools.builtin._run_bounded_package_download",
                        lambda *args, **kwargs: pytest.fail("Package download ran without Bubblewrap"))

    result = asyncio.run(code_execute("print('fixture')", packages=["sample==1.0"]))

    assert "Bubblewrap is missing" in result


def test_package_download_stops_when_sandbox_preflight_fails(monkeypatch):
    async def unavailable():
        return {"ready": False, "error": "Synthetic unsupported host"}

    monkeypatch.setattr("bifang.tools.builtin.shutil.which", lambda name, path=None: "/synthetic/bwrap")
    monkeypatch.setattr("bifang.sandbox_diagnostics.inspect_sandbox", unavailable)
    monkeypatch.setattr(
        "bifang.tools.builtin._run_bounded_package_download",
        lambda *args, **kwargs: pytest.fail("Package download ran without a working sandbox"),
    )

    result = asyncio.run(code_execute("print('fixture')", packages=["sample==1.0"]))

    assert "preflight failed" in result
    assert "no package download was run" in result


def test_generated_python_rejects_direct_package_urls():
    with pytest.raises(ValueError, match="Direct package URLs"):
        _validated_package_requirements(["sample @ https://example.invalid/sample.whl"])


def test_package_download_is_stopped_when_temporary_byte_budget_is_exceeded(tmp_path):
    download_dir = tmp_path / "package-download"
    download_dir.mkdir()
    max_bytes = 32 * 1024
    script = (
        "from pathlib import Path\n"
        "import sys, time\n"
        "target = Path(sys.argv[1]) / 'large.whl'\n"
        "with target.open('wb') as wheel:\n"
        "    for _ in range(1000):\n"
        "        wheel.write(b'x' * 4096)\n"
        "        wheel.flush()\n"
        "        time.sleep(0.001)\n"
    )

    completed, failure = _run_bounded_package_download(
        [sys.executable, "-c", script, str(download_dir)],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        download_dir=download_dir,
        max_bytes=max_bytes,
        timeout=5,
        poll_interval=0.005,
    )

    assert completed is None
    assert failure == "size"
    assert _directory_size_bytes(download_dir) <= max_bytes + 512 * 1024


def test_package_install_uses_the_same_python_as_the_isolated_runtime(tmp_path, monkeypatch):
    commands = []

    def download(argv, **kwargs):
        assert argv[0] == "/synthetic/bin/python3"
        destination = Path(argv[argv.index("--dest") + 1])
        (destination / "pip-1.0-py3-none-any.whl").write_bytes(b"wheel")
        (destination / "sample-1.0-py3-none-any.whl").write_bytes(b"wheel")
        return SimpleNamespace(returncode=0, stderr=""), None

    async def sandbox_run(policy, command, **kwargs):
        commands.append(command)
        return {"returncode": 0, "stdout": "fixture", "stderr": ""}

    monkeypatch.setattr("bifang.tools.builtin.shutil.which",
                        lambda name, path=None: "/synthetic/bin/python3")
    async def sandbox_ready():
        return {"ready": True}

    monkeypatch.setattr("bifang.sandbox_diagnostics.inspect_sandbox", sandbox_ready)
    monkeypatch.setattr("bifang.tools.builtin._run_bounded_package_download", download)
    monkeypatch.setattr("bifang.tools.builtin.run_command", sandbox_run)

    result = asyncio.run(code_execute("print('fixture')", packages=["sample==1.0"]))

    assert result == "fixture"
    assert commands[0].startswith(
        "PYTHONPATH=/workspace/package-download/wheelhouse/pip-1.0-py3-none-any.whl python3 -m pip install"
    )
    assert "--find-links=/workspace/package-download/wheelhouse" in commands[0]
    assert "--no-index" in commands[0]
    assert commands[1] == "PYTHONPATH=/workspace/site-packages python3 script.py"
