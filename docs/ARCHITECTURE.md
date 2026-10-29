# Architecture

Bifang has two clients over a shared Python agent service: a Textual terminal
interface and a Tauri desktop workspace. Both use a bounded agent loop, typed
tool registry, policy engine, and OpenAI-compatible model providers. Nebius
Token Factory is the default hosted inference path; a separately configured
NVIDIA NIM endpoint is also supported.

## Desktop request flow

The React frontend starts and monitors the local `bifang-server` sidecar. It
creates an assist-mode session for the selected workspace, sends prompts to
the session endpoint, polls for explicit tool approvals, and displays the
resulting worktree diff. The user can review and apply a patch to the original
Git checkout, or close the session to discard its isolated worktree. The
desktop presents each action in an in-app modal with Deny and Allow once
controls. Applying a reviewed diff requires a separate confirmation.

## Isolation and evidence

Git workspaces use disposable Git worktrees by default. File operations are
confined to the active Bifang workspace, and subprocess isolation via
Bubblewrap is optional on Linux. The API service requires an API key for
non-loopback binds. Sessions are held in process memory; closing the service
discards active isolated worktrees. Phoenix tracing is optional and exports
OpenTelemetry spans when configured. It does not record prompt or file
contents.

The KV-cache quantizer is an isolated prototype and is not connected to model
serving. GPU, latency, throughput, and recall improvements are not implied by
the current architecture.
