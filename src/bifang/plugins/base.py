from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""
    name: str
    version: str
    description: str
    author: str = ""
    dependencies: list[str] = field(default_factory=list)
    entry_point: str | None = None


class Plugin(ABC):
    """Base class for all plugins."""

    def __init__(self, metadata: PluginMetadata):
        self.metadata = metadata

    @property
    def name(self) -> str:
        return self.metadata.name

    @abstractmethod
    async def initialize(self, context: "PluginContext") -> None:
        """Initialize the plugin with the given context."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the plugin."""
        pass


@dataclass
class ToolPlugin(Plugin):
    """A plugin that provides tools."""

    tools: dict[str, Callable] = field(default_factory=dict)
    schemas: list[dict] = field(default_factory=list)

    def add_tool(self, name: str, func: Callable, schema: dict) -> None:
        """Add a tool to this plugin."""
        self.tools[name] = func
        self.schemas.append(schema)

    async def initialize(self, context: "PluginContext") -> None:
        """Register tools with the context."""
        for name, func in self.tools.items():
            context.register_tool(name, func)
        for schema in self.schemas:
            context.register_schema(schema)

    async def shutdown(self) -> None:
        pass


@dataclass
class SkillPlugin(Plugin):
    """A plugin that provides skills (complex workflows)."""

    skills: dict[str, Callable] = field(default_factory=dict)

    def add_skill(self, name: str, func: Callable) -> None:
        """Add a skill to this plugin."""
        self.skills[name] = func

    async def initialize(self, context: "PluginContext") -> None:
        """Register skills with the context."""
        for name, func in self.skills.items():
            context.register_skill(name, func)

    async def shutdown(self) -> None:
        pass


class PluginContext:
    """Context provided to plugins during initialization."""

    def __init__(self):
        self.tools: dict[str, Callable] = {}
        self.schemas: list[dict] = []
        self.skills: dict[str, Callable] = {}
        self.config: dict[str, Any] = {}

    def register_tool(self, name: str, func: Callable) -> None:
        """Register a tool function."""
        self.tools[name] = func

    def register_schema(self, schema: dict) -> None:
        """Register a tool schema."""
        self.schemas.append(schema)

    def register_skill(self, name: str, func: Callable) -> None:
        """Register a skill function."""
        self.skills[name] = func

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.config.get(key, default)

    def set_config(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        self.config[key] = value
