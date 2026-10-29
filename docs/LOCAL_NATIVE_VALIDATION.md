# Local native validation — October 24, 2026

These are local, unreleased artifacts. No public release or Devpost entry was
changed. The public preview predates this package.

## Approval-level candidate

The local approval-level package now passes actual native manual/auto/full
selection, explicit full-mode opt-in/cancellation, a sandboxed sentinel command,
blocked-command rejection, mid-turn pause, denied post-pause write and
new-chat/reload reset. Source changes stay in the disposable worktree.
The selector's native WebKit appearance was corrected and its full/paused
states visually reviewed. Eight local synthetic provider responses were used.

The same new sidecar passes its own missing-sandbox frozen API regression and
real authenticated Phoenix collector check. Its frozen source passes 295 tests,
13 frontend helper cases and the production/native builds. All 336 manifest
source files remain unchanged afterward. Exact identities and scope are in
[approval evidence](evidence/approval-native.json).

This exact candidate now also passes fresh Ubuntu 24.04.5 APT installation
and a native live Ultra task through the judge relay. Five model calls used
13,522 total tokens; requested/reported IDs matched, only `receipts.py`
changed, the original checks were preserved and all five checks passed after
Apply. Three approvals used an automated exact-action allowlist. That run
explicitly opted out of Bubblewrap in the disposable trusted VM, so it is
installation/live-function evidence, not sandbox evidence. Its installation
receipt SHA-256 is
`168de45d2982cda0c27b554e70e93231c29dcc79f3bd4e271e9ad2f022bf9d90`.
Guest credential removal, service closure, VM shutdown and overlay/key removal
were verified. The accepted video remains bound to an older package.

Separately, Ubuntu's distribution-supplied scoped AppArmor profile passed an
A/B/A command-layout probe with global namespace restrictions still enabled;
see [Ubuntu sandbox setup](UBUNTU_SANDBOX.md). An initial installed-desktop
profile run timed out creating its WebDriver session; cleanup passed. A fresh
retry with a 90-second harness HTTP timeout passed the installed native
manual/auto/full, sandboxed sentinel, policy denial, pause/denial and reset
checks. Global namespace restrictions remained enabled, no sandbox opt-out
was used and no runtime binaries changed. Eight synthetic responses and no
real credentials were used. Full/paused screenshots were visually reviewed.
Guest services, VM, overlay, key and host ports were cleaned up. See
[installed Ubuntu sandbox evidence](evidence/ubuntu-native-sandbox.json).
The raw helper's generic host-only scope string is inherited metadata;
the installation wrapper records the actual guest context. These docs
postdate the frozen source archive. Everything remains local and unreleased.

## Frozen-source rebuild

The private source archive containing 328 files was rebuilt into
`Bifang-source-candidate_0.2.0_amd64.deb`. All 328 extracted source files still
match their manifest after building and runtime checks. The build uses locked
dependencies and the existing Cargo cache. Exact identities and receipts are
in [source-candidate runtime evidence](evidence/source-candidate-runtime.json).

The rebuilt package passes these synthetic host checks:

- Actual frozen API: missing Bubblewrap returns actionable HTTP 503 without
  executing the sentinel; the explicit opt-out control succeeds separately.
- Native desktop: automatic, explicit and configured model choices, requested
  and reported receipts, busy controls, catalog recovery, saved history,
  process restart, Apply/Cancel and final patch application.
- Real authenticated Phoenix collector: six linked spans from three synthetic
  provider responses, selected content/credential privacy checks, HTTP 401
  for missing/wrong keys and rejection of unauthenticated gRPC.
- Build-environment inventory: 476 components with retained notice texts.

Nine synthetic HTTP model responses were used across these checks, with zero
hosted model calls. Success and recovery-message screenshots were inspected;
native ports 8000 and 4444 were independently confirmed closed afterward.

This is an extracted-host runtime check, not a fresh-machine installation or
a live inference run for this new sidecar. The installation and video below
retain their original package identities. Later editorial documentation
changes are outside this frozen archive; native bit reproducibility and
rendered Phoenix UI remain separate checks.

## Latest recovery-message candidate

The subsequent release-profile package `bifang-local-recovery_0.2.0_amd64.deb`
has SHA-256
`81944a2639bfa486e19a329964cb2f5371ff2b705be5b1af4b68ae6deae13a91`.
App SHA-256 is
`6dc87707c373c45fc84e1e59d6b7422424d93e397b33643beb2af3297b57e7e3`;
sidecar SHA-256 is
`000009d70dc63c00bad3dd9c27255b5c9a44cdcab6dcdd99bd757c0b60589d65`.

Its actual frozen API returns HTTP 503 with recovery detail when requested
Bubblewrap is missing, after exact-action approval, without creating the
harmless sentinel. The explicit opt-out control still works. An older sidecar
control returns HTTP 500 for the same missing-executable case without creating
the sentinel. These synthetic fixtures make no hosted inference requests.

The new native app also passes model selection, receipts, history restoration,
restart persistence and Apply/Cancel checks using three local synthetic model
responses. An injected structured HTTP 503 reaches its real chat interface as
readable guidance, not a JSON wrapper; the screenshot was visually reviewed.
That UI fault injection is not an actual OS namespace-failure test. Host
ports 8000 and 4444 were independently confirmed closed after cleanup.

The build notice inventory again contains 476 components with no missing
notice texts; it is not a complete binary SBOM or legal certification.

### Subsequent hosted-relay rehearsal

The same exact retained package now passes a native UI coding task through
the approved Vercel HTTPS relay using only its judge token, not the provider
key. Five Ultra calls reported 12,252 tokens. The automated in-app path dialog
rejected relative/file/nonexistent paths, exact-action approvals passed,
only `receipts.py` changed, and the five original checks remained unchanged
and passed after Apply. Model receipts were rendered and visually verified.

Unlike the earlier disposable Ubuntu rehearsal, Bubblewrap was enabled in
the app for this host run and independent final checks used a read-only,
network-isolated fixture mount. The app command sandbox retains its existing
network-sharing policy; this is not a network-denial or hostile-code proof.
No kernel controls were changed. Ports 8000 and 4444 closed after cleanup.
The 30.05-second private raw recording and exact artifact hashes are in
[native relay evidence](evidence/native-vercel-relay.json). This run is not a
fresh-machine installation or native OS folder-chooser trial.

### Earlier fresh Ubuntu installation

This exact candidate now also passes a fresh Ubuntu 24.04.5 APT installation
and live native coding rehearsal: five Ultra calls, 13,722 reported tokens,
only `receipts.py` changed and five original checks unchanged/passing. Its
31.55-second raw recording and screenshots have their own identities in
[current installation evidence](evidence/ubuntu-recovery-desktop.json).
The guest again denied benign Bubblewrap namespace probes; no controls were
weakened, and the trusted fixture explicitly opted out inside the VM. Default
sandbox support in that guest remains unproven. Provider file, guest overlay and private
SSH key were removed after shutdown; test ports were confirmed closed.

Authenticated Phoenix 20.25.0 also passes against this frozen sidecar with
three synthetic model responses and six linked spans. HTTP missing/wrong keys
return 401, unauthenticated gRPC is rejected, and selected content/credential
privacy checks pass. Rendered Phoenix UI, automated evaluation and production
retention are not verified. Previous video/installation results are not reused.

## Earlier sandbox-repair candidate

A later missing-sandbox UX change returns HTTP 503 with recovery guidance and
formats structured errors in the desktop. The package and video identified
below predate that change; see the newer candidate above for its own checks.

`bifang-local-sandbox_0.2.0_amd64.deb` SHA-256:
`339a71b2824089e12fb218af600bdb8b6a5e9e511e264b9817430eb2a31d1c03`.
Native app hash is unchanged; new frozen sidecar SHA-256:
`c482bdb0bd9a134a1c380321e9367ddd693caa60ce625684e252d490d7ace0d0`.

The missing-Bubblewrap regression now passes through the packaged HTTP API,
including actual action approval. The previous sidecar fails that same safe
sentinel check. Explicit opt-out is separately checked. The new extracted
app also passes synthetic model-selection/history/Apply/Cancel/paint checks,
and the actual authenticated Phoenix collector rehearsal passes against its
new sidecar. All these checks use synthetic responses, not hosted inference.

The rebuilt notice inventory has 476 components and no missing notice texts.
This exact package has now also been APT-installed in another fresh Ubuntu
24.04.5 guest. Five live Ultra requests reported 13,464 total tokens; actual
path selection, approvals, model receipts, review/apply and five unchanged
checks passed. A 32.45-second continuous local recording was retained.
The final screenshot and sampled final video frame are bright and show the
success banner; the earlier dim capture was not reused as proof.

Important limitation: Ubuntu installed Bubblewrap, but a benign namespace
probe failed with uid-map Permission denied. The AppArmor user-namespace
restriction flag was 1; the precise cause was not fully isolated. No kernel
security setting was weakened. The known trusted fixture explicitly opted
out of Bubblewrap inside the disposable guest, as earlier rehearsals did.
This is not proof that default sandboxed commands work on that guest.
See [new exact-package evidence](evidence/ubuntu-sandbox-desktop.json).
Nothing was published; the raw recording is not a finished submission video.

## Streaming-repair rebuild

The newer local `bifang-local-streaming_0.2.0_amd64.deb` includes the source
streaming repair. Package SHA-256:
`07fe7df0b8a1142cb55c6fb49f9c64689b0d222c25910bcda402f69efc725129`.
Native app hash is unchanged from below; frozen sidecar SHA-256:
`6e42087c86a2a329d2bd654bee093b6c8a20835f89320c19af5eaedfab9dd609`.

Its extracted native app passed the synthetic model-selection/history test
again: three fixture HTTP model calls, busy controls, requested/reported
receipts, catalog recovery, history restoration and Stop/Start persistence.
Evidence is in sibling `bifang-native-streaming-check-20261023/evidence.json`.
This did not call hosted models or exercise streaming inside the frozen
binary: the desktop HTTP ask route currently uses non-streaming completion.
The separate live source SSE check is documented in `STREAMING.md`.

The new build-notice inventory has 476 components and zero missing notice
texts, with package/sidecar binding in the sibling
`bifang-streaming-complete-notices-20261023` directory. Offline Cargo metadata
required an explicit Linux target; the unfiltered attempt wanted an uncached
Android crate and failed rather than downloading it.

The helper returned success after requesting sidecar stop. A separate
host-network socket check was not executed because the automatic approval
reviewer hit its usage limit. Do not claim independently verified post-test
port closure for that extracted-app run.

The same exact package has subsequently been APT-installed in a fresh
Ubuntu 24.04.5 LTS KVM guest. The installed app passed the live Token Factory
Ultra fixture through the actual path dialog, action approvals, review/apply
and five unchanged original checks. Four model requests reported 10,066 total
tokens, with requested/reported IDs matching. Guest runtime libraries came
from Ubuntu, not the host's extracted development-library directory.
Both guest test ports were confirmed closed; its private provider file was
removed, the guest powered off, and the overlay/disposable SSH private key
removed. See [exact-package installation evidence](evidence/ubuntu-streaming-desktop.json).
This closes that package's Ubuntu installation/live coding gate, not broad
portability, frozen SSE, native GTK chooser or general agent-quality gates.
Prior results below belong to the older package.

## Capture/paint follow-up

The clean-guest final screenshot was dimmed after dialog closure, although
the DOM success check and independently applied source tests passed.
A separate local synthetic native fixture now exercises the real Apply
confirmation, Cancel, Apply-to-repository, actual file change and source
restoration. It retains immediate and two-frame-plus-100-ms screenshots.
Both success images were visually reviewed: the backdrop was absent and the
success banner legible. History, model selection and Stop/Start checks also
passed, using three local fixture HTTP calls and zero hosted calls.

Evidence is in sibling `bifang-native-paint-check-20261024/`. This does not
reproduce or identify the cause of the earlier Ubuntu-only captured frame;
do not call that a proven runtime fix. The live rehearsal helper now waits
for the same frame barrier before screenshots, which still needs its own
public-video review before use. A later clean-guest live recording using the
frame barrier now has a clear final screenshot and sampled final video frame;
this validates that capture run, not the root cause of the earlier frame.
Synthetic images
must not be presented as new live-model results.

## Previous exact package identity

`bifang-local-multimodel-dark-picker_0.2.0_amd64.deb`

- Debian package SHA-256: `c01bf384cd71791f4854a721411ce27bbbc5e3c5a75a327a92873f3b27fc5a34`
- Native app SHA-256: `7b92143d0269749793cd28943f5254b27e85e15624fbf7650e195c44208aa221`
- Frozen sidecar SHA-256: `38ba11096beb40abb0c1b7e13b7893b703f88de420b37581e6f8c3bf9d1864d4`

The release-profile package was built from the local source and extracted on
the development host. It is not a fresh-machine installation result. Existing
public-preview installation evidence does not establish installation of this
new exact binary.

## Native model controls and history

`scripts/smoke-desktop-history.py --model-fixture` uses a local synthetic
OpenAI-compatible HTTP service, with a synthetic credential, isolated home,
temporary repository and dedicated X display. No paid hosted inference occurs.
The actual packaged app/sidecar transport issued three fixture completions:
auto → balanced, explicit → fast, configured → pinned Ultra. The test checked
actual provider requests, separate requested/reported model identities,
disabled model changes while busy, catalog failure visibility and recovery.

The same run verified real history selection, literal historical text,
HTTP-503 resume-failure preservation/candidate cleanup, Stop/Start and durable
history after process restart, without replaying historical commands or
changing source. See [sanitized evidence](evidence/desktop-model-selection.json).
The legacy `model_requests: 0` field means hosted requests; the separate
`model_fixture_requests: 3` records the actual local fixture requests.

The first new-helper attempt selected the hidden path-dialog submit button
instead of the chat submit button. Its selector was corrected. Native visual
inspection also revealed an unreadable light-themed select; explicit native
appearance removal/dark styling fixed its contrast in the rebuilt package.

## Live coding regression

`scripts/rehearse-desktop.py` then used the private Token Factory key only
against the official endpoint, with the same exact app binary. The final
successful run made four Ultra calls, all reporting the requested Ultra model,
and 10,044 total reported tokens. This is one synthetic coding task, not a
general model-quality or performance benchmark.

The actual UI selected the workspace, rejected relative/file/missing paths,
presented exact-action approvals, reviewed/applied the patch and left only
`receipts.py` changed. All five original checks passed and the checks file
remained byte-identical. See [live coding evidence](evidence/desktop-multimodel-live-coding.json).
Approval clicks were an automated exact-action allowlist, not human judgments
or proof of adversarial-repository isolation. Bubblewrap was disabled for this
controlled fixture. No new recording/video was produced.

An earlier run passed coding but left its sidecar after WebDriver's forced
session shutdown. Only that verified test-owned process group was terminated.
The helper now explicitly invokes sidecar Stop before deleting its automation
session and attempts cleanup on failures. The corrected rerun passed; separate
post-run checks confirmed ports 8000 and 4444 had no listeners. This does not
establish cleanup after arbitrary force-killing of the application.

## Notices and remaining gates

`bifang-multimodel-notices-20261023.tar.gz` SHA-256:
`e55e6b0daa7151a8ed7bf313aa50913d5793cc4d2996ccc392049acb763c798c`.
It contains the current 476-component Python/npm/Cargo/distribution build
inventory, notice text for every listed component, retained supplementary
source provenance and a binary-binding manifest. This conservative inventory
is not a complete binary SBOM or legal certification. The initial collection
used the wrong supplementary argument and listed six gaps; regeneration used
the actual supplementary directory and closed those inventory gaps.

The newer streaming-repair package now has fresh Ubuntu installation/live
coding and frozen-server Phoenix evidence. Distribution review, hosted CI,
broad routing evaluations and publication approval remain distinct gates.
The older package above predates a subsequent NVIDIA/Nebius
streaming source repair. Fourteen transport/agent tests now cover fragmented
arguments, protocol errors, usage, history and cancellation in local source;
see [streaming boundaries](STREAMING.md). These source tests and the successful
non-streaming desktop test do not prove live streaming in this frozen package.
