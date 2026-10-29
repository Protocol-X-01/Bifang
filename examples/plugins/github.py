# Example plugin for Bifang - GitHub integration
# Save this as ~/.config/bifang/plugins/github.py

from bifang.plugins import ToolPlugin, PluginMetadata


async def github_list_repos(username: str) -> str:
    """List repositories for a GitHub user."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/users/{username}/repos",
                params={"per_page": 100, "sort": "updated"},
                timeout=10.0
            )
            repos = response.json()
            if isinstance(repos, list):
                lines = [f"{r['name']} - {r['description'] or 'No description'} ({r['html_url']})" for r in repos]
                return "\n".join(lines)
            return "Failed to fetch repositories"
    except Exception as e:
        return f"GitHub API error: {e}"


async def github_get_repo(owner: str, repo: str) -> str:
    """Get details about a GitHub repository."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                timeout=10.0
            )
            repo_data = response.json()
            if "name" in repo_data:
                return f"{repo_data['full_name']}\n{repo_data.get('description', 'No description')}\nStars: {repo_data.get('stargazers_count', 0)}\nLanguage: {repo_data.get('language', 'Unknown')}\nURL: {repo_data['html_url']}"
            return "Repository not found"
    except Exception as e:
        return f"GitHub API error: {e}"


async def github_search_repos(query: str, max_results: int = 10) -> str:
    """Search GitHub repositories."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "per_page": max_results, "sort": "stars"},
                timeout=10.0
            )
            data = response.json()
            items = data.get("items", [])
            lines = [f"{r['full_name']} - {r.get('description', 'No description')} (★{r['stargazers_count']})" for r in items]
            return "\n".join(lines) or "No repositories found"
    except Exception as e:
        return f"GitHub search error: {e}"


def create_plugin() -> ToolPlugin:
    """Create the GitHub plugin."""
    plugin = ToolPlugin(
        metadata=PluginMetadata(
            name="github",
            version="1.0.0",
            description="GitHub repository search and inspection",
            author="Bifang Team",
        )
    )

    plugin.add_tool(
        "github_list_repos",
        github_list_repos,
        {
            "type": "function",
            "function": {
                "name": "github_list_repos",
                "description": "List repositories for a GitHub user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string", "description": "GitHub username"},
                    },
                    "required": ["username"],
                },
            },
        }
    )

    plugin.add_tool(
        "github_get_repo",
        github_get_repo,
        {
            "type": "function",
            "function": {
                "name": "github_get_repo",
                "description": "Get details about a GitHub repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner"},
                        "repo": {"type": "string", "description": "Repository name"},
                    },
                    "required": ["owner", "repo"],
                },
            },
        }
    )

    plugin.add_tool(
        "github_search_repos",
        github_search_repos,
        {
            "type": "function",
            "function": {
                "name": "github_search_repos",
                "description": "Search GitHub repositories",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "description": "Maximum results", "default": 10},
                    },
                    "required": ["query"],
                },
            },
        }
    )

    return plugin


PLUGIN = create_plugin()