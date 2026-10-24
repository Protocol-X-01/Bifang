# Durable conversation history

Implemented in the local development version, not yet in the public preview.
This stores application conversation records, **not model-engine KV tensors**.

## Terminal use

```bash
bifang --workspace /absolute/project/path conversations
bifang --workspace /absolute/project/path chat --session CONVERSATION_ID
```

The first command lists the selected project's saved identifiers and turn
counts without creating a Git worktree or making an inference request. The
second resumes an existing identifier from that project. Unknown identifiers
fail rather than silently starting a different conversation. The terminal
chat pane displays restored user/assistant text and new model responses.

Restoring history does not restore an old worktree, apply a patch, rerun a
command, or approve a tool. Re-inspect current files before continuing:
historical claims about code may no longer match the current checkout.

## Local API

- `GET /conversations?workspace=relative/project` lists that workspace's histories.
- `POST /sessions` accepts optional `conversation_id` alongside `workspace`.
- Session creation returns a live `session_id` and durable `conversation_id`.
- `GET /sessions/{session_id}/history` returns turn text, timestamps and status.

A conversation from a different project is not silently imported. Workspace
confinement also applies when Git promotes a selected child directory to its
repository root. The API's existing authentication requirements apply; these
are local-owner/project boundaries, not a multi-tenant account/ACL system.

The desktop client can keep making normal sessions without API changes. A
desktop history picker and corresponding native UI rehearsal remain pending;
the new resume controls are currently available through the API and terminal.

## Durability and failure behavior

Completed turns are committed to SQLite before the agent returns its answer.
Their original user, assistant tool requests, tool results and final assistant
messages are retained together. Explicit resume restores valid completed
message sequences and the original system instructions without executing tools.

Failed, cancelled, interrupted and maximum-step turns are marked separately.
They are not injected as completed turns on resume. Failure/cancellation rolls
the in-memory request back so unresolved tool calls do not poison the next
request. An orderly session close awaits persistence rather than launching
an untracked background save. A hard process kill may lose an in-flight turn;
already committed completed turns are durable.

Separate cache instances append transactional records rather than replacing a
shared JSON snapshot. IDs use UUIDs rather than millisecond timestamps.
Appending from two writers preserves their stored turns; this does not make
simultaneous model actions on one Git worktree safe. Agent requests are
serialized per live agent. Each provider manager owns its clients, so closing
one manager does not close another session's connections.

## Storage and privacy

The default database is
`~/.local/state/bifang/conversations/PROJECT_ID/conversations.db`, where
`PROJECT_ID` hashes the original source path. Disposable worktrees from that
same source share its histories. Newly created POSIX files use mode 0600 and
directories mode 0700. Data is plaintext, not encrypted at rest.

History may include prompts, generated code and tool/file outputs. Do not
feed secrets into a conversation. Set `BIFANG_ENABLE_CONVERSATION_HISTORY=0`
to prevent this transcript database from being written. This setting is
independent of `BIFANG_ENABLE_MEMORY` and does **not** disable the local audit
log in `.bifang/sessions/`. New audit logs have unique names, private file
permissions and a check against workspace-escaping directory symlinks.

`BIFANG_CONVERSATION_CACHE_PATH` explicitly overrides the directory. Using
one directory for several projects intentionally shares their histories.
The old global `conversation_cache/sessions.json` is left untouched and is
not automatically imported into an arbitrarily chosen project. Corrupt new
databases raise an error rather than being silently replaced or discarded.

Storage grows until cleaned up. The cache's explicit cleanup method prunes
old sessions; automatic retention deletion and a history-management UI are
not yet enabled. Back up valuable histories and protect backups separately.

## Verified scope

Tests cover commit/reopen, complete tool-pair restoration, project separation,
rapid unique IDs, independent writers, failure/cancellation, corrupt storage,
disabled history, explicit API resume, client ownership, terminal history
rendering, new response display, and CLI selection. Model responses in these
tests are mocked. Five frontend API tests cover response validation, stable
message IDs, literal historical text, URL encoding and visible fetch failures.
Listings page metadata without loading full transcripts, with bounded query
parameters and backend pagination coverage.

The local Linux release candidate passed `scripts/smoke-desktop-history.py`
against its actual extracted Tauri binary on an isolated virtual display.
The test selects the project through the path dialog, renders/restores two
preseeded synthetic messages, rejects executable historical markup, injects a
history-HTTP-503 failure without replacing the active conversation, checks
candidate cleanup and resumes after a real server stop/start. Health disappears
and in-memory sessions reset before the SQLite history is retrieved again.
Historical command records are not executed, source files remain unchanged,
and the test makes zero model calls. Evidence:
[native history report](evidence/desktop-history.json).

The rehearsal found and fixed a one-file sidecar process-tree cleanup defect.
This is local native UI evidence, not a new live-model recall benchmark,
fresh-machine installation, crash-proof in-flight execution or hostile-code
isolation. The public preview has not been updated.
