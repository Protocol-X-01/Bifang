# Ember terminal

Run `bifang chat` from the project you want to inspect. Configuration and provider
selection follow the same Python CLI settings. Git projects normally use an
isolated worktree; inspect its diff before transferring changes to your checkout.

## Action review and cancellation

The current local source runs chat in a background UI worker, keeping the terminal
responsive while a model or tool is waiting. Manual tool approval appears inside
the terminal, with the exact requested action as literal, scrollable text.

- **Deny** is focused initially. Enter without moving focus denies the action.
- Tab to **Approve**, then Enter, to approve that one action.
- Escape dismisses the approval as a denial.
- Ctrl+X cancels the active request, including a pending approval. Inspect changes
  already made before continuing; cancellation does not roll them back.
- Closing the application while approval is pending does not authorize the write.

The configured manual/auto/full approval policy still applies. Automatic policy
decisions do not acquire a new manual prompt, and approval does not disable
workspace or command-sandbox policy.

F2 opens Checks, F3 Activity and F4 Receipts. Inspectors replace the main view on
narrow terminals; press the same key again to return. The layout is tested at
80×24, 100×36 and larger sizes.

For keyboard-only engineering, **F6** opens Setup and focuses the brief. Tab moves
through source files, writable paths and the check argv, then Build, Check,
Review, Stage, Apply and Cancel. **F7** opens and focuses the scrollable Evidence
view. From Evidence, Tab reaches Build and the subsequent action buttons. Closing
Checks returns focus to chat; F1 opens visible help even from another inspector.

## Developer workbench

**F8** or `/workbench` opens the plugin, language and local system workbench.
It uses the original project directory, not an agent's isolated worktree.
The newer **Packages** tab adds [reviewed npm, Python and Rust setup](PROJECT_SETUP.md),
with a separate install confirmation, streamed output, Ctrl+X cancellation and
saved exit receipts. Select the ecosystem and whether to request build-code
permission before planning; build-enabled plans require two separate approvals.
This is distinct from the F6 engineering-brief Setup view.

- Select a plugin and **Review** to inspect its literal metadata, source and
  origin-bound SHA-256. No plugin code is imported for inspection.
- **Enable** always opens a separate full-host-code trust prompt, including in
  auto/full agent modes. Deny is initially focused; Escape denies. Changed bytes
  during confirmation reject the old fingerprint and require fresh review.
- **Disable** removes current trust. Already executed host-code side effects
  are not reversed. Plugins load on the agent's next refresh, not by viewing them.
- **Languages** lists detected root manifests and exact bootstrap argv previews.
  A foreign JavaScript lockfile requires manager selection; no npm substitution
  or package installation runs from this screen.
- **Sample** shows one real [Forge pulse](SYSTEM_METRICS.md) reading, separately
  from model usage. It makes no model request and starts no background monitor.
- Escape or Close returns to the editor. Ctrl+X cancels a pending workbench
  action or trust confirmation. Workbench actions pause while chat/engineering
  is active. Source above 5,000 lines requires desktop/external review; the
  terminal refuses enablement rather than silently truncating the inspected code.

The current source adds these controls in development version dev.8. Headless
Textual tests cover keyboard use at 80×24 and 120×36, literal source, default
denial, exact trust, disable, changed-code rejection, Escape, cancellation,
busy gating and real local sampling. These are not provider or native-window
acceptance claims; the earlier installed dev.7 wheel predates this workbench.

## Selected-file engineering

Open **Checks** with F2. In Setup, enter the brief, a JSON array of existing source
files, an explicit JSON array of writable paths, and the independent check argv.
Tests can be selected as read-only inputs; only writable paths are editable by
the implementer. Engineering requires a clean, isolated Git worktree.

1. **Build** asks permission to share the selected files with configured model
   routing for up to six implementer steps. Individual writes follow the chosen
   approval mode. The result is labelled as a model proposal, not verification.
2. **Check** confirms the exact argv and candidate hash, then runs it against a
   frozen, read-only Bubblewrap snapshot with a 30-second limit. Command output,
   exit status and candidate hash appear in Evidence. Missing sandbox support
   stops the check; there is no unsandboxed fallback.
3. **Review** shows the full candidate patch as literal text and records its hash.
4. **Stage** requires a current passing check and the reviewed candidate. Its
   separate confirmation transfers the patch into the isolated worktree only.
5. **Apply** separately displays and confirms the staged patch for the original
   checkout. Changes after review, including changes during the confirmation,
   are rejected. A dirty original checkout is refused by the shared workspace
   implementation. Review and preserve your staged changes before exiting.

Ctrl+X also cancels engineering operations. Chat and engineering actions cannot
run concurrently in the same application. Temporary candidate storage is removed
when the application closes; the isolated worktree remains available for review.

Local commands are `/help`, `/status`, `/diff`, `/checks` (alias `/verify`),
`/activity`, `/metrics`, `/workbench` and `/quit`. Unknown slash commands are reported locally
without sending a model request. Commands do not grant host privilege.

## Evidence and next acceptance gates

October 28: the dev11 wheel built from frozen source
`ca7377fea38884020174d5b328ae0e6ff9bfc5cf1cd41527cda1d720f0909a1f`
is installed in an isolated Python 3.11 environment. All 112 package files
match that source and the installed files; wheel RECORD hashes and dependency
compatibility pass. Wheel SHA-256:
`42a9c9457d0768ae629269a25c4b69bdd876523ed7ed30fb2d6693a3d391f1b4`.

Its actual 80×24 PTY completes keyboard-only Build, failing Check, repaired
Check, Review, Stage and separate Apply. Two synthetic HTTP model replies
drive the task; Bubblewrap checks and Git changes are real. Denied sharing,
Stage and Apply preserve the original files; only the approved implementation
changes after final Apply. The fixture process, server and temporary workspace
are removed. This updates the installed terminal evidence beyond dev7;
human usability, screen-reader acceptance and publication remain open.

The new controls are post-Preview-6 local source changes. Headless
Textual keyboard tests exercise real Agent write-tool approval, default denial,
explicit approval, Escape, cancellation during approval and inference, provider
stream closure, another request after cancellation, literal prompt rendering and
shutdown with an unanswered approval. These use synthetic model responses and
disposable files, without provider credentials or hosted inference.

The [terminal engineering receipt](evidence/terminal-engineering.json) records an
80×24 headless keyboard workflow with a synthetic implementer and real Bubblewrap
checks: one deliberate exit-1 check, a passing unittest check, candidate review,
denied and approved stage/Apply, unchanged tests, stale-patch rejection and exact
original-checkout Apply. That earlier source checkpoint passed 536 backend tests
with real-sandbox execution enabled. The fixture uses no hosted model requests
and changes no host policy.

Reproduce on a host with working Bubblewrap:

```sh
BIFANG_TEST_REAL_BWRAP=1 uv run --locked --extra dev pytest -q tests/test_terminal_engineering.py
```

Ordinary test runs skip only the explicitly opted-in real-sandbox case.

The newer [installed-wheel receipt](evidence/terminal-wheel.json) binds the local
Python 3.11 `0.2.1.dev7` candidate. Its 94 package files match the frozen source and
installed bytes, its wheel RECORD validates, and two local builds produce identical
wheel bytes. All 537 backend tests pass against imports from that installed wheel,
with pytest's source-path injection disabled.

An actual 80×24 pseudo-terminal walkthrough also passes: typed setup, source-sharing
denial without inference, two synthetic loopback HTTP model responses, real
exit-1/exit-0 Bubblewrap checks, patch review, denied and approved stage/Apply, exact
original changes, immutable tests and clean shutdown. Keyboard and terminal mouse
events are automated from decoded screen labels; this is separate from a human
usability or screen-reader walkthrough. No hosted model credits are consumed.

The development wheel and newer source remain local; the published Preview 6
desktop installer is unchanged. Screen-reader and human usability checks remain
acceptance gates. Desktop and hosted receipts do not replace terminal evidence.

The subsequent [keyboard-only receipt](evidence/terminal-keyboard.json) binds the
focus-repaired development candidate: 539 tests pass against its installed wheel,
and the complete real PTY workflow uses zero mouse events. The same real sandbox
checks, denial paths, immutable tests and separate original Apply are exercised.
This adds keyboard-navigation evidence; it does not establish screen-reader
compatibility. Earlier wheel receipts retain their original source/package hashes.
