# Architecture

Arca comprises a Textual terminal client, bounded agent loop, Nebius Token Factory provider, typed tool registry, policy engine, Git-worktree box, optional Bubblewrap process isolation, and append-only audit log. The model selects tools through Chat Completions function calls. Every tool result returns to the model until it emits a final answer or reaches the configured step limit.
