# Security

Bifang assumes model output is untrusted. File paths are resolved and constrained to the active workspace. Commands pass through deny rules, approval policy, time limits, environment filtering, and optional Bubblewrap namespaces. Git worktrees separate agent modifications from the developer checkout.

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
Workspace confinement does not hide secrets already inside that workspace.
Keep provider credentials outside projects and out of model-readable files.

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
