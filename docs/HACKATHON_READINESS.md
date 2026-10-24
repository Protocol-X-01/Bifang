# Hackathon readiness — 2026-10-24

## Current delivery checkpoint

Preview 4 packages bounded read-only team review, an isolated selected-file
implementer, independently executed checks, reviewed staging, Tavily search,
optional metadata-only LangSmith export, and the responsive Ember terminal.
All 348 backend tests pass from the retained 363-file build-input archive.
The exact installer passes a fresh Ubuntu native walkthrough: write denial
causes a failing check; write approval enables a passing check, reviewed
staging and separate original Apply. Seven synthetic model calls, zero hosted
calls, scoped distro AppArmor profile, global restriction still enabled.
See [engineering guide](ENGINEERING_WORKFLOW.md),
[installed package evidence](evidence/ubuntu-engineering-native.json), and
[installation details](INSTALLATION_EVIDENCE.md).

The source archive and build-input archive have distinct roles; post-build
documentation and the native test helper are not a new binary rebuild.
Vision, durable hosted orchestration, and actual iOS/Android clients remain
explicit requirements in [product expansion](PRODUCT_EXPANSION.md).
Final video publication and Devpost submission remain owner decisions.

## Historical checkpoints

The working source now includes three desktop tool-approval levels: manual,
automatic ordinary worktree edits and explicit full tool approval. A dedicated
pause control returns subsequent actions to review during a turn. The full
source suite passes 295 tests, the frontend passes 13 helper tests and its
production build. A new frozen-source release-profile Debian candidate now
passes actual native approval controls, full sandboxed command execution,
policy denial, pause/denial and reset checks with eight synthetic model replies.
Its own frozen API fails closed when the sandbox is missing; authenticated
Phoenix also passes against the same new sidecar. All 336 source files remain
unchanged after build/tests. See `evidence/approval-native.json` for host proof.
This exact package now also passes fresh Ubuntu installation and a live Ultra
coding task, with an explicit sandbox opt-out in that trusted VM. A separate
scoped distribution AppArmor profile probe keeps global namespace restrictions
enabled; see `UBUNTU_SANDBOX.md`. Installed-desktop profile integration also
passes with eight synthetic replies, a real sandboxed sentinel and the native
approval/pause/reset controls; see `evidence/ubuntu-native-sandbox.json`.
The live opt-out task and synthetic sandboxed task are separate proofs.
This checkpoint's publication hold was later lifted for source and Ubuntu
prereleases; the retained historical evidence keeps its original scope.
See `APPROVAL_MODES.md`.

A frozen 328-file source archive now produces a release-profile Debian package
that passes its own frozen API, synthetic native model/history/Apply checks
and real authenticated Phoenix collector test. All 328 source files still
match after validation; nine synthetic model responses and zero hosted calls
were used. The source/package identities and exact scope are recorded in
`evidence/source-candidate-runtime.json`. The newer reading-friendly private
video runs 2:50, with the complete earlier live capture at half speed and
clearly labelled detail pauses; see `SUBMISSION_VIDEO.md`.

The pre-approval-mode working copy passed 263 backend tests; its desktop helper
run passed 11 tests. Six newer tests covered relay-only Vercel packaging,
explicit runtime selection and shared model IDs. The
minimal local bundle separately passes synthetic ASGI checks with fresh locked
dependencies on Python 3.11 and 3.12. A relay-only Vercel Hobby preview is now
deployed using managed Python 3.12, with provider credentials stored as secrets.
External HTTPS verifies authorization, the three-model catalog, an actual
Ultra client completion and Nano SSE completion (177 reported tokens total).
There is no agent execution on the relay. A subsequent retained-package native
desktop coding task through this URL passed with judge-only credentials,
Bubblewrap enabled, exact-action approvals, patch apply and five unchanged
checks. It made five Ultra calls reporting 12,252 tokens; see
`evidence/native-vercel-relay.json`. Shared quotas and judging-period
availability remain unverified.
The operator access check passes seven metadata requests without inference;
28 new tests cover credential-safe reporting, redirects, metadata bounds and
invalid input. `JUDGE_OPERATIONS.md` defines the remaining operating gates.
The creator published the WAF burst-observation rule. Preview matching is
verified by five log events from 125 empty unauthenticated requests, all
rejected with 401; this is log-only observation, not enforcing throttling.
The additional 16 tests cover an optional inference-only judge relay, including
the real Nebius client against synthetic upstream responses. Its Docker image
now builds, but was not run before Vercel replaced the earlier hosting proposal.
See `VERCEL_SETUP.md` and `evidence/vercel-relay-hosted.json` for the preview
and cleanup of two automatically promoted preliminary deployments.
One separate live relay request reported 42 tokens and matching
Ultra IDs, using an in-process relay rather than a hosted URL. The later HTTPS
and native task checks do not prove funding or availability through judging;
see `JUDGE_ACCESS.md`.
A later missing-sandbox UX fix returns actionable HTTP 503 errors without
host-shell fallback. A new recovery-message package verifies its frozen API
and native UI formatting. Its own fresh Ubuntu installation/live coding and
frozen authenticated Phoenix checks now pass; its 31.55-second raw video is
separate from the previous package's captioned draft. The new release-profile
streaming-repair package passes the synthetic native model-selection/history
regression, while live SSE passes separately from source. A fresh Ubuntu
APT installation now independently verifies this exact new sidecar's live
native coding loop, path selection, approvals, apply and five unchanged checks.
The older public preview's clean-VM results were not reused for that claim.
See `LOCAL_NATIVE_VALIDATION.md` for exact package hashes and boundaries.

The newest sandbox-repair package now verifies the command-runner fail-closed
fix through its frozen API and passes synthetic native/Phoenix regression
checks. Fresh Ubuntu installation and a live trusted-fixture recording now
also pass for that exact new sidecar. The guest denied a benign Bubblewrap
namespace probe, so the rehearsal's explicit in-VM opt-out must not be
presented as default sandbox support. No kernel controls were weakened.

The curated dataset now has 10,414 training examples (347 MB) and 558
validation examples (19 MB), each below 1 GB. The creator has authorized its
private Token Factory upload, not training, LangSmith upload or publication.
Only a completed remote-content checksum receipt establishes upload success.
Both Files API objects now have that receipt; training has not started.
The small held-out module trial scored Nano 1/3, Super 2/3 and Ultra 3/3;
see `evaluations/coding-v1/README.md` for the single-trial limits and disclosed
test-contract correction. No broad superiority or router-quality claim follows.

The milestones below include historical evidence; source/package identity
must be matched before interpreting any result as current delivery proof.

## Product and track

Bifang is a desktop IDE for the **Coding and Agentic Engineering** track. The
desktop coding loop is the submission; the longer-term product vision retains
both desktop and mobile clients, with mobile following as a companion for
session review and approvals rather than a second full IDE before the deadline.
KV-cache quantization remains an evidence-driven research thread, not the
product definition or a current serving optimization.

The GPU-acceleration interest was inspired by the prospect of running coding
agents on desk-side AI hardware. NVIDIA now uses **RTX Spark** for its new class
of Windows PCs and **DGX Spark** for its desktop AI supercomputer platform;
both are relevant examples, but neither is currently a tested Bifang local
inference target. The hackathon build gets model inference from Nebius Token
Factory (or a separately configured NIM endpoint), and no local-GPU speedup is
claimed. A local backend can remain a post-submission direction without
weakening the current cloud-backed Track 1 demo.

The official [Devpost rules](https://nebiusglobalaihackathon.devpost.com/rules)
require a working app using an NVIDIA open model on Token Factory or Nebius AI
Cloud, a public code repository with an open-source license and setup README, a
working demo, hosted app, or test-build URL, and a public YouTube demo of no
more than three minutes. Testing access must remain free and unrestricted
through the judging period ending December 15. The
submission deadline is October 30, 2026 at 10:00 PDT.

## Verified implementation

- Public commit `1372625f51954c43b2377efd47aa9b0a51141ee9` was downloaded
  into a separate directory and passed `npm ci` followed by `npm run build`.
  Its tracked files matched the then-current local working copy byte for byte.
  Subsequent local changes are not published. This repaired
  a prior truncated upload of `ChatPanel.tsx`; use this commit or a newer
  verified revision rather than the earlier affected revision.
- Python is constrained to `>=3.11,<3.12`; all source files pass Python
  compilation; the earlier development milestone passed 93 tests, superseded
  by the current 202-test result above.
  The newer compaction, memory and history changes are not yet in the public desktop package.
- An agent regression test exercises the model → read-file tool → model
  exchange through the HTTP provider adapter, including nested usage metadata.
  It covers task-schema argument binding and assistant message roles.
- Provider selection is authoritative for streamed and regular requests;
  an NVIDIA-prefixed model identifier no longer overrides the selected
  Nebius endpoint. Eight routing checks cover default/explicit selections
  and refusal to silently fall back from a missing provider.
- The agent's outer task router now preserves the configured deployment
  model and provider for every task type. Automatic task classification no
  longer substitutes a hard-coded NVIDIA endpoint or an unverified model ID.
- Session deletion refuses active agent requests with HTTP 409. A concurrent
  request regression test verifies that the worktree cleanup happens only
  after the chat finishes; desktop submission is also disabled during reset.
- The desktop frontend passes the production TypeScript/Vite build; the
  production dependency audit reports zero vulnerabilities.
- The Tauri bridge now registers file-tree and server-status commands, and
  file nodes serialize the `type` field expected by the frontend. A locked
  Windows GNU `cargo check --tests` passes with a temporary check-only config
  that omits the platform-specific sidecar. This type-check is not a native
  package build or runtime test.
- The desktop New Chat action now closes its server-side session and asks
  before discarding un-applied worktree changes. Unused dashboard, reasoning,
  and verification panels containing fabricated sample metrics were removed;
  no measured performance claims are shown as live data.
- The Linux Python server sidecar builds with PyInstaller and its packaged
  executable successfully serves `/health` on loopback.
- A local OTLP collector test verifies Phoenix span export, and a server test
  verifies non-loopback requests require the configured API key.
- The Rust/Tauri app now uses packaged frontend assets, least-privilege dialog
  capability, a scoped CSP, a private per-user `.env` path, and the bundled
  server sidecar. A native Linux **release-profile Debian preview** now builds.
  Vite emits assets to `desktop/dist`, matching Tauri's packaged asset path.
  The extracted app completed a live Token Factory task under a virtual X
  display through its actual UI, including action approvals, diff review,
  confirmation, and apply. Only the parser changed and all five original
  checks passed. Automated clicks used an exact-action allowlist; workspace
  selection was preseeded. See [demo evidence](DEMO_EVIDENCE.md).
- The Rust app passes a Windows GNU target `cargo check`; this is compile-time
  evidence only, not a Windows installer or runtime test.
- Prior same-day live checks confirmed both configured inference paths
  authenticated and accepted a tiny Nemotron Ultra request. Do not show API
  keys in logs, repository history, screenshots, or video.
- A live Token Factory Nemotron Ultra rehearsal through the packaged server
  fixed the receipt-parser demo, preserved the original checks, applied only
  `receipts.py`, and passed all five checks. Three approvals were resolved by
  an exact-action automated allowlist. The local report records 7.48 seconds
  for this one run, including server startup; this is not a general performance
  benchmark. The sidecar hash matches the final Debian test package.
- The configured NVIDIA endpoint authenticated and returned text from
  `nvidia/nemotron-3-ultra-550b-a55b`. That endpoint is NVIDIA's public hosted
  API; no self-hosted NIM deployment is established by this result.
- Workspace patch export excludes Bifang/Arca audit directories, preventing
  internal transcripts from being applied to the source checkout.
- Docker now binds on the container interface and refuses non-loopback startup
  without `BIFANG_SERVER_API_KEY`.
- The Docker build now uses the checked-in `uv.lock`, and `.dockerignore`
  excludes environment files and generated assets. The local Docker daemon is
  inaccessible on the host, but the image now builds in a fresh Ubuntu 24.04
  VM. Its smoke test verifies non-root execution, key enforcement, workspace
  path confinement, and an authenticated session lifecycle. CI includes the
  same smoke check. This does not verify live container inference or sandboxing.
- The project has an Apache-2.0 license and `.env` is ignored.
- The original supplied archive contains an `.env`; the working release copy
  does not. Never publish or reuse the original archive as the repository
  source. Because the archive was shared during project review and the
  repository is now public, rotate credentials from that file immediately.
  Keep real credentials out of commits, build contexts, screenshots, and
  recordings.

## Not yet demonstrated

- CI jobs previously stopped before execution under an account billing lock.
  Local native compilation was unblocked using development packages extracted
  under `/tmp`, with `PKG_CONFIG_PATH` and a native link search path pointing
  there. System package installation still requires administrator access.
  The earlier preview's release-profile build, extracted-app UI test, and fresh
  Ubuntu 24.04 installation/live UI task passed. The latest approval-level
  candidate now independently passes fresh installation/live coding and a
  separate scoped-profile synthetic sandboxed native workflow, as documented
  at the top of this page. The newer preview selects its workspace
  through the actual in-app path dialog, rejecting invalid input first;
  native GTK chooser selection remains unverified. This build
  references GLIBC symbols through 2.39 and must not be advertised as Debian
  12 compatible without a suitable baseline rebuild and runtime test.
- The public Apache-2.0 source repository is
  [Protocol-X-01/bifang](https://github.com/Protocol-X-01/bifang). The
  sanitized source tree is on `main`; the original archive was not published.
- No live 8×H200 deployment is evidenced. Token Factory inference does not
  prove that this project provisioned eight H200s.
- KV-cache quantization is a standalone prototype, not connected to the NIM or
  TensorRT-LLM serving path; no speed, memory, or recall claim is supported.
- Phoenix export passes a real temporary authenticated Phoenix collector and
  bounded live model/tool rehearsal from source. The newer frozen sidecar also
  passes a synthetic provider/file/error collector rehearsal, but frozen SSE
  and production operations remain unverified. Lobster Trap
  remains disabled after pinned synthetic compatibility checks found SSE,
  tool-argument and structured-content inspection gaps; see `LOBSTERTRAP.md`.
  It must not be presented as integrated metrics or serving-path guardrails.
- A public Linux test build is available in
  [preview 2](https://github.com/Protocol-X-01/Bifang/releases/tag/v0.2.0-preview.2).
  The public YouTube video and a funded, free judge-access arrangement remain
  required. Bring-your-own-key installation alone does not prove free access.

## Critical path

1. Use the verified in-app path dialog for the supported Ubuntu walkthrough;
   native GTK chooser automation remains a separate unverified UI path.
   Resolve CI billing or retain the verified local builder and distribution baseline.
2. Preserve the successful native UI rehearsal and verify any separately
   deployed NIM endpoint. Distinguish hosted NVIDIA API access from NIM.
3. Keep the public Apache-2.0 repository limited to the sanitized working
   copy. Rotate credentials from the supplied archive promptly; confirm no
   actual credentials were used in the public source, build context, or demo.
4. Record and publish a concise demo (≤3 minutes) showing the user-visible IDE,
   Nebius Token Factory, NVIDIA Nemotron, approvals, real diff, and test result.
5. Complete the active product requirements tracked in `PRODUCT_EXPANSION.md`.
   KV-cache/GPU experiments are deferred; preserve the explicit distinction
   between hosted NVIDIA-compatible inference and a separately deployed NIM.

Use [submission handoff](SUBMISSION_CHECKLIST.md) for the current remaining
gates and [judge walkthrough](JUDGE_QUICKSTART.md) for the unreleased candidate.
