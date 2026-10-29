import pytest

from bifang.mcp import MCPManager


def test_environment_server_mapping_becomes_an_executable_config():
    manager = MCPManager()
    manager.add_server({"name": "the-toolbox", "command": "/local/the-toolbox", "args": ["--db", "/local/index.db"]})
    configured = manager.configs["the-toolbox"]
    assert configured.command == "/local/the-toolbox"
    assert configured.args == ["--db", "/local/index.db"]


@pytest.mark.parametrize("override", [
    {"name": "ambiguous_server"}, {"name": ""}, {"command": ""},
    {"args": "--db index.db"}, {"transport": "sse"},
])
def test_invalid_mcp_config_fails_before_spawning(override):
    manager = MCPManager()
    with pytest.raises(ValueError):
        manager.add_server({"name": "the-toolbox", "command": "/local/the-toolbox", **override})
    assert not manager.configs and not manager.clients
