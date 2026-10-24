# Work at your own pace

Choose **Approvals** in the chat panel. This controls tool approval, independently
of the **Model** selector's task-based routing.

## Three levels

- **Off · manual review** is the default. Inspect proposed edits, commands,
  generated-code execution and external tools before allowing each action.
  Local inspection and the agent's internal task checklist remain automatic.
- **Auto · workspace edits** automatically permits ordinary source-file edits
  in a disposable Git worktree. Sensitive/hidden paths, dependency manifests,
  unknown file types and large writes still ask. Direct edits to a checkout,
  commands, generated code, memory writes and external tools also ask.
- **Full tool approval** requires an explicit confirmation. Enabled tools can
  proceed without repeated prompts, including commands, generated code, MCP
  and plugins. Use it when you trust the project, task and enabled tools.

The choice stays visible and cannot be elevated while a turn is running.
**Pause auto approvals** returns subsequent tool requests to manual review
during a turn; an already-running action can finish. A new chat, workspace change, restored
conversation or browser reload returns to manual review; elevated approval is
not saved in conversation history or browser storage. Applying the final patch
to the original repository is a separate confirmation in every mode.

## What changes and what stays the same

These levels remove approval round trips, not operating-system boundaries.
Existing path checks, command restrictions and the configured command sandbox
remain in effect. Missing required Bubblewrap still stops command execution.
Full approval does not enable disabled tools, grant root or disable the sandbox.

External tools and generated-code execution retain their existing permissions;
not every tool runs inside the command sandbox. They can contact services,
change data and consume credits. Full approval is therefore a deliberate
trust choice, not a classification that every action is safe. Auto mode is a
conservative file-edit policy, not a semantic code-safety guarantee.

Each automatic or manual tool approval is recorded in the local audit with
its selected mode and decision source. Requests outside existing command/path
policy are still rejected.

## API and terminal

Each session chat request accepts `approval_mode`: `manual`, `auto` or `full`.
Full requires the JSON boolean `full_access_confirmed: true`. Omitted approval
mode means manual for that request, even if the previous turn used full.
Elevation cannot affect an already-running session request. The dedicated
`POST /sessions/{id}/pause-auto-approval` endpoint can only narrow approval
to manual, including during an active turn. Session creation
always starts in manual mode, independent of the server's environment.

For terminal agents, explicitly set `BIFANG_APPROVAL_MODE` to `manual`, `auto`
or `full`; unknown values fail configuration validation. Observe mode remains
read-only. The standalone `bifang run` command retains its own command review.

## Native verification

The local release-profile Debian candidate now passes these controls through
its actual Tauri interface: manual approval, automatic isolated edits, full-mode
confirmation/cancellation, a sandboxed sentinel command, a blocked command,
mid-turn pause, post-pause denial and new-chat/reload reset. The original
checkout remains unchanged. Eight synthetic model replies were used.
Exact package/source identities are in [native evidence](evidence/approval-native.json).

To repeat on a supported Linux host with working Bubblewrap namespaces:

```bash
xvfb-run -a uv run --extra dev python scripts/smoke-desktop-approvals.py \
  --application /absolute/path/to/bifang-desktop \
  --native-driver /absolute/path/to/WebKitWebDriver \
  --tauri-driver /absolute/path/to/tauri-driver \
  --output /absolute/path/to/fresh-private-results
```

The script requires free loopback ports 8000 and 4444, creates a disposable
workspace/home and local synthetic provider, and closes test services afterward.
Fresh Ubuntu installation/live coding now pass separately with an explicit
sandbox opt-out; see [Ubuntu sandbox setup](UBUNTU_SANDBOX.md) for the scoped
profile prerequisite and its separate integration evidence. Publication remains held;
the existing public desktop preview predates these approval controls.
