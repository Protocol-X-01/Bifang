# Example plugin for Bifang
# Save this as ~/.config/bifang/plugins/web_search.py

from bifang.plugins import ToolPlugin, PluginMetadata


async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information."""
    # This is a placeholder - in reality you'd use a search API
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=10.0
            )
            data = response.json()
            abstract = data.get("Abstract", "")
            related = data.get("RelatedTopics", [])
            results = [abstract] if abstract else []
            for topic in related[:max_results]:
                if isinstance(topic, dict):
                    results.append(topic.get("Text", ""))
            return "\n".join(results) or "No results found"
    except Exception as e:
        return f"Search failed: {e}"


def create_plugin() -> ToolPlugin:
    """Create the web search plugin."""
    plugin = ToolPlugin(
        metadata=PluginMetadata(
            name="web_search",
            version="1.0.0",
            description="Web search capabilities using DuckDuckGo",
            author="Bifang Team",
        )
    )

    plugin.add_tool(
        "web_search",
        web_search,
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "description": "Maximum results", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        }
    )

    return plugin


# For direct module loading
PLUGIN = create_plugin()