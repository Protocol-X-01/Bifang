# Security

Arca assumes model output is untrusted. File paths are resolved and constrained to the active workspace. Commands pass through deny rules, approval policy, time limits, environment filtering, and optional Bubblewrap namespaces. Git worktrees separate agent modifications from the developer checkout.

Limitations: regular expressions are not a complete shell policy; Bubblewrap is not available on every kernel; sharing host `/etc` read-only can expose non-secret metadata; network is currently shared to support package/test workflows. For hostile code, run Arca inside a disposable VM and disable network externally.
