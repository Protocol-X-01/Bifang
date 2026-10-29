from __future__ import annotations

import copy
import inspect
import sys
import types
from pathlib import Path
from typing import Any

from .base import Plugin, PluginContext
from .catalog import PluginCandidate, PluginCatalog, plugin_directories


class PluginManager:
    def __init__(self, plugin_dirs: list[Path] | None = None, trust_path: Path | None = None):
        self.plugins: dict[str, Plugin] = {}
        self.context = PluginContext()
        self.plugin_dirs = plugin_dirs if plugin_dirs is not None else plugin_directories(Path.cwd())
        self.catalog = PluginCatalog(self.plugin_dirs, trust_path)
        self._loaded: dict[str, tuple[PluginCandidate, Plugin, PluginContext]] = {}
        self._owners: dict[str, str] = {}
        self.errors: list[dict] = []

    def register_plugin(self, plugin: Plugin) -> None:
        if plugin.name in self.plugins:
            raise ValueError(f"Plugin already registered: {plugin.name}")
        self.plugins[plugin.name] = plugin

    def unregister_plugin(self, name: str) -> None:
        if any(plugin.name == name for _, plugin, _ in self._loaded.values()):
            raise ValueError("Disable a file plugin through its catalog before removing it")
        self.plugins.pop(name, None)

    async def initialize_all(self) -> None:
        for plugin in self.plugins.values():
            if not any(loaded is plugin for _, loaded, _ in self._loaded.values()):
                await plugin.initialize(self.context)

    async def shutdown_all(self) -> None:
        try:
            for plugin in self.plugins.values():
                try:
                    await plugin.shutdown()
                except Exception:
                    self.errors.append({"plugin": plugin.name, "error": "Plugin shutdown failed"})
        finally:
            self.plugins.clear()
            self._loaded.clear()
            self._owners.clear()
            self.context = PluginContext()

    def _valid(self, identity: str) -> bool:
        try:
            current = self.catalog.select(identity)
            previous = self._loaded[identity][0]
            return current.sha256 == previous.sha256 and self.catalog.approved(current)
        except (OSError, ValueError, KeyError):
            return False

    def get_tool(self, name: str) -> Any | None:
        identity = self._owners.get(name)
        if identity is not None and not self._valid(identity):
            return None
        return self.context.tools.get(name)

    def get_skill(self, name: str) -> Any | None:
        identity = self._owners.get(name)
        if identity is not None and not self._valid(identity):
            return None
        return self.context.skills.get(name)

    def get_all_schemas(self) -> list[dict]:
        return [schema for schema in self.context.schemas
                if self.get_tool(schema.get("function", {}).get("name", "")) is not None]

    async def load_from_directory(self, directory: Path) -> None:
        if directory not in self.plugin_dirs:
            raise ValueError("Plugin directory is outside this catalog")
        await self.discover_and_load()

    async def load_plugin_file(self, file_path: Path) -> None:
        candidates, _ = self.catalog.discover()
        selected = [candidate for candidate in candidates if candidate.source_path == file_path.absolute()]
        if len(selected) != 1 or not self.catalog.approved(selected[0]):
            raise PermissionError("Review and explicitly trust this plugin before loading it")
        candidate = selected[0]
        if candidate.identity not in self._loaded:
            await self._load(candidate)

    async def _load(self, candidate: PluginCandidate) -> None:
        if not self.catalog.approved(candidate):
            return
        module_name = f"bifang_plugin_{candidate.identity}_{candidate.sha256[:12]}"
        module = types.ModuleType(module_name)
        module.__file__ = str(candidate.source_path)
        sys.modules[module_name] = module
        try:
            exec(compile(candidate.source, str(candidate.source_path), "exec", dont_inherit=True), module.__dict__)
            factory = getattr(module, "create_plugin", None)
            plugin = factory() if callable(factory) else getattr(module, "PLUGIN", None)
        finally:
            sys.modules.pop(module_name, None)
        if not isinstance(plugin, Plugin):
            raise TypeError("Plugin must expose create_plugin() or PLUGIN")
        if plugin.name != candidate.metadata["name"] or plugin.metadata.version != candidate.metadata["version"]:
            raise ValueError("Plugin metadata does not match the reviewed manifest")
        if plugin.name in self.plugins:
            raise ValueError("Plugin name is already loaded")
        context = PluginContext()
        try:
            await plugin.initialize(context)
            self._validate_context(context, candidate.metadata["name"])
            self._loaded[candidate.identity] = (candidate, plugin, context)
            self.plugins[plugin.name] = plugin
            self._rebuild()
        except BaseException:
            await plugin.shutdown()
            raise

    def _validate_context(self, context: PluginContext, plugin_name: str) -> None:
        if set(context.tools).intersection(context.skills):
            raise ValueError("Plugin tools and skills must have distinct names")
        for name, callback in {**context.tools, **context.skills}.items():
            if not isinstance(name, str) or not name.isascii() or not name.isidentifier() or len(f"plugin_{plugin_name}_{name}") > 64:
                raise ValueError("Plugin tool names must be bounded ASCII identifiers")
            if not inspect.iscoroutinefunction(callback):
                raise ValueError("Plugin tools and skills must be asynchronous")
        schema_names = [schema.get("function", {}).get("name") for schema in context.schemas]
        if len(schema_names) != len(set(schema_names)) or set(schema_names) != set(context.tools):
            raise ValueError("Every plugin tool requires one matching function schema")

    def _rebuild(self) -> None:
        old_names = set(self._owners)
        self.context.tools = {name: callback for name, callback in self.context.tools.items() if name not in old_names}
        self.context.skills = {name: callback for name, callback in self.context.skills.items() if name not in old_names}
        self.context.schemas = [schema for schema in self.context.schemas
                                if schema.get("function", {}).get("name") not in old_names]
        self._owners.clear()
        for identity, (candidate, _, context) in self._loaded.items():
            prefix = f"plugin_{candidate.metadata['name']}_"
            for name, callback in context.tools.items():
                self.context.tools[prefix + name] = callback
                self._owners[prefix + name] = identity
            for name, callback in context.skills.items():
                self.context.skills[prefix + name] = callback
                self._owners[prefix + name] = identity
            for schema in context.schemas:
                exported = copy.deepcopy(schema)
                exported["function"]["name"] = prefix + exported["function"]["name"]
                self.context.schemas.append(exported)

    async def discover_and_load(self) -> None:
        candidates, self.errors = self.catalog.discover()
        for identity, (_, plugin, _) in list(self._loaded.items()):
            if not self._valid(identity):
                self._loaded.pop(identity)
                self.plugins.pop(plugin.name, None)
                self._rebuild()
                try:
                    await plugin.shutdown()
                except Exception:
                    self.errors.append({"plugin": plugin.name, "error": "Plugin shutdown failed"})
        for candidate in candidates:
            if candidate.identity not in self._loaded and self.catalog.approved(candidate):
                try:
                    await self._load(candidate)
                except Exception:
                    self.errors.append({"id": candidate.identity, "error": "Plugin load failed; inspect trusted code locally"})

    async def load_entry_points(self) -> None:
        return None
