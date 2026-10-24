from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from .base import Plugin, PluginContext, PluginMetadata, ToolPlugin, SkillPlugin


class PluginManager:
    """Manages plugin loading and lifecycle."""

    def __init__(self, plugin_dirs: list[Path] | None = None):
        self.plugins: dict[str, Plugin] = {}
        self.context = PluginContext()
        self.plugin_dirs = plugin_dirs or [
            Path.cwd() / ".bifang" / "plugins",
            Path.home() / ".config" / "bifang" / "plugins",
        ]

    def register_plugin(self, plugin: Plugin) -> None:
        """Register a plugin instance."""
        if plugin.name in self.plugins:
            raise ValueError(f"Plugin already registered: {plugin.name}")
        self.plugins[plugin.name] = plugin

    def unregister_plugin(self, name: str) -> None:
        """Unregister a plugin."""
        self.plugins.pop(name, None)

    async def initialize_all(self) -> None:
        """Initialize all registered plugins."""
        for plugin in self.plugins.values():
            await plugin.initialize(self.context)

    async def shutdown_all(self) -> None:
        """Shutdown all plugins."""
        for plugin in self.plugins.values():
            await plugin.shutdown()

    def get_tool(self, name: str) -> Any | None:
        """Get a tool by name."""
        return self.context.tools.get(name)

    def get_skill(self, name: str) -> Any | None:
        """Get a skill by name."""
        return self.context.skills.get(name)

    def get_all_schemas(self) -> list[dict]:
        """Get all tool schemas."""
        return self.context.schemas

    async def load_from_directory(self, directory: Path) -> None:
        """Load plugins from a directory."""
        if not directory.exists():
            return

        for py_file in directory.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            await self.load_plugin_file(py_file)

    async def load_plugin_file(self, file_path: Path) -> None:
        """Load a single plugin file."""
        module_name = f"bifang_plugin_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)

            # Look for plugin classes or factory functions
            if hasattr(module, "create_plugin"):
                plugin = module.create_plugin()
                if isinstance(plugin, Plugin):
                    self.register_plugin(plugin)
            elif hasattr(module, "PLUGIN"):
                plugin = module.PLUGIN
                if isinstance(plugin, Plugin):
                    self.register_plugin(plugin)
            else:
                # Look for Plugin subclasses
                for name in dir(module):
                    obj = getattr(module, name)
                    if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                        plugin = obj()
                        self.register_plugin(plugin)

        except Exception as e:
            print(f"Failed to load plugin {file_path}: {e}")

    async def discover_and_load(self) -> None:
        """Discover and load plugins from all configured directories."""
        for directory in self.plugin_dirs:
            await self.load_from_directory(directory)

    async def load_entry_points(self) -> None:
        """Load plugins from entry points (setuptools)."""
        try:
            import importlib.metadata
            for entry_point in importlib.metadata.entry_points(group="bifang.plugins"):
                try:
                    plugin_factory = entry_point.load()
                    plugin = plugin_factory()
                    if isinstance(plugin, Plugin):
                        self.register_plugin(plugin)
                except Exception as e:
                    print(f"Failed to load entry point {entry_point.name}: {e}")
        except Exception:
            pass  # importlib.metadata not available or no entry points
