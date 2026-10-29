from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label, 
    RichLog, Static, TabbedContent, TabPane, Tree
)
from textual.binding import Binding

from .github import GitHubClient, GitHubIssue, GitHubPR, GitHubRepo, GitHubFile, parse_github_url
from .config import Config


@dataclass
class GitHubState:
    """GitHub integration state."""
    client: Optional[GitHubClient] = None
    token: str = ""
    current_repo: Optional[GitHubRepo] = None
    issues: list = field(default_factory=list)
    prs: list = field(default_factory=list)
    files: list = field(default_factory=list)


from dataclasses import field


class GitHubPanel(App):
    """GitHub integration panel for Bifang TUI."""
    
    CSS = """
    #github-header {height: 3; background: $panel; padding: 0 1}
    #github-tabs {height: 1fr}
    #repo-info {height: 1fr; border: solid $primary}
    #issue-list {height: 1fr; border: solid $primary}
    #pr-list {height: 1fr; border: solid $primary}
    #file-tree {height: 1fr; border: solid $primary}
    #file-content {height: 1fr; border: solid $primary}
    .tab-content {padding: 1}
    .repo-header {text-style: bold; padding: 1}
    .repo-meta {padding: 0 1}
    DataTable {height: 1fr}
    Input {dock: bottom}
    """
    
    BINDINGS = [
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("ctrl+n", "new_issue", "New Issue"),
        Binding("ctrl+p", "new_pr", "New PR"),
        Binding("ctrl+o", "open_repo", "Open Repo"),
        Binding("ctrl+f", "search", "Search"),
        Binding("ctrl+q", "quit", "Back"),
    ]
    
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.state = GitHubState()
        self.current_tab = "repo"
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("GITHUB | Not connected", id="github-header")
        yield TabbedContent(
            TabPane("Repository", id="tab-repo"),
            TabPane("Issues", id="tab-issues"),
            TabPane("Pull Requests", id="tab-prs"),
            TabPane("Files", id="tab-files"),
            id="github-tabs",
        )
        yield Footer()
    
    def on_mount(self):
        self.load_token()
        self.query_one("#github-tabs", TabbedContent).focus()
        self.query_one("#repo-info", RichLog).write("[bold green]GitHub Panel[/] Press Ctrl+O to connect to a repository")
    
    def load_token(self):
        """Load GitHub token from environment."""
        token = os.getenv("GITHUB_TOKEN", "")
        if token:
            self.state.token = token
            self.state.client = GitHubClient(token)
            self.update_header()
        else:
            self.query_one("#repo-info", RichLog).write("[yellow]No GITHUB_TOKEN found. Set GITHUB_TOKEN environment variable.[/]")
    
    def update_header(self):
        """Update header with connection status."""
        header = self.query_one("#github-header", Static)
        if self.state.client:
            repo_str = f" | {self.state.current_repo.full_name}" if self.state.current_repo else ""
            header.update(f"GITHUB | Connected{repo_str}")
        else:
            header.update("GITHUB | Not connected")
    
    async def action_refresh(self):
        """Refresh current tab."""
        if self.current_tab == "repo":
            await self.load_repo_info()
        elif self.current_tab == "issues":
            await self.load_issues()
        elif self.current_tab == "prs":
            await self.load_prs()
        elif self.current_tab == "files":
            await self.load_files()
    
    async def action_open_repo(self):
        """Open a repository."""
        # In real implementation, would show a dialog
        # For now, use a default if configured
        repo_url = os.getenv("BIFANG_GITHUB_REPO", "")
        if repo_url:
            await self.connect_repo(repo_url)
        else:
            self.query_one("#repo-info", RichLog).write("[yellow]Set BIFANG_GITHUB_REPO or use /gh connect <url>[/]")
    
    async def connect_repo(self, repo_url: str):
        """Connect to a GitHub repository."""
        if not self.state.client:
            self.query_one("#repo-info", RichLog).write("[red]Not authenticated. Set GITHUB_TOKEN.[/]")
            return
        
        parsed = parse_github_url(repo_url)
        if not parsed:
            self.query_one("#repo-info", RichLog).write("[red]Invalid GitHub URL[/]")
            return
        
        owner, name = parsed
        self.query_one("#repo-info", RichLog).write(f"[cyan]Connecting to {owner}/{name}...[/]")
        
        try:
            repo = await self.state.client.get_repo(owner, name)
            self.state.current_repo = repo
            self.update_header()
            await self.load_repo_info()
            self.query_one("#repo-info", RichLog).write(f"[green]Connected to {repo.full_name}[/]")
        except Exception as e:
            self.query_one("#repo-info", RichLog).write(f"[red]Failed to connect: {e}[/]")
    
    async def load_repo_info(self):
        """Load repository info."""
        if not self.state.current_repo:
            return
        
        repo = self.state.current_repo
        log = self.query_one("#repo-info", RichLog)
        log.clear()
        log.write(f"[bold]{repo.full_name}[/]")
        log.write(f"[dim]{repo.description or 'No description'}[/]")
        log.write("")
        log.write(f"[bold]Default branch:[/] {repo.default_branch}")
        log.write(f"[bold]Language:[/] {repo.language or 'N/A'}")
        log.write(f"[bold]Stars:[/] {repo.stars} | [bold]Forks:[/] {repo.forks}")
        log.write(f"[bold]Private:[/] {'Yes' if repo.private else 'No'}")
        log.write(f"[bold]Updated:[/] {repo.updated_at}")
        log.write("")
        log.write(f"[bold]Clone (HTTPS):[/] {repo.clone_url}")
        log.write(f"[bold]Clone (SSH):[/] {repo.ssh_url}")
    
    async def load_issues(self):
        """Load issues for current repo."""
        if not self.state.current_repo or not self.state.client:
            return
        
        log = self.query_one("#issue-list", RichLog)
        log.clear()
        log.write("[cyan]Loading issues...[/]")
        
        try:
            issues = await self.state.client.list_issues(
                self.state.current_repo.owner,
                self.state.current_repo.name,
                state="open",
                per_page=20,
            )
            self.state.issues = issues
            
            log.clear()
            if not issues:
                log.write("[dim]No open issues[/]")
                return
            
            for issue in issues:
                labels = " ".join(f"[#{l}]" for l in issue.labels) if issue.labels else ""
                log.write(f"[bold]#{issue.number}[/] {issue.title} {labels}")
                log.write(f"  [dim]Created: {issue.created_at[:10]} | Updated: {issue.updated_at[:10]} | Comments: {issue.comments}[/]")
                log.write("")
        except Exception as e:
            log.clear()
            log.write(f"[red]Failed to load issues: {e}[/]")
    
    async def load_prs(self):
        """Load pull requests for current repo."""
        if not self.state.current_repo or not self.state.client:
            return
        
        log = self.query_one("#pr-list", RichLog)
        log.clear()
        log.write("[cyan]Loading PRs...[/]")
        
        try:
            prs = await self.state.client.list_prs(
                self.state.current_repo.owner,
                self.state.current_repo.name,
                state="open",
                per_page=20,
            )
            self.state.prs = prs
            
            log.clear()
            if not prs:
                log.write("[dim]No open PRs[/]")
                return
            
            for pr in prs:
                draft = " [yellow](draft)[/]" if pr.draft else ""
                log.write(f"[bold]#{pr.number}[/] {pr.title}{draft}")
                log.write(f"  [dim]{pr.head_ref} → {pr.base_ref} | +{pr.additions} -{pr.deletions} | Files: {pr.changed_files}[/]")
                log.write(f"  [dim]By: {pr.user} | Updated: {pr.updated_at[:10]}[/]")
                if pr.mergeable is not None:
                    mergeable_str = "[green]mergeable[/]" if pr.mergeable else "[red]conflicts[/]"
                    log.write(f"  {mergeable_str}")
                log.write("")
        except Exception as e:
            log.clear()
            log.write(f"[red]Failed to load PRs: {e}[/]")
    
    async def load_files(self):
        """Load file tree for current repo."""
        if not self.state.current_repo or not self.state.client:
            return
        
        log = self.query_one("#file-tree", RichLog)
        log.clear()
        log.write("[cyan]Loading files...[/]")
        
        try:
            files = await self.state.client.get_directory(
                self.state.current_repo.owner,
                self.state.current_repo.name,
                "",
                self.state.current_repo.default_branch,
            )
            self.state.files = files
            
            log.clear()
            for file in files:
                icon = "📁" if file.type == "dir" else "📄"
                log.write(f"{icon} {file.path}")
        except Exception as e:
            log.clear()
            log.write(f"[red]Failed to load files: {e}[/]")
    
    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated):
        self.current_tab = event.tab.id.replace("tab-", "")
        if self.current_tab == "repo":
            asyncio.create_task(self.load_repo_info())
        elif self.current_tab == "issues":
            asyncio.create_task(self.load_issues())
        elif self.current_tab == "prs":
            asyncio.create_task(self.load_prs())
        elif self.current_tab == "files":
            asyncio.create_task(self.load_files())
    
    async def action_new_issue(self):
        """Create a new issue."""
        if not self.state.current_repo or not self.state.client:
            return
        # Would open a dialog in real implementation
        self.query_one("#issue-list", RichLog).write("[yellow]Use /gh issue create <title> <body>[/]")
    
    async def action_new_pr(self):
        """Create a new PR."""
        if not self.state.current_repo or not self.state.client:
            return
        self.query_one("#pr-list", RichLog).write("[yellow]Use /gh pr create <title> <head> <base>[/]")
    
    async def action_search(self):
        """Search code."""
        # Would open search dialog
        pass
    
    async def action_quit(self):
        """Return to main TUI."""
        self.exit()


async def run_github_panel(cfg: Config):
    """Run the GitHub panel."""
    app = GitHubPanel(cfg)
    await app.run_async()