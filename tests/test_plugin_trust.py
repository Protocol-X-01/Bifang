import asyncio
import json
import stat
from types import SimpleNamespace

import pytest

from bifang.agent import Agent
from bifang.cli import amain
from bifang.config import Config
from bifang.plugins import PluginMetadata, SkillPlugin, ToolPlugin
from bifang.plugins.catalog import PluginCatalog
from bifang.plugins.manager import PluginManager
from bifang.workspace import Workspace

SOURCE = '''from pathlib import Path
from bifang.plugins import PluginMetadata, ToolPlugin
Path(__file__).with_suffix(".executed").write_text("executed")
async def respond():
    return "fixture reply"
def create_plugin():
    plugin = ToolPlugin(PluginMetadata("fixture", "1.0", "Fixture"))
    plugin.add_tool("read_file", respond, {"type": "function", "function": {
        "name": "read_file", "description": "Fixture", "parameters": {"type": "object", "properties": {}}}})
    return plugin
'''


@pytest.fixture
def fixture_plugin(tmp_path):
    directory = tmp_path / ".bifang/plugins"
    directory.mkdir(parents=True)
    manifest = directory / "fixture.plugin.json"
    manifest.write_text(json.dumps({"name": "fixture", "version": "1.0", "description": "Fixture",
                                    "capabilities": ["filesystem"]}))
    source = directory / "fixture.py"
    source.write_text(SOURCE)
    trust = tmp_path / "private/trust.json"
    manager = PluginManager([directory], trust)
    return manager, manifest, source


def test_discovery_and_untrusted_load_never_execute_repository_code(fixture_plugin):
    manager, _, source = fixture_plugin
    listing = manager.catalog.list()
    assert len(listing["plugins"]) == 1
    assert not listing["plugins"][0]["trusted"]
    asyncio.run(manager.discover_and_load())
    asyncio.run(manager.load_entry_points())
    assert not manager.plugins and not source.with_suffix(".executed").exists()
    with pytest.raises(PermissionError):
        asyncio.run(manager.load_plugin_file(source))
    assert not source.with_suffix(".executed").exists()


def test_exact_content_trust_exports_namespaced_tools_and_revocation_removes_them(fixture_plugin):
    manager, _, source = fixture_plugin
    candidate = manager.catalog.discover()[0][0]
    manager.catalog.enable(candidate.identity, candidate.sha256)
    assert stat.S_IMODE(manager.catalog.trust_path.stat().st_mode) == 0o600

    async def scenario():
        await manager.discover_and_load()
        assert source.with_suffix(".executed").exists()
        assert manager.get_tool("read_file") is None
        assert await manager.get_tool("plugin_fixture_read_file")() == "fixture reply"
        assert manager.get_all_schemas()[0]["function"]["name"] == "plugin_fixture_read_file"
        await manager.discover_and_load()
        assert len(manager.get_all_schemas()) == 1
        manager.catalog.disable(candidate.identity)
        assert manager.get_tool("plugin_fixture_read_file") is None
        assert manager.get_all_schemas() == []
        await manager.discover_and_load()
        assert not manager.plugins and not manager.context.tools
        await manager.shutdown_all()

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["source", "manifest"])
def test_changed_content_requires_fresh_trust(fixture_plugin, change):
    manager, manifest, source = fixture_plugin
    candidate = manager.catalog.discover()[0][0]
    manager.catalog.enable(candidate.identity, candidate.sha256)
    asyncio.run(manager.discover_and_load())
    if change == "source":
        source.write_text(SOURCE + "\nCHANGED = True\n")
    else:
        metadata = json.loads(manifest.read_text())
        metadata["description"] = "Changed"
        manifest.write_text(json.dumps(metadata))
    assert manager.get_tool("plugin_fixture_read_file") is None
    assert manager.catalog.list()["plugins"][0]["state"] == "changed"
    with pytest.raises(ValueError, match="changed"):
        manager.catalog.enable(candidate.identity, candidate.sha256)
    asyncio.run(manager.discover_and_load())
    assert not manager.plugins


@pytest.mark.parametrize("target", ["source", "manifest", "directory"])
def test_symlinked_plugin_paths_are_not_discovered(fixture_plugin, target):
    manager, manifest, source = fixture_plugin
    path = {"source": source, "manifest": manifest, "directory": source.parent}[target]
    moved = path.with_name(path.name + ".saved")
    path.rename(moved)
    path.symlink_to(moved, target_is_directory=target == "directory")
    assert manager.catalog.list()["plugins"] == []
    asyncio.run(manager.discover_and_load())
    assert not source.with_suffix(".executed").exists()


def test_missing_or_oversized_manifest_fails_without_import(fixture_plugin):
    manager, manifest, source = fixture_plugin
    manifest.unlink()
    asyncio.run(manager.discover_and_load())
    assert not source.with_suffix(".executed").exists()
    manifest.write_text("x" * 16001)
    assert manager.catalog.list()["errors"]


def test_trust_is_bound_to_origin_and_fail_closed_on_corrupt_storage(fixture_plugin, tmp_path):
    manager, manifest, source = fixture_plugin
    candidate = manager.catalog.discover()[0][0]
    other = tmp_path / "another"
    other.mkdir()
    (other / manifest.name).write_bytes(manifest.read_bytes())
    (other / source.name).write_bytes(source.read_bytes())
    manager.catalog.enable(candidate.identity, candidate.sha256)
    catalog = PluginCatalog([other], manager.catalog.trust_path)
    assert not catalog.list()["plugins"][0]["trusted"]
    manager.catalog.trust_path.write_text("invalid storage")
    with pytest.raises(ValueError):
        asyncio.run(manager.discover_and_load())


def test_plugin_dataclass_constructors_accept_metadata():
    metadata = PluginMetadata("fixture", "1.0", "Fixture")
    assert ToolPlugin(metadata).name == "fixture"
    assert SkillPlugin(metadata).name == "fixture"


def test_cli_trust_denial_and_changed_fingerprint_never_enable(fixture_plugin, tmp_path, monkeypatch):
    manager, _, source = fixture_plugin
    monkeypatch.setattr("bifang.cli.Config.load", lambda: Config())
    monkeypatch.setattr("bifang.plugins.catalog.state_home", lambda: tmp_path / "private")
    monkeypatch.setattr("bifang.plugins.catalog.plugin_directories", lambda project: manager.plugin_dirs)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    candidate = manager.catalog.discover()[0][0]
    arguments = SimpleNamespace(cmd="plugins", plugin_action="trust", workspace=str(tmp_path), provider=None,
                                plugin_id=candidate.identity, sha256=candidate.sha256, yes=False)
    asyncio.run(amain(arguments))
    assert not (tmp_path / "private/plugins/trust.json").exists()
    arguments.sha256 = "a" * 64
    with pytest.raises(ValueError, match="changed"):
        asyncio.run(amain(arguments))
    assert not source.with_suffix(".executed").exists()


def test_actual_agent_startup_uses_source_origin_and_preserves_tool_approval(fixture_plugin, tmp_path, monkeypatch):
    _, _, source = fixture_plugin
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    other_directory = tmp_path / "unrelated-cwd"
    other_directory.mkdir()
    monkeypatch.chdir(other_directory)

    async def scenario():
        agent = Agent(Config(enable_memory=False, enable_conversation_history=False),
                      Workspace(tmp_path, tmp_path), approve=lambda prompt: False)
        try:
            await agent._ensure_services_started()
            assert not source.with_suffix(".executed").exists()
            candidate = agent.plugins.catalog.discover()[0][0]
            agent.plugins.catalog.enable(candidate.identity, candidate.sha256)
            await agent._ensure_services_started()
            assert source.with_suffix(".executed").exists()
            assert await agent.tool("plugin_fixture_read_file", {}) == "DENIED by user"
            agent.approve = lambda prompt: True
            assert await agent.tool("plugin_fixture_read_file", {}) == "fixture reply"
            agent.plugins.catalog.disable(candidate.identity)
            assert agent.plugins.get_tool("plugin_fixture_read_file") is None
        finally:
            await agent.close()

    asyncio.run(scenario())
