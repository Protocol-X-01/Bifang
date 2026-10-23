from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx


@dataclass
class GitHubRepo:
    """GitHub repository info."""
    owner: str
    name: str
    full_name: str
    url: str
    clone_url: str
    ssh_url: str
    default_branch: str
    description: str | None
    private: bool
    stars: int
    forks: int
    language: str | None
    updated_at: str


@dataclass
class GitHubIssue:
    """GitHub issue."""
    number: int
    title: str
    body: str | None
    state: str
    labels: list[str]
    assignees: list[str]
    created_at: str
    updated_at: str
    html_url: str
    comments: int


@dataclass
class GitHubPR:
    """GitHub pull request."""
    number: int
    title: str
    body: str | None
    state: str
    draft: bool
    head_ref: str
    base_ref: str
    head_sha: str
    base_sha: str
    user: str
    labels: list[str]
    created_at: str
    updated_at: str
    html_url: str
    additions: int
    deletions: int
    changed_files: int
    mergeable: bool | None
    merged: bool
    merged_at: str | None


@dataclass
class GitHubFile:
    """File in a GitHub repository."""
    path: str
    mode: str
    type: str
    sha: str
    size: int
    content: str | None = None


class GitHubClient:
    """GitHub API client."""
    
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.base_url = "https://api.github.com"
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers=self._get_headers(),
        )
    
    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any] | list[Any]:
        """Make a GitHub API request."""
        url = f"{self.base_url}{endpoint}"
        response = await self.client.request(method, url, **kwargs)
        
        if response.status_code == 401:
            raise PermissionError("GitHub authentication failed. Check GITHUB_TOKEN.")
        elif response.status_code == 403:
            raise PermissionError("GitHub API rate limit exceeded or access denied.")
        elif response.status_code == 404:
            raise FileNotFoundError(f"GitHub resource not found: {endpoint}")
        
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        return response.json()
    
    # Repository operations
    async def get_repo(self, owner: str, repo: str) -> GitHubRepo:
        data = await self._request("GET", f"/repos/{owner}/{repo}")
        return GitHubRepo(
            owner=data["owner"]["login"],
            name=data["name"],
            full_name=data["full_name"],
            url=data["html_url"],
            clone_url=data["clone_url"],
            ssh_url=data["ssh_url"],
            default_branch=data["default_branch"],
            description=data.get("description"),
            private=data["private"],
            stars=data["stargazers_count"],
            forks=data["forks_count"],
            language=data.get("language"),
            updated_at=data["updated_at"],
        )
    
    async def list_repos(self, owner: str | None = None, per_page: int = 30) -> list[GitHubRepo]:
        endpoint = f"/users/{owner}/repos" if owner else "/user/repos"
        data = await self._request("GET", endpoint, params={"per_page": per_page, "sort": "updated"})
        return [
            GitHubRepo(
                owner=r["owner"]["login"],
                name=r["name"],
                full_name=r["full_name"],
                url=r["html_url"],
                clone_url=r["clone_url"],
                ssh_url=r["ssh_url"],
                default_branch=r["default_branch"],
                description=r.get("description"),
                private=r["private"],
                stars=r["stargazers_count"],
                forks=r["forks_count"],
                language=r.get("language"),
                updated_at=r["updated_at"],
            )
            for r in data
        ]
    
    async def get_file(self, owner: str, repo: str, path: str, ref: str | None = None) -> GitHubFile:
        params = {"ref": ref} if ref else {}
        data = await self._request("GET", f"/repos/{owner}/{repo}/contents/{path}", params=params)
        
        if isinstance(data, list):
            raise ValueError(f"Path {path} is a directory, not a file")
        
        content = None
        if data.get("content"):
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        
        return GitHubFile(
            path=data["path"],
            mode=data["mode"],
            type=data["type"],
            sha=data["sha"],
            size=data["size"],
            content=content,
        )
    
    async def get_directory(self, owner: str, repo: str, path: str, ref: str | None = None) -> list[GitHubFile]:
        params = {"ref": ref} if ref else {}
        data = await self._request("GET", f"/repos/{owner}/{repo}/contents/{path}", params=params)
        
        if not isinstance(data, list):
            raise ValueError(f"Path {path} is not a directory")
        
        return [
            GitHubFile(
                path=item["path"],
                mode=item["mode"],
                type=item["type"],
                sha=item["sha"],
                size=item["size"],
            )
            for item in data
        ]
    
    # Issue operations
    async def list_issues(self, owner: str, repo: str, state: str = "open", labels: str | None = None, per_page: int = 30) -> list[GitHubIssue]:
        params = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = labels
        data = await self._request("GET", f"/repos/{owner}/{repo}/issues", params=params)
        return [
            GitHubIssue(
                number=i["number"],
                title=i["title"],
                body=i.get("body"),
                state=i["state"],
                labels=[l["name"] for l in i.get("labels", [])],
                assignees=[a["login"] for a in i.get("assignees", [])],
                created_at=i["created_at"],
                updated_at=i["updated_at"],
                html_url=i["html_url"],
                comments=i["comments"],
            )
            for i in data
            if "pull_request" not in i  # Exclude PRs
        ]
    
    async def get_issue(self, owner: str, repo: str, number: int) -> GitHubIssue:
        data = await self._request("GET", f"/repos/{owner}/{repo}/issues/{number}")
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            labels=[l["name"] for l in data.get("labels", [])],
            assignees=[a["login"] for a in data.get("assignees", [])],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            html_url=data["html_url"],
            comments=data["comments"],
        )
    
    async def create_issue(self, owner: str, repo: str, title: str, body: str | None = None, labels: list[str] | None = None, assignees: list[str] | None = None) -> GitHubIssue:
        data = await self._request("POST", f"/repos/{owner}/{repo}/issues", json={
            "title": title,
            "body": body,
            "labels": labels or [],
            "assignees": assignees or [],
        })
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            labels=[l["name"] for l in data.get("labels", [])],
            assignees=[a["login"] for a in data.get("assignees", [])],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            html_url=data["html_url"],
            comments=data["comments"],
        )
    
    async def update_issue(self, owner: str, repo: str, number: int, **kwargs) -> GitHubIssue:
        data = await self._request("PATCH", f"/repos/{owner}/{repo}/issues/{number}", json=kwargs)
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            labels=[l["name"] for l in data.get("labels", [])],
            assignees=[a["login"] for a in data.get("assignees", [])],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            html_url=data["html_url"],
            comments=data["comments"],
        )
    
    # PR operations
    async def list_prs(self, owner: str, repo: str, state: str = "open", per_page: int = 30) -> list[GitHubPR]:
        data = await self._request("GET", f"/repos/{owner}/{repo}/pulls", params={"state": state, "per_page": per_page, "sort": "updated"})
        return [
            GitHubPR(
                number=p["number"],
                title=p["title"],
                body=p.get("body"),
                state=p["state"],
                draft=p.get("draft", False),
                head_ref=p["head"]["ref"],
                base_ref=p["base"]["ref"],
                head_sha=p["head"]["sha"],
                base_sha=p["base"]["sha"],
                user=p["user"]["login"],
                labels=[l["name"] for l in p.get("labels", [])],
                created_at=p["created_at"],
                updated_at=p["updated_at"],
                html_url=p["html_url"],
                additions=p.get("additions", 0),
                deletions=p.get("deletions", 0),
                changed_files=p.get("changed_files", 0),
                mergeable=p.get("mergeable"),
                merged=p.get("merged", False),
                merged_at=p.get("merged_at"),
            )
            for p in data
        ]
    
    async def get_pr(self, owner: str, repo: str, number: int) -> GitHubPR:
        data = await self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
        return GitHubPR(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            draft=data.get("draft", False),
            head_ref=data["head"]["ref"],
            base_ref=data["base"]["ref"],
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            user=data["user"]["login"],
            labels=[l["name"] for l in data.get("labels", [])],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            html_url=data["html_url"],
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
            mergeable=data.get("mergeable"),
            merged=data.get("merged", False),
            merged_at=data.get("merged_at"),
        )
    
    async def get_pr_files(self, owner: str, repo: str, number: int) -> list[dict]:
        return await self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}/files")
    
    async def get_pr_reviews(self, owner: str, repo: str, number: int) -> list[dict]:
        return await self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}/reviews")
    
    async def create_pr(self, owner: str, repo: str, title: str, head: str, base: str, body: str | None = None, draft: bool = False) -> GitHubPR:
        data = await self._request("POST", f"/repos/{owner}/{repo}/pulls", json={
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "draft": draft,
        })
        return GitHubPR(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            draft=data.get("draft", False),
            head_ref=data["head"]["ref"],
            base_ref=data["base"]["ref"],
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            user=data["user"]["login"],
            labels=[l["name"] for l in data.get("labels", [])],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            html_url=data["html_url"],
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changed_files", 0),
            mergeable=data.get("mergeable"),
            merged=data.get("merged", False),
            merged_at=data.get("merged_at"),
        )
    
    async def merge_pr(self, owner: str, repo: str, number: int, commit_title: str | None = None, commit_message: str | None = None, merge_method: str = "merge") -> dict:
        return await self._request("PUT", f"/repos/{owner}/{repo}/pulls/{number}/merge", json={
            "commit_title": commit_title,
            "commit_message": commit_message,
            "merge_method": merge_method,
        })
    
    # Repository file operations
    async def create_file(self, owner: str, repo: str, path: str, content: str, message: str, branch: str | None = None) -> dict:
        encoded = base64.b64encode(content.encode()).decode()
        payload = {
            "message": message,
            "content": encoded,
        }
        if branch:
            payload["branch"] = branch
        return await self._request("PUT", f"/repos/{owner}/{repo}/contents/{path}", json=payload)
    
    async def update_file(self, owner: str, repo: str, path: str, content: str, message: str, sha: str, branch: str | None = None) -> dict:
        encoded = base64.b64encode(content.encode()).decode()
        payload = {
            "message": message,
            "content": encoded,
            "sha": sha,
        }
        if branch:
            payload["branch"] = branch
        return await self._request("PUT", f"/repos/{owner}/{repo}/contents/{path}", json=payload)
    
    async def delete_file(self, owner: str, repo: str, path: str, message: str, sha: str, branch: str | None = None) -> dict:
        params = {"message": message, "sha": sha}
        if branch:
            params["branch"] = branch
        return await self._request("DELETE", f"/repos/{owner}/{repo}/contents/{path}", params=params)
    
    # Actions/Workflows
    async def list_workflows(self, owner: str, repo: str) -> list[dict]:
        return await self._request("GET", f"/repos/{owner}/{repo}/actions/workflows")
    
    async def list_workflow_runs(self, owner: str, repo: str, workflow_id: str | int, per_page: int = 20) -> list[dict]:
        return await self._request("GET", f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs", params={"per_page": per_page})
    
    async def trigger_workflow(self, owner: str, repo: str, workflow_id: str | int, ref: str, inputs: dict | None = None) -> dict:
        return await self._request("POST", f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches", json={
            "ref": ref,
            "inputs": inputs or {},
        })
    
    # Search
    async def search_code(self, query: str, per_page: int = 30) -> list[dict]:
        data = await self._request("GET", "/search/code", params={"q": query, "per_page": per_page})
        return data.get("items", [])
    
    async def search_repos(self, query: str, per_page: int = 30) -> list[dict]:
        data = await self._request("GET", "/search/repositories", params={"q": query, "per_page": per_page})
        return data.get("items", [])
    
    async def search_issues(self, query: str, per_page: int = 30) -> list[dict]:
        data = await self._request("GET", "/search/issues", params={"q": query, "per_page": per_page})
        return data.get("items", [])
    
    # User
    async def get_user(self, username: str | None = None) -> dict:
        endpoint = f"/users/{username}" if username else "/user"
        return await self._request("GET", endpoint)
    
    async def close(self):
        await self.client.aclose()


# Utility functions
def parse_github_url(url: str) -> tuple[str, str] | None:
    """Extract owner/repo from GitHub URL."""
    parsed = urlparse(url)
    if parsed.netloc not in ("github.com", "www.github.com"):
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


async def get_github_client() -> GitHubClient:
    """Get a GitHub client instance."""
    return GitHubClient()