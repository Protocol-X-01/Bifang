# Filespaces

Use **New workspace…** to create an empty project under an existing parent,
or open an existing directory. Creation never overwrites an existing path and
does not install dependencies, initialize Git, or run scripts.

The sidebar remembers the last 20 opened filespaces on this device: directory
path, display name and last-opened time. Reopening checks that the directory
still exists. Files remain in their original directories; this list is not a
backup or cloud sync. Browser storage is origin-specific and can be cleared or
unavailable. Closing a workspace does not delete its files.
**Forget current filespace** removes its saved history entry, not the directory
or the currently open project.

## Local browser development

The Vite development server provides folder creation, directory selection,
reopening and a filename-only tree without requiring Tauri. In a browser,
**Browse parent folder…** lists local directories instead of opening the native
desktop picker. File trees skip hidden paths, symlinks and common build outputs,
limit traversal to nine levels and reject trees over 2,000 entries.

Access is restricted to the host user's home directory by default. To narrow
it further, set `BIFANG_BROWSER_WORKSPACE_ROOT` to an existing project directory
before starting the development server. Both connection addresses must be
loopback; Host and Origin must match the actual HTTP listening port. Requests
use a same-origin handshake and an in-memory token, strict fields and an 8 KiB
body limit. Canonical directory checks reject paths and symlinks outside the
configured root. These are local-development boundaries, not protection against
another process already running as the same user or racing filesystem changes.

This bridge is development-only, not a public hosted filesystem API. Do not
reverse-proxy it to the internet. Static production builds do not contain a
filesystem server. It does not expose shell execution, file-content reading,
plugin trust, credentials or the native workbench over HTTP. The desktop keeps
its separate native access checks. Browser folder access alone does not provide
the full desktop agent or terminal experience.

## Memory and conversation storage

Filespaces are separate from the existing agent memory and conversation history.
Agent memory uses the configured SQLite store; conversation history has its own
configured cache and controls. See [Memory retrieval](MEMORY_RETRIEVAL.md) and
[Conversation history](CONVERSATION_HISTORY.md). Saved paths are not model
instructions, and reopening a project does not grant new execution permissions.
