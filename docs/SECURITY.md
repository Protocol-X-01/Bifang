# Security

Bifang assumes model output is untrusted. File paths are resolved and constrained to the active workspace. On the first workspace file list, read, search result, diff or saved-memory result in a chat, Manual and Auto modes ask before sharing that content with configured model endpoints; consent applies to workspace/model sharing for that chat. Restoring a saved conversation with tool results asks separately before its history is sent to a model. A memory write sent to a remote embedding endpoint has a per-write endpoint-aware approval, and memory-retrieval queries sent to a remote embedding endpoint have their own chat-scoped approval for that embedding configuration. Neither approval grants workspace/model sharing or authorizes a different embedding configuration. Built-in file tools block conventional credential paths, and recognized secret values are redacted from file, memory, diff and command output. Manual and Auto command prompts disclose that command output returns to the model. These checks are heuristic and do not detect every secret format.

The generated-Python tool runs only in a temporary Bubblewrap workspace with the offline network filter and a bounded timeout. Missing or unsupported Bubblewrap stops execution; there is no host-Python fallback. Optional package requirements are restricted to names/specifiers, downloaded as binary wheels from PyPI without running source builds, and monitored against a 128 MiB temporary-data budget during acquisition, with a 60-second timeout. The downloader is stopped when the monitor observes an overrun, and the final wheelhouse is checked before installation. Monitoring is polled, so temporary aggregate usage can briefly exceed the threshold; POSIX hosts also enforce a per-file size limit. Wheels are installed inside the sandbox. The approval prompt shows the exact code and package list. Full mode skips prompts but does not disable the generated-Python sandbox. Recognized-value redaction is heuristic; command approval remains important for workspaces containing private material. Git worktrees separate agent modifications from the developer checkout.

Current local source uses [offline command networking](NETWORK_ISOLATION.md),
with a private network namespace and a seccomp transport filter. Use
`bifang sandbox-check` to verify the actual host. Older published packages and
retained VM evidence have their own layouts and are not upgraded by this change.
Regular expressions are not a complete shell policy; Bubblewrap is not available
on every kernel and sharing host `/etc` read-only can expose metadata. For
hostile code, run Bifang inside an externally network-restricted disposable VM.

## What the action-boundary tests establish

Ten additional local cases in `tests/test_agent_action_boundaries.py` exercise
the real agent's tool dispatcher, not just a string classifier:

- Assist mode refuses file writes, shell commands and generated Python when
  approval is denied, even when argument text claims a system override or
  that approval has already been granted.
- Observe mode denies those same actions without asking for approval.
- Recognized privilege-escalation/destructive command patterns remain denied
  before approval or subprocess execution.
- Parent traversal and symlink escapes cannot read outside the workspace.

These cases use synthetic arguments and fixtures. They make no hosted model
requests and do not execute dangerous shell commands. They do **not** measure
how often an actual model resists direct/indirect prompt injection, malicious
repository instructions, encoded attacks or multi-turn social engineering.
Literal historical HTML not executing in the desktop is a separate UI XSS
check, not a prompt-injection benchmark.

An action approval is a permission boundary, not evidence that the proposed
action is safe. Users must inspect it. Shell deny patterns are not a complete
parser or semantic safety policy; obfuscated/equivalent commands can evade
pattern matching. Trusted mode removes normal approval prompts and should not
be used for untrusted projects. MCP, plugins, network egress and every builtin
need separate permission/abuse coverage before a general guardrail claim.
When Bubblewrap is active, the agent shell and package setup hide recognized
credential paths and private Bifang session logs. Git metadata, dependency
stores and build output remain visible and may contain historical secrets.
Keep credentials outside projects and out of Git history. Setting
`BIFANG_BWRAP=0` runs shell commands directly on the host and gives them access
to workspace files; use that option only for trusted workspaces.

The ordinary command runner previously fell back to the host shell when
Bubblewrap was requested but its executable was missing. A new regression
reproduced that behavior before the source fix. It now fails before starting
any subprocess. Explicit sandbox opt-out remains possible for trusted
environments; two tests cover missing-sandbox rejection and explicit opt-out
with environment filtering. This narrow repair does not harden all builtin,
plugin or MCP execution paths or prove that Bubblewrap defeats hostile code.
The isolated coding-evaluation runner has its own fail-closed sandbox path.
The native coding rehearsal explicitly disabled Bubblewrap inside a disposable
guest and is not proof of hostile-code isolation.

A new local sandbox-repair package now passes the regression through its
actual frozen API and exact-action approval flow. With Bubblewrap absent
from PATH and sandboxing requested, no harmless sentinel file is created;
explicit opt-out permits the same controlled command. The prior sidecar
creates the sentinel even with sandboxing requested, so the harness detects
the original defect. No hosted calls or real credentials are used. See
`evidence/frozen-sandbox.json` for exact hashes and limitations. The rejection
surfaces as HTTP 500 in that retained package. A subsequent source-only UX
change gives missing-executable failures a dedicated exception and HTTP 503
with installation/recovery guidance, without starting a shell or automatically
disabling protection. The desktop parses the structured message instead of
displaying the JSON wrapper or arbitrary raw HTML errors. An actual Agent
through the ASGI route with a synthetic provider verifies approval, one model
request, no subprocess, and cleared busy state; desktop helper tests verify
message formatting. The newer recovery-message package now independently
passes the actual frozen API check (HTTP 503, no sentinel) and native UI
formatting with an injected structured error. The screenshot was inspected;
ports were independently confirmed closed. See `LOCAL_NATIVE_VALIDATION.md`
for its distinct hashes. Fresh-install/live trusted-fixture and frozen
authenticated Phoenix checks now also pass for that exact newer sidecar;
these are not general sandbox compatibility or prompt-resistance results.
Ubuntu's installed-but-denied namespace case now has a measured scoped setup:
the distribution's extra Bubblewrap AppArmor profile passed an A/B/A probe
while its global namespace restriction remained enabled. See
[Ubuntu sandbox setup](UBUNTU_SANDBOX.md) for the administrator prerequisite,
exact evidence and separate desktop-integration status.
The missing-executable recovery does not detect or fix every installed-but-denied namespace
failure. The retained exact package also passes a trusted live coding fixture in
fresh Ubuntu, but that rehearsal explicitly opts out of Bubblewrap inside
the disposable guest. Its installed Bubblewrap failed a benign user-namespace
probe with uid-map Permission denied. A working executable is not sufficient
proof that the OS permits sandbox creation. Do not weaken host kernel/AppArmor
controls just to make a demo pass. Use an appropriately configured isolated
environment for untrusted code; explicit opt-out is only for trusted workloads.

Phoenix exports allowlisted observability metadata; it does not enforce
execution safety. Advanced metrics integration remains a post-hackathon feature:
[pinned synthetic compatibility tests](SECURITY.md) found streaming,
tool-argument and structured-content inspection gaps. Do not advertise it as
active guardrail coverage on the serving path.
Do not describe either as independently proving dangerous-prompt resistance.
